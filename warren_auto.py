# ==================================================
# 💡 終極防爆：解決雲端無黑視窗環境導致 FinMind 崩潰的 Bug
# ==================================================
import sys
import os

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
# ==================================================

import datetime
import time
import threading
import pandas as pd
from FinMind.data import DataLoader
import ta  # 💡 引入專業技術分析套件

# 引入 Flask 與 LINE 官方套件
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ==================================================
# 🔑 安全修改：從雲端環境變數讀取金鑰，GitHub 上完全看不到真密碼！
# ==================================================
# 💡 os.getenv 會去讀取系統環境變數，括號內是變數名稱
RAW_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
RAW_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")

# 自動清除換行與空白防護
LINE_CHANNEL_ACCESS_TOKEN = RAW_TOKEN.replace("\n", "").replace(" ", "").strip()
LINE_CHANNEL_SECRET = RAW_SECRET.replace("\n", "").replace(" ", "").strip()

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# ==================================================
# 💡 全域記憶體變數
# ==================================================
global_multiplier = 1.2

# 💡 請填入您的 LINE User ID (傳任意文字給雷達，它會印出來給您複製)
MY_LINE_USER_ID = 'Uc5021074b341423eb34f332cea077309' 

stock_list = {
    '2340': '台亞',
    '3042': '晶技',
    '6805': '富世達',
    '2317': '鴻海',
    '2330': '台積電',
    '2454': '聯發科'
}

