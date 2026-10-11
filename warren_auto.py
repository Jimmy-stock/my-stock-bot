# ==================================================
# 💡 終極防爆：解決雲端無黑視窗環境導致 FinMind 崩潰的 Bug (絕對不能漏掉這段)
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
import pandas as pd
from FinMind.data import DataLoader

# 引入 Flask 與 LINE 官方套件
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage

app = Flask(__name__)

# ==================================================
# 🔑 關鍵設定：保持您最新申請的 LINE 通關憑證
# ==================================================
LINE_CHANNEL_ACCESS_TOKEN = 'nVnfDE3AZrJIouniBoNSchLCpyLSL2nlwO7zr+twctQF2L1AxFqogyxLBHDay05h/B9uDrmMvjrIXTR2yhLVc9VJmwtFWwrd7Hef5V7r8uC72PbQo/nBADAsn8zSfINI+U3iEBSOTxtpl7tVHVs5IAdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '376de813a560b7b7751c0de7d071375'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 💡 全域記憶體變數
global_multiplier = 1.2

stock_list = {
    '2340': '台亞',
    '3042': '晶技',
    '6805': '富世達',
    '2317': '鴻海',
    '2330': '台積電',
    '2454': '聯發科'
}

# ==================================================
# 📊 核心策略分析邏輯
# ==================================================
def run_strategy_for_line(volume_multiplier):
    dl = DataLoader()
    today_dt = datetime.date.today()
    end_date = today_dt.strftime("%Y-%m-%d")
    start_date = (today_dt - datetime.timedelta(days=25)).strftime("%Y-%m-%d")

    now_time = datetime.datetime.now().time()
    is_market_open = (today_dt.weekday() < 5) and (datetime.time(9, 0) <= now_time <= datetime.time(13, 35))

    reply_msg = f"📊【台股主力爆量篩選】\n"
    reply_msg += f"🎯 門檻：5日均量 × {volume_multiplier} 倍\n"
    reply_msg += f"⏰ 時間：{datetime.datetime.now().strftime('%m/%d %H:%M:%S')}\n"
    reply_msg += "-------------------------\n"
    
    matched_stocks = []

    for stock_id, stock_name in stock_list.items():
        try:
            df_hist = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            if df_hist.empty:
                continue
                
            df_hist['張數'] = df_hist['Trading_Volume'] / 1000
            
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
                five_day_avg = df_hist['張數'].rolling(5).mean().iloc[-1]
                status_lbl = ""

            is_volume_up = today_volume > (five_day_avg * volume_multiplier)
            status_text = f"🎉 爆量({volume_multiplier}倍)" if is_volume_up else "❌ 未達標"
            
            if is_volume_up:
                matched_stocks.append(stock_name)
                
            reply_msg += f"📈 {stock_name}({stock_id})：{current_price}元{status_lbl}\n"
            reply_msg += f" 🔹今日：{today_volume:.1f}張\n"
            reply_msg += f" 🔹均量：{five_day_avg:.1f}張\n"
            reply_msg += f" 🔹狀態：{status_text}\n\n"
            
            time.sleep(0.3)
        except Exception:
            reply_msg += f"⚠️ {stock_name}({stock_id}) 連線超時\n\n"

    reply_msg += "-------------------------\n"
    if matched_stocks:
        reply_msg += f"🔥 爆量攻擊標的：【 {', '.join(matched_stocks)} 】"
    else:
        reply_msg += "😭 今日暫無符合門檻個股。"
        
    return reply_msg

# ==================================================
# 🌐 3. 接收 LINE 訊號與 指令解析
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
    
    # 💡 捷徑一：開始選股
    if user_msg == "選股" or user_msg == "1" or user_msg.lower() == "a":
        result_text = run_strategy_for_line(volume_multiplier=global_multiplier)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_text))
        
    # 💡 捷徑二：修改倍數 (格式: 2 1.5)
    elif user_msg.startswith("修改倍數") or user_msg.startswith("2 ") or user_msg.lower().startswith("b "):
        try:
            parts = user_msg.split()
            global_multiplier = float(parts[1])
            success_text = f"✅ 門檻倍數已成功修改為：{global_multiplier} 倍！\n下一次輸入【1】時將自動套用新門檻。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=success_text))
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 修改失敗，請輸入正確快捷格式，例如：2 1.5"))

    # 💡 捷徑三：增加股票 (格式: 3 2382 廣達)
    elif user_msg.startswith("增加股票") or user_msg.startswith("3 ") or user_msg.lower().startswith("c "):
        try:
            parts = user_msg.split()
            new_id = str(parts[1])
            new_name = str(parts[2])
            stock_list[new_id] = new_name
            success_text = f"✅ 已成功將【{new_id} {new_name}】加入監控清單！"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=success_text))
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 增加失敗，請輸入正確快捷格式，例如：3 2382 廣達"))

    # 💡 捷徑四：刪除股票 (格式: 4 3042)
    elif user_msg.startswith("刪除股票") or user_msg.startswith("4 ") or user_msg.lower().startswith("d "):
        try:
            parts = user_msg.split()
            del_id = str(parts[1])
            if del_id in stock_list:
                del_name = stock_list[del_id]
                del stock_list[del_id]
                success_text = f"❌ 已成功將【{del_id} {del_name}】從清單中移除！"
            else:
                success_text = f"⚠️ 刪除失敗：清單中原本就沒有 {del_id} 這檔股票。"
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text=success_text))
        except Exception:
            line_bot_api.reply_message(event.reply_token, TextSendMessage(text="❌ 刪除失敗，請輸入正確快捷格式，例如：4 3042"))

    # 💡 快捷鍵選單提示文字
    else:
        info_text = "🤖 您好！我是您的台股 AI 助手。\n\n"
        info_text += "您可以直接輸入【數字】或【英文】捷徑來控制我：\n"
        info_text += "-------------------------\n"
        info_text += "👉 【1】或【A】 : 開始大數據選股\n"
        info_text += "👉 【2 1.5】或【B 1.5】 : 調整門檻倍數\n"
        info_text += "👉 【3 2382 廣達】或【C 2382 廣達】 : 加入監控\n"
        info_text += "👉 【4 3042】或【D 3042】 : 移除個股\n"
        info_text += "-------------------------\n"
        info_text += "💡 提示：指令與代號之間記得空一格喔！"
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=info_text))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
