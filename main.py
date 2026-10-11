import os
import requests
import time

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

print("=" * 40)
print("Crypto-bot started successfully!")
print("Smart Money Trading Bot for Bitpin")
print("=" * 40)

if not TOKEN:
    print("ERROR: TELEGRAM_BOT_TOKEN not found!")
    exit(1)

print(f"Token loaded: {TOKEN[:10]}...")

# پاک کردن Webhook (مشکل اصلی همین بود)
try:
    delete_url = f"https://api.telegram.org/bot{TOKEN}/deleteWebhook"
    response = requests.get(delete_url, timeout=15)
    print(f"Delete Webhook: {response.text}")
except Exception as e:
    print(f"Delete Webhook Error: {e}")

print("Waiting for messages to detect chat_id...")
print("Send a message to your bot now!")
print("-" * 40)

offset = 0

while True:
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        params = {"offset": offset, "timeout": 10}
        response = requests.get(url, params=params, timeout=15)
        data = response.json()

        if data.get("ok") and data.get("result"):
            for update in data["result"]:
                offset = update["update_id"] + 1
                
                if "message" in update:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"].get("text", "")
                    
                    print("=" * 40)
                    print(f"CHAT_ID FOUND: {chat_id}")
                    print(f"Message: {text}")
                    print(f"From: {update['message']['from'].get('first_name', 'Unknown')}")
                    print("=" * 40)
                    print("Copy this CHAT_ID to Railway Variables as TELEGRAM_CHAT_ID")
                    print("=" * 40)
        else:
            print(f"No messages yet. Status: {data.get('ok')}")

    except Exception as e:
        print(f"Error: {e}")
    
    time.sleep(5)