# ==================================================
# 📊 核心策略分析邏輯 (爆量＋三大法人籌碼＋KD交叉)
# ==================================================
def run_strategy_for_line(volume_multiplier):
    dl = DataLoader()
    today_dt = datetime.date.today()
    end_date = today_dt.strftime("%Y-%m-%d")
    start_date = (today_dt - datetime.timedelta(days=50)).strftime("%Y-%m-%d")

    now_time = datetime.datetime.now().time()
    is_market_open = (today_dt.weekday() < 5) and (datetime.time(9, 0) <= now_time <= datetime.time(13, 35))

    reply_msg = f"📊【台股法人級多指標篩選】\n"
    reply_msg += f"🎯 門檻：均量 × {volume_multiplier}倍 + 三大法人買超 + KD多頭\n"
    reply_msg += f"⏰ 時間：{datetime.datetime.now().strftime('%m/%d %H:%M:%S')}\n"
    reply_msg += "-------------------------\n"
    
    matched_stocks = []

    for stock_id, stock_name in stock_list.items():
        try:
            df_hist = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            if df_hist.empty:
                reply_msg += f"📈 {stock_name}({stock_id})：⚠️暫無數據\n\n"
                continue
                
            df_hist['張數'] = df_hist['Trading_Volume'] / 1000
            
            # 使用 ta 套件計算標準 KD (9, 3, 3)
            kd_inst = ta.momentum.StochasticOscillator(
                high=df_hist['max'], low=df_hist['min'], close=df_hist['close'], 
                window=9, smooth_window=3
            )
            df_hist['K'] = kd_inst.stoch().round(1)
            df_hist['D'] = kd_inst.stoch_signal().round(1)
            
            if is_market_open:
                df_tick = dl.taiwan_stock_tick(stock_id=stock_id, date=end_date)
                if not df_tick.empty:
                    current_price = df_tick['price'].iloc[-1]
                    today_volume = df_tick['volume'].sum() / 1000
                    five_day_avg = df_hist['張數'].tail(5).mean()
                    status_lbl = " (即時)"
                else:
                    latest_day = df_hist.iloc[-1]
                    current_price = latest_day['close']
                    today_volume = latest_day['張數']
                    five_day_avg = df_hist['張數'].rolling(5).mean().iloc[-1]
                    status_lbl = ""
            else:
                latest_day = df_hist.iloc[-1]
                current_price = latest_day['close']
                today_volume = latest_day['張數']
                five_day_avg = df_hist['張數'].iloc[-6:-1].mean()
                if pd.isna(five_day_avg):
                    five_day_avg = df_hist['張數'].rolling(5).mean().iloc[-1]
                status_lbl = " (休市)"

            if pd.isna(today_volume): today_volume = 0.0
            if pd.isna(five_day_avg) or five_day_avg == 0: five_day_avg = 1.0

            # 抓取法人籌碼面數據
            df_inst = dl.taiwan_stock_institutional_investors(stock_id=stock_id, start_date=start_date, end_date=end_date)
            foreign_buy = 0
            investment_buy = 0
            
            if not df_inst.empty:
                last_inst_date = df_inst['date'].max()
                df_last_inst = df_inst[df_inst['date'] == last_inst_date]
                
                f_data = df_last_inst[df_last_inst['name'] == 'Foreign_Investor']
                it_data = df_last_inst[df_last_inst['name'] == 'Investment_Trust']
                
                if not f_data.empty: foreign_buy = int(f_data['buy'].sum() - f_data['sell'].sum()) / 1000
                if not it_data.empty: investment_buy = int(it_data['buy'].sum() - it_data['sell'].sum()) / 1000

            is_volume_up = today_volume > (five_day_avg * volume_multiplier)
            is_chip_clean = (foreign_buy > 0) or (investment_buy > 0)
            
            current_k = df_hist['K'].iloc[-1]
            current_d = df_hist['D'].iloc[-1]
            prev_k = df_hist['K'].iloc[-2]
            prev_d = df_hist['D'].iloc[-2]
            
            kd_text = f"K:{current_k}/D:{current_d}"
            if prev_k <= prev_d and current_k > current_d:
                kd_status = "🌟 黃金交叉"
            elif current_k > current_d:
                kd_status = "📈 K>D 多頭"
            else:
                kd_status = "📉 K<D 空頭"

            if is_volume_up and is_chip_clean and (current_k > current_d):
                matched_stocks.append(stock_name)
                star_icon = "🔥"
            else:
                star_icon = "📈"

            reply_msg += f"{star_icon} {stock_name}({stock_id})：{current_price}元{status_lbl}\n"
            reply_msg += f" 🔹今日：{today_volume:.1f}張 / 5日均：{five_day_avg:.1f}張\n"
            reply_msg += f" 🔹外資：{'+' if foreign_buy>0 else ''}{foreign_buy:.1f}張 / 投信：{'+' if investment_buy>0 else ''}{investment_buy:.1f}張\n"
            reply_msg += f" 🔹技術：{kd_text} ({kd_status})\n\n"
            
            time.sleep(0.3)
        except Exception:
            reply_msg += f"⚠️ {stock_name}({stock_id}) 分析超時\n\n"

    reply_msg += "-------------------------\n"
    if matched_stocks:
        reply_msg += f"🚀 法人現形強勢股：【 {', '.join(matched_stocks)} 】"
    else:
        reply_msg += "😭 今日暫無多指標共振個股。"
        
    return reply_msg

# ==================================================
# ⏰ 自動定時主動推播模組 (每週一至週五 13:40 自動發送)
# ==================================================
def cron_job_timer():
    while True:
        try:
            now = datetime.datetime.now()
            if now.weekday() < 5 and now.hour == 13 and now.minute == 40 and now.second < 30:
                report_text = run_strategy_for_line(volume_multiplier=global_multiplier)
                line_bot_api.push_message(MY_LINE_USER_ID, TextSendMessage(text=f"🔔【盤後定時自動回報】\n\n{report_text}"))
                time.sleep(40)
        except Exception:
            pass
        time.sleep(15)

timer_thread = threading.Thread(target=cron_job_timer, daemon=True)
timer_thread.start()

# ==================================================
# 🌐 3. 接收 LINE 訊號與指令解析
# ==================================================
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global global_multiplier, stock_list
    user_msg = event.message.text.strip()
    user_id = event.source.user_id
    
    if user_msg == "選股" or user_msg == "1" or user_msg.lower() == "a":
        result_text = run_strategy_for_line(volume_multiplier=global_multiplier)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_text))

if __name__ == "__main__":
    # Render 部署通常需要讀取 PORT 環境變數
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
