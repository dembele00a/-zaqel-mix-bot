import os
import requests
import time

TOKEN = os.getenv("BOT_TOKEN")

def send(chat_id, text):
    requests.get(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        params={"chat_id": chat_id, "text": text}
    )

print("Bot started")

while True:
    time.sleep(60)
