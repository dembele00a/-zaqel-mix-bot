import os
import time
import random
import requests

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
OFFSET = None

user_state = {}
orders = {}

COINS = {
    "TRX": "🔴 TRON (TRX)",
    "LTC": "⚪ Litecoin (LTC)",
    "USDT": "🔵 USDT (TRC20)",
}

def send_message(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json=data)

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
    send_message(chat_id, "👋 Zaqel Swap'a hoş geldiniz.\n\nGüvenli, hızlı ve manuel onaylı takas platformu.", keyboard)

def swap_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🏦 IBAN → Kripto", "callback_data": "iban_to_crypto"}],
            [{"text": "💳 Kripto → IBAN", "callback_data": "crypto_to_iban"}],
            [{"text": "🔄 Kripto → Kripto", "callback_data": "crypto_to_crypto"}],
            [{"text": "⬅️ Ana Menü", "callback_data": "main_menu"}],
        ]
    }
    send_message(chat_id, "🔄 İşlem türünü seçiniz:", keyboard)

def coin_from_menu(chat_id):
    keyboard = {
        "inline_keyboard": [
            [{"text": COINS["TRX"], "callback_data": "from_TRX"}],
            [{"text": COINS["LTC"], "callback_data": "from_LTC"}],
            [{"text": COINS["USDT"], "callback_data": "from_USDT"}],
            [{"text": "⬅️ Geri", "callback_data": "swap"}],
        ]
    }
    send_message(chat_id, "📤 Göndereceğin coini seç:", keyboard)

def coin_to_menu(chat_id, from_coin):
    rows = []
    for coin, label in COINS.items():
        if coin != from_coin:
            rows.append([{"text": label, "callback_data": f"to_{coin}"}])
    rows.append([{"text": "⬅️ Geri", "callback_data": "crypto_to_crypto"}])
    send_message(chat_id, "📥 Alacağın coini seç:", {"inline_keyboard": rows})

def create_order(chat_id, username):
    state = user_state[chat_id]
    order_id = random.randint(1000, 9999)

    orders[order_id] = {
        "chat_id": chat_id,
        "username": username,
        "from_coin": state["from_coin"],
        "to_coin": state["to_coin"],
        "amount": state["amount"],
        "wallet": state["wallet"],
        "status": "Admin onayı bekleniyor"
    }

    user_text = (
        f"📄 Sipariş Özeti\n\n"
        f"Sipariş No: #{order_id}\n"
        f"Tür: {state['from_coin']} → {state['to_coin']}\n"
        f"Miktar: {state['amount']} {state['from_coin']}\n"
        f"Alıcı Adresi:\n{state['wallet']}\n\n"
        f"Durum: ⏳ Admin onayı bekleniyor"
    )

    admin_text = (
        f"🚨 Yeni Swap Siparişi\n\n"
        f"No: #{order_id}\n"
        f"Kullanıcı: @{username}\n"
        f"Tür: {state['from_coin']} → {state['to_coin']}\n"
        f"Miktar: {state['amount']} {state['from_coin']}\n"
        f"Alıcı Adresi:\n{state['wallet']}\n\n"
        f"Manuel işlem sonrası kullanıcıya bilgi ver."
    )

    send_message(chat_id, user_text)

    if ADMIN_CHAT_ID:
        send_message(ADMIN_CHAT_ID, admin_text)

    user_state.pop(chat_id, None)

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
                msg = u["message"]
                chat_id = msg["chat"]["id"]
                text = msg.get("text", "")
                username = msg.get("from", {}).get("username", "unknown")

                if text == "/start":
                    main_menu(chat_id)

                elif chat_id in user_state:
                    step = user_state[chat_id].get("step")

                    if step == "amount":
                        user_state[chat_id]["amount"] = text
                        user_state[chat_id]["step"] = "wallet"
                        send_message(chat_id, "📥 Alacağın coin için cüzdan adresini gir:")

                    elif step == "wallet":
                        user_state[chat_id]["wallet"] = text
                        create_order(chat_id, username)

            if "callback_query" in u:
                cb = u["callback_query"]
                callback_id = cb["id"]
                chat_id = cb["message"]["chat"]["id"]
                data = cb["data"]

                answer_callback(callback_id)

                if data == "main_menu":
                    main_menu(chat_id)

                elif data == "swap":
                    swap_menu(chat_id)

                elif data == "crypto_to_crypto":
                    user_state[chat_id] = {"type": "crypto_to_crypto"}
                    coin_from_menu(chat_id)

                elif data.startswith("from_"):
                    coin = data.replace("from_", "")
                    user_state[chat_id]["from_coin"] = coin
                    coin_to_menu(chat_id, coin)

                elif data.startswith("to_"):
                    coin = data.replace("to_", "")
                    user_state[chat_id]["to_coin"] = coin
                    user_state[chat_id]["step"] = "amount"
                    send_message(chat_id, f"💰 Göndereceğin miktarı gir:\nÖrnek: 100")

                elif data == "iban_to_crypto":
                    send_message(chat_id, "🏦 IBAN → Kripto yakında eklenecek.")

                elif data == "crypto_to_iban":
                    send_message(chat_id, "💳 Kripto → IBAN yakında eklenecek.")

                elif data == "orders":
                    send_message(chat_id, "📦 Siparişlerim sistemi yakında eklenecek.")

                elif data == "fees":
                    send_message(chat_id, "💰 Komisyonlar:\n\n🔄 Kripto → Kripto: değişken\n🏦 IBAN → Kripto: değişken\n💳 Kripto → IBAN: değişken")

                elif data == "help":
                    send_message(chat_id, "ℹ️ İşlem seç → coin seç → miktar gir → adres gir → admin manuel tamamlar.")

                elif data == "support":
                    send_message(chat_id, "📞 Destek için admin ile iletişime geç.")

        time.sleep(1)

    except Exception as e:
        print("ERROR:", e)
        time.sleep(5)
