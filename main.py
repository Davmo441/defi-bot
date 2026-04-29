import os
import requests
import time

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("BOT_TOKEN:", BOT_TOKEN)
print("CHAT_ID:", CHAT_ID)

url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

response = requests.post(url, json={
    "chat_id": CHAT_ID,
    "text": "🚀 Bot Railway connecté !"
})

print("Status:", response.status_code)
print("Response:", response.text)

time.sleep(60)
