import os
import time
import random
import requests
import threading
import json
from datetime import datetime
from html import escape

from flask import Flask, request, redirect, session

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
PANEL_USERNAME = os.getenv("PANEL_USERNAME", "")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "")
PORT = int(os.getenv("PORT", "8080"))
OFFSET = None

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-in-railway")

user_state = {}
data_lock = threading.Lock()


def load_json(filename, default=None):
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


coins = load_json("coins.json", {})
settings = load_json("settings.json", {})
messages = load_json("messages.json", {})
orders = load_json("orders.json", {})


MESSAGE_DEFAULTS = {
    "welcome": "👋 Zaqel Swap'a hoş geldiniz.\n\nGüvenli, hızlı ve manuel onaylı takas platformu.",
    "swap_menu": "🔄 İşlem türünü seçiniz:",
    "coin_select_crypto_to_crypto": "🔄 Göndereceğiniz kripto para birimini seçiniz.",
    "coin_select_crypto_to_crypto_receive": "🔄 Almak istediğiniz kripto para birimini seçiniz.",
    "coin_select_iban_to_crypto": "🏦 Satın almak istediğiniz kripto para birimini seçiniz.",
    "coin_select_crypto_to_iban": "💳 TL'ye çevirmek istediğiniz kripto para birimini seçiniz.",
    "amount_question_crypto_to_crypto": "💰 Göndereceğiniz kripto miktarını giriniz:",
    "amount_question_iban_to_crypto": "💰 Göndereceğiniz TL miktarını giriniz:",
    "amount_question_crypto_to_iban": "💰 Bozduracağınız kripto miktarını giriniz:",
    "wallet_question": "📥 Alıcı cüzdan adresini giriniz:",
    "iban_question": "🏦 IBAN adresinizi giriniz:",
    "name_question": "👤 IBAN sahibinin ad soyad bilgisini giriniz:",
    "support": "📞 Destek için admin ile iletişime geçiniz.",
    "help": "ℹ️ İşlem türünü seçin ve bilgileri doldurun.",
    "iban_warning": "⚠️ Verilen IBAN numarasına para gönderen kişinin TC Kimlik numarasını açıklama kısmında belirtmesi zorunludur. Aksi takdirde dönüşüm işlemi gerçekleştirilmeyecektir.",
    "order_created": "✅ Siparişiniz oluşturuldu.",
    "order_completed": "✅ Siparişiniz tamamlandı.",
    "order_rejected": "❌ Siparişiniz reddedildi.",
    "orders_title": "📦 Siparişleriniz:",
    "orders_empty": "📦 Henüz siparişiniz yok.",
    "fees_title": "💰 Komisyonlar:",
    "iban_closed": "❌ Şu anda IBAN ile ödeme kapalıdır.",
    "session_expired": "❌ İşlem süresi doldu. Lütfen tekrar başlayın.",
    "working_hours": "09:00 - 23:59",
    "button_start_swap": "🔄 Swap Başlat",
    "button_my_orders": "📦 Siparişlerim",
    "button_fees": "💰 Komisyonlar",
    "button_help": "ℹ️ Nasıl Çalışır?",
    "button_support": "📞 Destek",
    "button_iban_to_crypto": "🏦 IBAN → Kripto",
    "button_crypto_to_iban": "💳 Kripto → IBAN",
    "button_crypto_to_crypto": "🔄 Kripto → Kripto",
    "button_main_menu": "⬅️ Ana Menü",
    "button_back": "⬅️ Geri",
}

for key, default_value in MESSAGE_DEFAULTS.items():
    messages.setdefault(key, default_value)

save_json("messages.json", messages)


ICON_DEFAULTS = {
    "icon_start_swap": "5893252234614939371",
    "icon_my_orders": "5895533287450877887",
    "icon_fees": "5895334439055009075",
    "icon_help": "5895656948149263789",
    "icon_support": "5895698390288703053",
    "icon_iban_to_crypto": "5895549153060069171",
    "icon_crypto_to_iban": "5895506164732403256",
    "icon_crypto_to_crypto": "5895671971944866108",
    "icon_main_menu": "",
    "icon_back": "",
    "icon_pending": "5895304795190730655",
    "icon_processing": "5895589615946964496",
    "icon_security": "5895439304976506343",
    "icon_rejected": "5895319286410387652",
    "icon_completed": "5893391786692323248",
}

for key, default_value in ICON_DEFAULTS.items():
    if not str(messages.get(key, "")).strip():
        messages[key] = default_value

save_json("messages.json", messages)

COIN_CUSTOM_EMOJI_DEFAULTS = {
    "TRX": "5895440778150288520",
    "LTC": "5895441495409828662",
    "USDT": "5895571353746021767",
}

