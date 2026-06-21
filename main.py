import os
import time
import requests

TOKEN = os.getenv("BOT_TOKEN")
OFFSET = None

def send(chat_id, text):
    requests.get(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        params={
            "chat_id": chat_id,
            "text": text
        }
    )

print("Bot started")

while True:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": OFFSET, "timeout": 20}
        ).json()

        for u in r.get("result", []):
            OFFSET = u["update_id"] + 1

            if "message" in u:
                chat_id = u["message"]["chat"]["id"]
                text = u["message"].get("text", "")

                if text == "/start":
                    send(
                        chat_id,
                        "👋 Zaqel aktif.\n\n1. Kripto → Kripto\n2. IBAN → Kripto\n3. Kripto → IBAN"
                    )

        time.sleep(1)

    except Exception as e:
        print(e)
        time.sleep(5)
