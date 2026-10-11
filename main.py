
import os
import requests

# خواندن توکن از Railway Variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

print("=" * 40)
print("Crypto-bot started successfully!")
print("Smart Money Trading Bot for Bitpin")
print("=" * 40)

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not found!")
else:
    print(f"Token loaded: {TOKEN[:10]}...")
    
    # ارسال پیام تست
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    
    if chat_id:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        data = {
            "chat_id": chat_id,
            "text": "Crypto-bot is alive!"
        }
        response = requests.post(url, data=data)
        print(f"Response: {response.status_code}")
        print(f"Result: {response.text}")
    else:
        print("TELEGRAM_CHAT_ID not set yet")