for symbol, custom_emoji_id in COIN_CUSTOM_EMOJI_DEFAULTS.items():
    if symbol in coins and not str(coins[symbol].get("custom_emoji_id", "")).strip():
        coins[symbol]["custom_emoji_id"] = custom_emoji_id

save_json("coins.json", coins)


def telegram_button(text, callback_data, icon_key=None):
    button = {
        "text": text,
        "callback_data": callback_data,
    }

    if icon_key:
        custom_emoji_id = str(messages.get(icon_key, "")).strip()
        if custom_emoji_id:
            button["icon_custom_emoji_id"] = custom_emoji_id

    return button


def api(method, data):
    try:
        return requests.post(
            f"https://api.telegram.org/bot{TOKEN}/{method}",
            json=data,
            timeout=30,
        ).json()
    except Exception as exc:
        print("TELEGRAM API ERROR:", exc)
        return {}


def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": str(text)}
    if keyboard:
        data["reply_markup"] = keyboard
    return api("sendMessage", data)


def answer(cb_id):
    api("answerCallbackQuery", {"callback_query_id": cb_id})


def active_coins():
    return {k: v for k, v in coins.items() if v.get("active") == "on"}


def coin_label(symbol):
    c = coins.get(symbol, {})
    name = c.get("name", symbol)
    return f"{name} ({symbol})"


def coin_button(symbol, prefix):
    coin = coins.get(symbol, {})
    button = {
        "text": coin_label(symbol),
        "callback_data": f"{prefix}_{symbol}",
    }

    custom_emoji_id = str(coin.get("custom_emoji_id", "")).strip()
    if custom_emoji_id:
        button["icon_custom_emoji_id"] = custom_emoji_id

    return button


def menu(chat_id):
    send(
        chat_id,
        messages.get("welcome", MESSAGE_DEFAULTS["welcome"]),
        {
            "inline_keyboard": [
                [telegram_button(messages.get("button_start_swap", MESSAGE_DEFAULTS["button_start_swap"]), "swap", "icon_start_swap")],
                [telegram_button(messages.get("button_my_orders", MESSAGE_DEFAULTS["button_my_orders"]), "orders", "icon_my_orders")],
                [telegram_button(messages.get("button_fees", MESSAGE_DEFAULTS["button_fees"]), "fees", "icon_fees")],
                [telegram_button(messages.get("button_help", MESSAGE_DEFAULTS["button_help"]), "help", "icon_help")],
                [telegram_button(messages.get("button_support", MESSAGE_DEFAULTS["button_support"]), "support", "icon_support")],
            ]
        },
    )


def swap_menu(chat_id):
    send(
        chat_id,
        messages.get("swap_menu", MESSAGE_DEFAULTS["swap_menu"]),
        {
            "inline_keyboard": [
                [telegram_button(messages.get("button_iban_to_crypto", MESSAGE_DEFAULTS["button_iban_to_crypto"]), "type_iban_to_crypto", "icon_iban_to_crypto")],
                [telegram_button(messages.get("button_crypto_to_iban", MESSAGE_DEFAULTS["button_crypto_to_iban"]), "type_crypto_to_iban", "icon_crypto_to_iban")],
                [telegram_button(messages.get("button_crypto_to_crypto", MESSAGE_DEFAULTS["button_crypto_to_crypto"]), "type_crypto_to_crypto", "icon_crypto_to_crypto")],
                [telegram_button(messages.get("button_main_menu", MESSAGE_DEFAULTS["button_main_menu"]), "main", "icon_main_menu")],
            ]
        },
    )


def coin_menu(chat_id, prefix, exclude=None, message_text="Coin seçiniz:"):
    rows = []

    for symbol in active_coins():
        if symbol != exclude:
            rows.append([coin_button(symbol, prefix)])

    rows.append([
        telegram_button(
            messages.get("button_back", MESSAGE_DEFAULTS["button_back"]),
            "swap",
            "icon_back",
        )
    ])

    send(chat_id, message_text, {"inline_keyboard": rows})


def order_type_name(order_type):
    return {
        "crypto_to_crypto": "🔄 Kripto → Kripto",
        "iban_to_crypto": "🏦 IBAN → Kripto",
        "crypto_to_iban": "💳 Kripto → IBAN",
    }.get(order_type, order_type or "Bilinmiyor")


