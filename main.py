import os
import requests
import time

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("=" * 40)
print("Crypto-bot started successfully!")
print("=" * 40)

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not found!")
    exit(1)

if not CHAT_ID:
    print("ERROR: TELEGRAM_CHAT_ID not found!")
    exit(1)

print(f"Token loaded: {TOKEN[:10]}...")
print(f"Chat ID loaded: {CHAT_ID}")

# ===== تست مستقیم (بدون پروکسی) =====
message = "Crypto-bot is alive! Direct connection test."

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
data = {
    "chat_id": CHAT_ID,
    "text": message
}

try:
    response = requests.post(url, data=data, timeout=20)
    result = response.json()
    
    if result.get("ok"):
        print("=" * 40)
        print("MESSAGE SENT SUCCESSFULLY (DIRECT)!")
        print(f"Message: {message}")
        print("=" * 40)
    else:
        print(f"ERROR: {result}")
        
except Exception as e:
    print(f"Error: {e}")

print("Done. Bot will stay alive...")

while True:
    time.sleep(60)
