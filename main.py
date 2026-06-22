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
referrals = load_json("referrals.json", {})


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
    "working_hours": "7/24 Açık",
    "min_amount_error": "❌ Minimum işlem tutarı: {min_amount}",
    "referral_title": "👥 Referans Sistemi",
    "referral_text": "Referans linkiniz:\n{ref_link}\n\nToplam davet: {count}\nReferans kodunuz: {code}",
    "referral_registered": "✅ Referans kaydınız alındı.",
    "button_start_swap": "🔄 Swap Başlat",
    "button_my_orders": "📦 Siparişlerim",
    "button_fees": "💰 Komisyonlar",
    "button_help": "ℹ️ Nasıl Çalışır?",
    "button_support": "📞 Destek",
    "button_referral": "👥 Referansım",
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
    "icon_start_swap": "",
    "icon_my_orders": "",
    "icon_fees": "",
    "icon_help": "",
    "icon_support": "",
    "icon_referral": "",
    "icon_iban_to_crypto": "",
    "icon_crypto_to_iban": "",
    "icon_crypto_to_crypto": "",
    "icon_main_menu": "",
    "icon_back": "",
}

for key, default_value in ICON_DEFAULTS.items():
    messages.setdefault(key, default_value)

save_json("messages.json", messages)


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
                [telegram_button(messages.get("button_referral", MESSAGE_DEFAULTS["button_referral"]), "referral", "icon_referral")],
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


def parse_amount(value):
    text = str(value or "").strip().replace(" ", "").replace(",", ".")
    try:
        amount = float(text)
        if amount <= 0:
            return None
        return amount
    except Exception:
        return None


def min_key_for_type(order_type):
    return "min_" + str(order_type or "")


def check_min_amount(order_type, amount_text):
    amount = parse_amount(amount_text)
    if amount is None:
        return False, "❌ Lütfen geçerli bir miktar giriniz."

    min_value = parse_amount(settings.get(min_key_for_type(order_type), "0"))
    if min_value and amount < min_value:
        msg = messages.get("min_amount_error", MESSAGE_DEFAULTS["min_amount_error"])
        return False, msg.replace("{min_amount}", str(settings.get(min_key_for_type(order_type), min_value)))

    return True, ""


def bot_username():
    cached = settings.get("bot_username", "").strip()
    if cached:
        return cached.lstrip("@")

    result = api("getMe", {})
    username = result.get("result", {}).get("username", "") if isinstance(result, dict) else ""
    if username:
        settings["bot_username"] = username
        save_json("settings.json", settings)
    return username


def referral_code(chat_id):
    return str(chat_id)


def register_referral(new_chat_id, ref_code):
    new_chat_id = str(new_chat_id)
    ref_code = str(ref_code or "").replace("ref_", "").strip()

    if not ref_code or ref_code == new_chat_id:
        return False

    with data_lock:
        profile = referrals.setdefault(new_chat_id, {})
        if profile.get("referrer_id"):
            return False

        profile["referrer_id"] = ref_code
        profile["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        owner = referrals.setdefault(ref_code, {})
        invited = owner.setdefault("invited", [])
        if new_chat_id not in invited:
            invited.append(new_chat_id)

        save_json("referrals.json", referrals)

    return True


def referral_info(chat_id):
    chat_id = str(chat_id)
    code = referral_code(chat_id)
    username = bot_username()
    ref_link = f"https://t.me/{username}?start=ref_{code}" if username else f"/start ref_{code}"
    count = len(referrals.get(chat_id, {}).get("invited", []))

    text = messages.get("referral_text", MESSAGE_DEFAULTS["referral_text"])
    text = text.replace("{ref_link}", ref_link).replace("{count}", str(count)).replace("{code}", code)
    return messages.get("referral_title", MESSAGE_DEFAULTS["referral_title"]) + "\n\n" + text


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
            "referrer_id": referrals.get(str(chat_id), {}).get("referrer_id", ""),
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
                            "🧩 Custom Emoji ID:\n\n" + "\n".join(custom_emoji_ids)
                        )
                        continue

                    if text.startswith("/start"):
                        parts = text.split(maxsplit=1)
                        if len(parts) == 2 and parts[1].startswith("ref_"):
                            if register_referral(chat_id, parts[1]):
                                send(chat_id, messages.get("referral_registered", MESSAGE_DEFAULTS["referral_registered"]))
                        menu(chat_id)

                    elif text == "/siparislerim":
                        my_orders(chat_id)

                    elif text in ["/referans", "/ref"]:
                        send(chat_id, referral_info(chat_id))

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
                            ok_min, min_error = check_min_amount(s.get("type"), text)
                            if not ok_min:
                                send(chat_id, min_error)
                                continue

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
                        