import os
import time
import requests

TOKEN = os.getenv("BOT_TOKEN")
OFFSET = None

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard

    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage",
        json=data
    )

def answer_callback(callback_id):
    requests.post(
        f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback_id}
    )

def main_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔄 Swap Başlat", "callback_data": "swap"}],
            [{"text": "📦 Siparişlerim", "callback_data": "orders"}],
            [{"text": "💰 Komisyonlar", "callback_data": "fees"}],
            [{"text": "ℹ️ Nasıl Çalışır?", "callback_data": "help"}],
            [{"text": "📞 Destek", "callback_data": "support"}],
        ]
    }

    send_message(
        chat_id,
        "👋 Zaqel Swap'a hoş geldiniz.\n\nGüvenli, hızlı ve kolay kripto dönüşüm platformu.",
        keyboard
    )

def swap_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🏦 IBAN → Kripto", "callback_data": "iban_to_crypto"}],
            [{"text": "💳 Kripto → IBAN", "callback_data": "crypto_to_iban"}],
            [{"text": "🔄 Kripto → Kripto", "callback_data": "crypto_to_crypto"}],
            [{"text": "⬅️ Ana Menü", "callback_data": "main_menu"}],
        ]
    }

    send_message(
        chat_id,
        "🔄 İşlem türünü seçiniz:",
        keyboard
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
                    main_menu(chat_id)

            if "callback_query" in u:
                callback = u["callback_query"]
                callback_id = callback["id"]
                chat_id = callback["message"]["chat"]["id"]
                data = callback["data"]

                answer_callback(callback_id)

                if data == "swap":
                    swap_menu(chat_id)

                elif data == "main_menu":
                    main_menu(chat_id)

                elif data == "orders":
                    send_message(chat_id, "📦 Henüz sipariş geçmişi sistemi eklenmedi.")

                elif data == "fees":
                    send_message(
                        chat_id,
                        "💰 Komisyon Oranları:\n\n"
                        "🔄 Kripto → Kripto: %1\n"
                        "🏦 IBAN → Kripto: %3\n"
                        "💳 Kripto → IBAN: %2"
                    )

                elif data == "help":
                    send_message(
                        chat_id,
                        "ℹ️ Nasıl Çalışır?\n\n"
                        "1. İşlem türünü seçersiniz.\n"
                        "2. Göndereceğiniz ve alacağınız varlığı belirlersiniz.\n"
                        "3. Sipariş oluşturulur.\n"
                        "4. Admin işlemi manuel olarak tamamlar."
                    )

                elif data == "support":
                    send_message(chat_id, "📞 Destek için admin ile iletişime geçiniz.")

                elif data in ["iban_to_crypto", "crypto_to_iban", "crypto_to_crypto"]:
                    send_message(chat_id, "✅ İşlem türü seçildi. Bir sonraki aşamada coin seçimi eklenecek.")

        time.sleep(1)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
