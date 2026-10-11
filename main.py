import os
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("=" * 40)
print("Crypto-bot started successfully!")
print("Smart Money Trading Bot for Bitpin")
print("=" * 40)

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not found!")
    exit(1)

if not CHAT_ID:
    print("ERROR: TELEGRAM_CHAT_ID not found!")
    exit(1)

print(f"Token loaded: {TOKEN[:10]}...")
print(f"Chat ID loaded: {CHAT_ID}")

# ارسال پیام تست
message = "Crypto-bot is alive! Telegram connection works."

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {
    "chat_id": CHAT_ID,
    "text": message
}

try:
    response = requests.post(url, data=data, timeout=15)
    result = response.json()
    
    if result.get("ok"):
        print("=" * 40)
        print("MESSAGE SENT SUCCESSFULLY!")
        print(f"Message: {message}")
        print("=" * 40)
    else:
        print(f"ERROR sending message: {result}")
        
except Exception as e:
    print(f"Error: {e}")

print("Done. Bot will stay alive...")

# حلقه بی‌نهایت برای زنده نگه داشتن سرویس
import time
while True:
    time.sleep(60)
