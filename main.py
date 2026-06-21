import os
import time
import requests

TOKEN = os.getenv("BOT_TOKEN")
OFFSET = None

def send_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔄 Swap Başlat", "callback_data": "swap"}],
            [{"text": "📦 Siparişlerim", "callback_data": "orders"}],
            [{"text": "💰 Komisyonlar", "callback_data": "fees"}],
            [{"text": "ℹ️ Nasıl Çalışır?", "callback_data": "help"}],
            [{"text": "📞 Destek", "callback_data": "support"}],
        ]
    }

    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": "👋 Zaqel Swap'a hoş geldiniz.\n\nGüvenli, hızlı ve kolay kripto dönüşüm platformu.",
            "reply_markup": keyboard,
        },
    )

print("Bot started")

while True:
    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": OFFSET, "timeout": 20},
        ).json()

        for u in r.get("result", []):
            OFFSET = u["update_id"] + 1

            if "message" in u:
                chat_id = u["message"]["chat"]["id"]
                text = u["message"].get("text", "")

                if text == "/start":
                    send_menu(chat_id)

        time.sleep(1)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