def create_order(chat_id, username):
    s = user_state.get(chat_id)
    if not s:
        return

    with data_lock:
        oid = str(random.randint(10000, 99999))
        while oid in orders:
            oid = str(random.randint(10000, 99999))

        orders[oid] = {
            "chat_id": chat_id,
            "username": username,
            **s,
            "status": "⏳ Bekliyor",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        save_json("orders.json", orders)

    type_name = order_type_name(s.get("type"))
    fee = settings.get("fee_" + s.get("type", ""), "0")
    min_amount = settings.get("min_" + s.get("type", ""), "0")

    text = (
        f"📄 Sipariş Özeti\n\n"
        f"No: #{oid}\n"
        f"Tür: {type_name}\n"
        f"Komisyon: %{fee}\n"
        f"Minimum İşlem: {min_amount} TL\n"
    )

    if s.get("type") == "crypto_to_crypto":
        text += (
            f"\nGönderilen: {s.get('amount', '')} {s.get('from_coin', '')}\n"
            f"Alınacak: {s.get('to_coin', '')}\n"
            f"Alıcı adres:\n{s.get('wallet', '')}\n"
        )

    elif s.get("type") == "iban_to_crypto":
        text += (
            f"\nÖdenecek TL: {s.get('amount', '')} TL\n"
            f"Alınacak: {s.get('to_coin', '')}\n"
            f"Alıcı adres:\n{s.get('wallet', '')}\n\n"
            f"🏦 Ödeme IBAN:\n"
            f"Banka: {settings.get('bank_name', '')}\n"
            f"IBAN: {settings.get('iban', '')}\n"
            f"Alıcı: {settings.get('iban_owner', '')}\n\n"
            f"{messages.get('iban_warning', '')}\n"
        )

    elif s.get("type") == "crypto_to_iban":
        text += (
            f"\nGönderilen: {s.get('amount', '')} {s.get('from_coin', '')}\n"
            f"IBAN:\n{s.get('iban', '')}\n"
            f"Ad Soyad: {s.get('name', '')}\n"
        )

    text += "\nDurum: ⏳ Admin onayı bekleniyor"

    created_prefix = messages.get("order_created", "✅ Siparişiniz oluşturuldu.")
    send(chat_id, f"{created_prefix}\n\n{text}")

    if ADMIN_CHAT_ID:
        send(
            ADMIN_CHAT_ID,
            (
                f"🚨 Yeni Sipariş\n\n"
                f"Kullanıcı: @{username}\n"
                f"{text}\n\n"
                f"Web panelden tamamlayabilir veya reddedebilirsiniz.\n"
                f"Komutla tamamlamak için: /tamamla {oid}"
            ),
        )

    user_state.pop(chat_id, None)


def my_orders(chat_id):
    found = [
        f"#{oid} — {o.get('status', 'Bilinmiyor')}"
        for oid, o in orders.items()
        if str(o.get("chat_id")) == str(chat_id)
    ]
    if found:
        send(chat_id, messages.get("orders_title", MESSAGE_DEFAULTS["orders_title"]) + "\n\n" + "\n".join(found))
    else:
        send(chat_id, messages.get("orders_empty", MESSAGE_DEFAULTS["orders_empty"]))


def update_order_status(oid, new_status, reject_reason="", approval_reason=""):
    oid = str(oid)

    with data_lock:
        order = orders.get(oid)
        if not order:
            return False, "Sipariş bulunamadı."

        if new_status == "completed":
            order["status"] = "✅ Tamamlandı"
            order["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order["approval_reason"] = approval_reason.strip()
            order["archived"] = False
            user_message = messages.get("order_completed", MESSAGE_DEFAULTS["order_completed"])

        elif new_status == "rejected":
            order["status"] = "❌ Reddedildi"
            order["rejected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            order["reject_reason"] = reject_reason.strip()
            order["archived"] = False
            user_message = messages.get("order_rejected", MESSAGE_DEFAULTS["order_rejected"])

        else:
            return False, "Geçersiz durum."

        save_json("orders.json", orders)

    notification = f"{user_message}\n\nSipariş No: #{oid}"

    if new_status == "completed" and approval_reason.strip():
        notification += f"\nOnay notu: {approval_reason.strip()}"

    if new_status == "rejected" and reject_reason.strip():
        notification += f"\nRed sebebi: {reject_reason.strip()}"

    send(order.get("chat_id"), notification)
    return True, order["status"]


def bot_loop():
    global OFFSET
    print("Bot started")

    while True:
        try:
            r = requests.get(
                f"https://api.telegram.org/bot{TOKEN}/getUpdates",
                params={"offset": OFFSET, "timeout": 20},
                timeout=30,
            ).json()

            for u in r.get("result", []):
                OFFSET = u["update_id"] + 1

                if "message" in u:
                    msg = u["message"]
                    chat_id = msg["chat"]["id"]
                    text = msg.get("text", "")
                    username = msg.get("from", {}).get("username", "unknown")

                    custom_emoji_ids = [
                        str(entity.get("custom_emoji_id"))
                        for entity in msg.get("entities", [])
                        if entity.get("type") == "custom_emoji"
                        and entity.get("custom_emoji_id")
                    ]

                    if custom_emoji_ids and str(chat_id) == str(ADMIN_CHAT_ID):
                        send(
                            chat_id,
                            "\n".join(custom_emoji_ids)
                        )
                        continue

                    if text == "/start":
                        menu(chat_id)

                    elif text == "/siparislerim":
                        my_orders(chat_id)

                    elif text.startswith("/tamamla") and str(chat_id) == str(ADMIN_CHAT_ID):
                        parts = text.split()
                        if len(parts) >= 2:
                            ok, result = update_order_status(parts[1], "completed")
                            send(chat_id, "✅ Sipariş tamamlandı." if ok else f"❌ {result}")
                        else:
                            send(chat_id, "❌ Kullanım: /tamamla SIPARIS_NO")

                    elif chat_id in user_state:
                        s = user_state[chat_id]
                        step = s.get("step")

                        if step == "amount":
                            s["amount"] = text

                            if s["type"] in ["crypto_to_crypto", "iban_to_crypto"]:
                                s["step"] = "wallet"
                                send(
                                    chat_id,
                                    messages.get(
                                        "wallet_question",
                                        "📥 Alacağın coin için cüzdan adresini gir:"
                                    ),
                                )
                            else:
                                s["step"] = "iban"
                                send(
                                    chat_id,
                                    messages.get(
                                        "iban_question",
                                        "🏦 IBAN adresini gir:"
                                    ),
                                )

                        elif step == "wallet":
                            s["wallet"] = text
                            create_order(chat_id, username)

                        elif step == "iban":
                            s["iban"] = text
                            s["step"] = "name"
                            send(
                                chat_id,
                                messages.get(
                                    "name_question",
                                    "👤 IBAN sahibinin ad soyad bilgisini gir:"
                                ),
                            )

                        elif step == "name":
                            s["name"] = text
                            create_order(chat_id, username)

                if "callback_query" in u:
                    cb = u["callback_query"]
                    answer(cb["id"])
                    chat_id = cb["message"]["chat"]["id"]
                    data = cb["data"]

                    if data == "main":
                        menu(chat_id)

                    elif data == "swap":
                        swap_menu(chat_id)

                    elif data == "orders":
                        my_orders(chat_id)

                    elif data == "fees":
                        send(
                            chat_id,
                            (
                                messages.get("fees_title", MESSAGE_DEFAULTS["fees_title"]) + "\n\n"
                                f"🔄 Kripto → Kripto: %{settings.get('fee_crypto_to_crypto', '0')}\n"
                                f"🏦 IBAN → Kripto: %{settings.get('fee_iban_to_crypto', '0')}\n"
                                f"💳 Kripto → IBAN: %{settings.get('fee_crypto_to_iban', '0')}"
                            ),
                        )

                    elif data == "help":
                        send(
                            chat_id,
                            messages.get("help", "ℹ️ İşlem türünü seçin.")
                            + f"\n\nÇalışma saatleri: {messages.get('working_hours', '')}",
                        )

                    elif data == "support":
                        send(chat_id, messages.get("support", "📞 Destek"))

                    elif data == "type_crypto_to_crypto":
                        user_state[chat_id] = {"type": "crypto_to_crypto"}
                        coin_menu(
                            chat_id,
                            "from",
                            message_text=messages.get(
                                "coin_select_crypto_to_crypto",
                                "🔄 Takas etmek istediğiniz kripto para birimini seçiniz."
                            ),
                        )

                    elif data == "type_iban_to_crypto":
                        if settings.get("iban_active") != "on":
                            send(chat_id, messages.get("iban_closed", MESSAGE_DEFAULTS["iban_closed"]))
                        else:
                            user_state[chat_id] = {"type": "iban_to_crypto"}
                            coin_menu(
                                chat_id,
                                "to",
                                message_text=messages.get(
                                    "coin_select_iban_to_crypto",
                                    "🏦 Satın almak istediğiniz kripto para birimini seçiniz."
                                ),
                            )

                    elif data == "type_crypto_to_iban":
                        user_state[chat_id] = {"type": "crypto_to_iban"}
                        coin_menu(
                            chat_id,
                            "from",
                            message_text=messages.get(
                                "coin_select_crypto_to_iban",
                                "💳 TL'ye çevirmek istediğiniz kripto para birimini seçiniz."
                            ),
                        )

                    elif data.startswith("from_"):
                        coin = data.replace("from_", "")
                        s = user_state.get(chat_id)
                        if not s:
                            send(chat_id, messages.get("session_expired", MESSAGE_DEFAULTS["session_expired"]))
                            continue

                        s["from_coin"] = coin

                        if