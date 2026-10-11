import sys
import os
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
# 🔑 關鍵設定：已為您精準填入最新申請的 LINE 通關憑證
# ==================================================
LINE_CHANNEL_ACCESS_TOKEN = 'nVnfDE3AZrJIouniBoNSchLCpyLSL2nlwO7zr+twctQF2L1AxFqogyxLBHDay05h/B9uDrmMvjrIXTR2yhLVc9VJmwtFWwrd7Hef5V7r8uC72PbQo/nBADAsn8zSfINI+U3iEBSOTxtpl7tVHVs5IAdB04t89/1O/w1cDnyilFU='
LINE_CHANNEL_SECRET = '376de813a560b7b7751c0de7d071375'

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# 您指定的精選追蹤個股名單 (後續在 GitHub 上也可以隨時增減)
stock_list = {
    '2340': '台亞',
    '3042': '晶技',
    '6805': '富世達',
    '2317': '鴻海',
    '2330': '台積電',
    '2454': '聯發科'
}

# ==================================================
# 📊 核心策略分析邏輯 (即時動態計算版)
# ==================================================
def run_strategy_for_line(volume_multiplier=1.2):
    dl = DataLoader()
    today_dt = datetime.date.today()
    end_date = today_dt.strftime("%Y-%m-%d")
    start_date = (today_dt - datetime.timedelta(days=25)).strftime("%Y-%m-%d")

    now_time = datetime.datetime.now().time()
    # 判斷是不是台股開盤時間
    is_market_open = (today_dt.weekday() < 5) and (datetime.time(9, 0) <= now_time <= datetime.time(13, 35))

    reply_msg = f"📊【台股主力爆量篩選】\n"
    reply_msg += f"🎯 門檻：5日均量 × {volume_multiplier} 倍\n"
    reply_msg += f"⏰ 時間：{datetime.datetime.now().strftime('%m/%d %H:%M:%S')}\n"
    reply_msg += "-------------------------\n"
    
    matched_stocks = []

    for stock_id, stock_name in stock_list.items():
        try:
            # 抓取歷史大數據
            df_hist = dl.taiwan_stock_daily(stock_id=stock_id, start_date=start_date, end_date=end_date)
            if df_hist.empty:
                continue
                
            df_hist['張數'] = df_hist['Trading_Volume'] / 1000
            
            if is_market_open:
                # 💡 盤中即時模式
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
                # 💡 盤後模式
                latest_day = df_hist.iloc[-1]
                current_price = latest_day['close']
                today_volume = latest_day['張數']
                five_day_avg = df_hist['張數'].rolling(5).mean().iloc[-1]
                status_lbl = ""

            is_volume_up = today_volume > (five_day_avg * volume_multiplier)
            status_text = f"🎉 爆量({volume_multiplier}倍)" if is_volume_up else "❌ 未達標"
            
            if is_volume_up:
                matched_stocks.append(stock_name)
                
            # 串接每一檔股票的戰況文字
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
# 🌐 3. 接收 LINE 伺服器訊號的網頁接口
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

# 手機傳 LINE 訊息進來時會自動觸發這裡
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_msg = event.message.text.strip()
    
    if user_msg == "選股":
        # 呼叫大數據分析
        result_text = run_strategy_for_line(volume_multiplier=1.2)
        # 回傳精美分析結果
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=result_text))
    else:
        line_bot_api.reply_message(
            event.reply_token, 
            TextSendMessage(text="🤖 您好！我是您的台股 AI 助手。請在對話框輸入【選股】，我馬上為您連線證交所分析最新的主力爆量訊號！")
        )

if __name__ == "__main__":
    # 💡 雲端必備：自動動態讀取雲端環境分配的 Port
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
