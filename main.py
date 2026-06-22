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
    emoji = c.get("emoji", "🪙")
    name = c.get("name", symbol)
    return f"{emoji} {name} ({symbol})"


def menu(chat_id):
    send(
        chat_id,
        messages.get(
            "welcome",
            "👋 Zaqel Swap'a hoş geldiniz."
        ),
        {
            "inline_keyboard": [
                [{"text": "🔄 Swap Başlat", "callback_data": "swap"}],
                [{"text": "📦 Siparişlerim", "callback_data": "orders"}],
                [{"text": "💰 Komisyonlar", "callback_data": "fees"}],
                [{"text": "ℹ️ Nasıl Çalışır?", "callback_data": "help"}],
                [{"text": "📞 Destek", "callback_data": "support"}],
            ]
        },
    )


def swap_menu(chat_id):
    send(
        chat_id,
        messages.get("swap_menu", "🔄 İşlem türünü seçiniz:"),
        {
            "inline_keyboard": [
                [{"text": "🏦 IBAN → Kripto", "callback_data": "type_iban_to_crypto"}],
                [{"text": "💳 Kripto → IBAN", "callback_data": "type_crypto_to_iban"}],
                [{"text": "🔄 Kripto → Kripto", "callback_data": "type_crypto_to_crypto"}],
                [{"text": "⬅️ Ana Menü", "callback_data": "main"}],
            ]
        },
    )


def coin_menu(chat_id, prefix, exclude=None, message_text="Coin seçiniz:"):
    rows = []
    for symbol in active_coins():
        if symbol != exclude:
            rows.append(
                [{
                    "text": coin_label(symbol),
                    "callback_data": f"{prefix}_{symbol}",
                }]
            )

    rows.append([{"text": "⬅️ Geri", "callback_data": "swap"}])
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
        send(chat_id, "📦 Siparişlerin:\n\n" + "\n".join(found))
    else:
        send(chat_id, "📦 Henüz siparişin yok.")


def update_order_status(oid, new_status):
    oid = str(oid)
    with data_lock:
        order = orders.get(oid)
        if not order:
            return False, "Sipariş bulunamadı."

        if new_status == "completed":
            order["status"] = "✅ Tamamlandı"
            order["completed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_message = messages.get(
                "order_completed",
                "✅ Siparişiniz tamamlandı."
            )
        elif new_status == "rejected":
            order["status"] = "❌ Reddedildi"
            order["rejected_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            user_message = messages.get(
                "order_rejected",
                "❌ Siparişiniz reddedildi."
            )
        else:
            return False, "Geçersiz durum."

        save_json("orders.json", orders)

    send(order.get("chat_id"), f"{user_message}\n\nSipariş No: #{oid}")
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
                                "💰 Komisyonlar:\n\n"
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
                            send(chat_id, "❌ Şu anda IBAN ile ödeme kapalıdır.")
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
                            send(chat_id, "❌ İşlem süresi doldu. Lütfen tekrar başlayın.")
                            continue

                        s["from_coin"] = coin

                        if s["type"] == "crypto_to_crypto":
                            coin_menu(
                                chat_id,
                                "to",
                                exclude=coin,
                                message_text=messages.get(
                                    "coin_select_crypto_to_crypto",
                                    "🔄 Alacağınız kripto para birimini seçiniz."
                                ),
                            )
                        else:
                            s["step"] = "amount"
                            send(
                                chat_id,
                                messages.get(
                                    "amount_question_crypto_to_iban",
                                    "💰 Kripto miktarını giriniz:"
                                ),
                            )

                    elif data.startswith("to_"):
                        coin = data.replace("to_", "")
                        s = user_state.get(chat_id)
                        if not s:
                            send(chat_id, "❌ İşlem süresi doldu. Lütfen tekrar başlayın.")
                            continue

                        s["to_coin"] = coin
                        s["step"] = "amount"

                        if s["type"] == "iban_to_crypto":
                            send(
                                chat_id,
                                messages.get(
                                    "amount_question_iban_to_crypto",
                                    "💰 TL tutarını giriniz:"
                                ),
                            )
                        elif s["type"] == "crypto_to_crypto":
                            send(
                                chat_id,
                                messages.get(
                                    "amount_question_crypto_to_crypto",
                                    "💰 Miktarı giriniz:"
                                ),
                            )

            time.sleep(1)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(5)


def logged_in():
    return session.get("login") is True


def h(value):
    return escape(str(value if value is not None else ""), quote=True)


@app.route("/")
def home():
    return "Zaqel Bot aktif ✅"


@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""

    if request.method == "POST":
        if (
            request.form.get("username") == PANEL_USERNAME
            and request.form.get("password") == PANEL_PASSWORD
        ):
            session["login"] = True
            return redirect("/admin")
        error = "Hatalı giriş"

    return f"""
    <!doctype html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Zaqel Admin Giriş</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background: #0b0d12;
                color: white;
                display: grid;
                place-items: center;
                min-height: 100vh;
                margin: 0;
            }}
            .login-box {{
                width: min(420px, calc(100% - 40px));
                background: #151922;
                border: 1px solid #2a3040;
                padding: 28px;
                border-radius: 18px;
            }}
            input {{
                width: 100%;
                box-sizing: border-box;
                padding: 12px;
                margin-top: 7px;
                background: #0f131b;
                color: white;
                border: 1px solid #343b4e;
                border-radius: 10px;
            }}
            button {{
                width: 100%;
                padding: 12px;
                margin-top: 18px;
                border: 0;
                border-radius: 10px;
                background: #ef3340;
                color: white;
                font-weight: bold;
                cursor: pointer;
            }}
            .error {{ color: #ff6b73; }}
        </style>
    </head>
    <body>
        <div class="login-box">
            <h1>🔐 Zaqel Admin</h1>
            <form method="post">
                <label>Kullanıcı adı</label>
                <input name="username" autocomplete="username" required>
                <br><br>
                <label>Şifre</label>
                <input name="password" type="password" autocomplete="current-password" required>
                <button type="submit">Giriş Yap</button>
            </form>
            <p class="error">{h(error)}</p>
        </div>
    </body>
    </html>
    """


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not logged_in():
        return redirect("/login")

    if request.method == "POST":
        action = request.form.get("action")

        if action == "settings":
            for key in list(settings.keys()):
                settings[key] = request.form.get(key, "")

            for key in list(messages.keys()):
                messages[key] = request.form.get(key, "")

        elif action == "add_coin":
            symbol = request.form.get("symbol", "").upper().strip()
            if symbol:
                coins[symbol] = {
                    "name": request.form.get("name", ""),
                    "emoji": request.form.get("emoji", "🪙"),
                    "network": request.form.get("network", ""),
                    "address": request.form.get("address", ""),
                    "logo": request.form.get("logo", ""),
                    "active": request.form.get("active", "on"),
                }

        elif action == "update_coins":
            for symbol in list(coins.keys()):
                coins[symbol]["name"] = request.form.get(
                    f"name_{symbol}", coins[symbol].get("name", "")
                )
                coins[symbol]["emoji"] = request.form.get(
                    f"emoji_{symbol}", coins[symbol].get("emoji", "🪙")
                )
                coins[symbol]["network"] = request.form.get(
                    f"network_{symbol}", coins[symbol].get("network", "")
                )
                coins[symbol]["address"] = request.form.get(
                    f"address_{symbol}", coins[symbol].get("address", "")
                )
                coins[symbol]["logo"] = request.form.get(
                    f"logo_{symbol}", coins[symbol].get("logo", "")
                )
                coins[symbol]["active"] = request.form.get(
                    f"active_{symbol}", "off"
                )

        elif action == "complete_order":
            update_order_status(request.form.get("order_id", ""), "completed")

        elif action == "reject_order":
            update_order_status(request.form.get("order_id", ""), "rejected")

        save_json("settings.json", settings)
        save_json("messages.json", messages)
        save_json("coins.json", coins)
        save_json("orders.json", orders)
        return redirect("/admin")

    coin_rows = ""
    for symbol, c in coins.items():
        checked = "checked" if c.get("active") == "on" else ""
        coin_rows += f"""
        <tr>
            <td><strong>{h(symbol)}</strong></td>
            <td><input name="emoji_{h(symbol)}" value="{h(c.get('emoji', ''))}" class="small"></td>
            <td><input name="name_{h(symbol)}" value="{h(c.get('name', ''))}"></td>
            <td><input name="network_{h(symbol)}" value="{h(c.get('network', ''))}"></td>
            <td><input name="address_{h(symbol)}" value="{h(c.get('address', ''))}"></td>
            <td><input name="logo_{h(symbol)}" value="{h(c.get('logo', ''))}"></td>
            <td><input type="checkbox" name="active_{h(symbol)}" value="on" {checked}></td>
        </tr>
        """

    order_cards = ""
    sorted_orders = sorted(
        orders.items(),
        key=lambda item: item[1].get("created_at", ""),
        reverse=True,
    )

    for oid, o in sorted_orders:
        status = o.get("status", "Bilinmiyor")
        is_pending = status == "⏳ Bekliyor"

        details = [
            ("Sipariş No", f"#{oid}"),
            ("Kullanıcı", f"@{o.get('username', 'unknown')}"),
            ("Telegram ID", o.get("chat_id", "")),
            ("Tür", order_type_name(o.get("type"))),
            ("Miktar", o.get("amount", "")),
            ("Gönderilen Coin", o.get("from_coin", "-")),
            ("Alınacak Coin", o.get("to_coin", "-")),
            ("Cüzdan", o.get("wallet", "-")),
            ("IBAN", o.get("iban", "-")),
            ("Ad Soyad", o.get("name", "-")),
            ("Oluşturulma", o.get("created_at", "-")),
            ("Durum", status),
        ]

        detail_html = "".join(
            f"<div class='detail'><span>{h(label)}</span><strong>{h(value)}</strong></div>"
            for label, value in details
        )

        buttons = ""
        if is_pending:
            buttons = f"""
            <div class="actions">
                <form method="post" onsubmit="return confirm('Bu sipariş tamamlandı olarak işaretlensin mi?')">
                    <input type="hidden" name="action" value="complete_order">
                    <input type="hidden" name="order_id" value="{h(oid)}">
                    <button class="complete" type="submit">✅ Tamamla</button>
                </form>
                <form method="post" onsubmit="return confirm('Bu sipariş reddedilsin mi?')">
                    <input type="hidden" name="action" value="reject_order">
                    <input type="hidden" name="order_id" value="{h(oid)}">
                    <button class="reject" type="submit">❌ Reddet</button>
                </form>
            </div>
            """

        order_cards += f"""
        <article class="order-card">
            <div class="order-head">
                <h3>#{h(oid)}</h3>
                <span class="status">{h(status)}</span>
            </div>
            <div class="details">{detail_html}</div>
            {buttons}
        </article>
        """

    if not order_cards:
        order_cards = "<p>Henüz sipariş bulunmuyor.</p>"

    message_fields = [
        ("welcome", "Hoş geldin mesajı"),
        ("swap_menu", "İşlem türü seçim mesajı"),
        ("coin_select_crypto_to_crypto", "Kripto → Kripto coin seçim mesajı"),
        ("coin_select_iban_to_crypto", "IBAN → Kripto coin seçim mesajı"),
        ("coin_select_crypto_to_iban", "Kripto → IBAN coin seçim mesajı"),
        ("amount_question_crypto_to_crypto", "Kripto → Kripto miktar sorusu"),
        ("amount_question_iban_to_crypto", "IBAN → Kripto miktar sorusu"),
        ("amount_question_crypto_to_iban", "Kripto → IBAN miktar sorusu"),
        ("wallet_question", "Cüzdan adresi sorusu"),
        ("iban_question", "IBAN sorusu"),
        ("name_question", "Ad soyad sorusu"),
        ("order_created", "Sipariş oluşturuldu mesajı"),
        ("order_completed", "Sipariş tamamlandı mesajı"),
        ("order_rejected", "Sipariş reddedildi mesajı"),
        ("help", "Nasıl çalışır mesajı"),
        ("support", "Destek mesajı"),
        ("iban_warning", "IBAN uyarı mesajı"),
        ("working_hours", "Çalışma saatleri"),
    ]

    message_inputs = ""
    for key, label in message_fields:
        value = messages.get(key, "")
        if key == "working_hours":
            message_inputs += (
                f"<label>{h(label)}</label>"
                f"<input name='{h(key)}' value='{h(value)}'>"
            )
        else:
            message_inputs += (
                f"<label>{h(label)}</label>"
                f"<textarea name='{h(key)}'>{h(value)}</textarea>"
            )

    return f"""
    <!doctype html>
    <html lang="tr">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width,initial-scale=1">
        <title>Zaqel Admin</title>
        <style>
            :root {{
                color-scheme: dark;
                --bg: #0b0d12;
                --panel: #151922;
                --panel-2: #0f131b;
                --border: #2a3040;
                --text: #f4f7fb;
                --muted: #98a2b3;
                --red: #ef3340;
                --green: #25b56a;
            }}
            * {{ box-sizing: border-box; }}
            body {{
                margin: 0;
                font-family: Arial, sans-serif;
                background: var(--bg);
                color: var(--text);
            }}
            .container {{
                width: min(1280px, calc(100% - 28px));
                margin: 0 auto;
                padding: 24px 0 60px;
            }}
            .topbar {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-bottom: 22px;
            }}
            a {{ color: #ff6872; }}
            .box {{
                background: var(--panel);
                border: 1px solid var(--border);
                border-radius: 16px;
                padding: 20px;
                margin-bottom: 20px;
            }}
            h1, h2, h3 {{ margin-top: 0; }}
            label {{
                display: block;
                color: var(--muted);
                margin: 14px 0 7px;
            }}
            input, textarea {{
                width: 100%;
                background: var(--panel-2);
                color: white;
                border: 1px solid #343b4e;
                border-radius: 9px;
                padding: 10px;
            }}
            textarea {{
                min-height: 78px;
                resize: vertical;
            }}
            button {{
                border: 0;
                border-radius: 9px;
                padding: 10px 16px;
                color: white;
                font-weight: bold;
                cursor: pointer;
                background: var(--red);
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                min-width: 920px;
            }}
            th, td {{
                border-bottom: 1px solid var(--border);
                padding: 10px;
                text-align: left;
                vertical-align: middle;
            }}
            .table-wrap {{ overflow-x: auto; }}
            .small {{ min-width: 70px; }}
            .order-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
                gap: 16px;
            }}
            .order-card {{
                background: var(--panel-2);
                border: 1px solid var(--border);
                border-radius: 14px;
                padding: 16px;
            }}
            .order-head {{
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 12px;
                border-bottom: 1px solid var(--border);
                padding-bottom: 12px;
                margin-bottom: 12px;
            }}
            .order-head h3 {{ margin: 0; }}
            .status {{
                font-size: 14px;
                color: #d5d9e2;
            }}
            .details {{
                display: grid;
                gap: 8px;
            }}
            .detail {{
                display: flex;
                justify-content: space-between;
                gap: 12px;
                padding: 7px 0;
                border-bottom: 1px dashed #262c39;
            }}
            .detail span {{ color: var(--muted); }}
            .detail strong {{
                max-width: 62%;
                text-align: right;
                overflow-wrap: anywhere;
            }}
            .actions {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 10px;
                margin-top: 16px;
            }}
            .actions form {{ margin: 0; }}
            .actions button {{ width: 100%; }}
            .complete {{ background: var(--green); }}
            .reject {{ background: var(--red); }}
            .save {{ margin-top: 18px; }}
            @media (max-width: 650px) {{
                .container {{ width: min(100% - 18px, 1280px); }}
                .topbar {{ align-items: flex-start; }}
                .box {{ padding: 15px; border-radius: 12px; }}
                .detail {{ display: block; }}
                .detail strong {{
                    display: block;
                    max-width: 100%;
                    text-align: left;
                    margin-top: 4px;
                }}
            }}
        </style>
    </head>
    <body>
        <main class="container">
            <div class="topbar">
                <div>
                    <h1>⚙️ Zaqel Admin Panel</h1>
                    <div style="color:var(--muted)">Bot ve sipariş kontrol alanı</div>
                </div>
                <a href="/logout">Çıkış</a>
            </div>

            <section class="box">
                <h2>📦 Sipariş Kontrol Alanı</h2>
                <div class="order-grid">{order_cards}</div>
            </section>

            <form method="post">
                <input type="hidden" name="action" value="settings">

                <section class="box">
                    <h2>📝 Bot Mesajları</h2>
                    {message_inputs}
                </section>

                <section class="box">
                    <h2>💰 Komisyon Yönetimi</h2>
                    <label>Kripto → Kripto %</label>
                    <input name="fee_crypto_to_crypto" value="{h(settings.get('fee_crypto_to_crypto', ''))}">
                    <label>IBAN → Kripto %</label>
                    <input name="fee_iban_to_crypto" value="{h(settings.get('fee_iban_to_crypto', ''))}">
                    <label>Kripto → IBAN %</label>
                    <input name="fee_crypto_to_iban" value="{h(settings.get('fee_crypto_to_iban', ''))}">
                </section>

                <section class="box">
                    <h2>📉 Minimum Ödeme Yönetimi</h2>
                    <label>Min Kripto → Kripto TL</label>
                    <input name="min_crypto_to_crypto" value="{h(settings.get('min_crypto_to_crypto', ''))}">
                    <label>Min IBAN → Kripto TL</label>
                    <input name="min_iban_to_crypto" value="{h(settings.get('min_iban_to_crypto', ''))}">
                    <label>Min Kripto → IBAN TL</label>
                    <input name="min_crypto_to_iban" value="{h(settings.get('min_crypto_to_iban', ''))}">
                </section>

                <section class="box">
                    <h2>🏦 IBAN Yönetimi</h2>
                    <label>Banka adı</label>
                    <input name="bank_name" value="{h(settings.get('bank_name', ''))}">
                    <label>IBAN</label>
                    <input name="iban" value="{h(settings.get('iban', ''))}">
                    <label>Alıcı adı soyadı</label>
                    <input name="iban_owner" value="{h(settings.get('iban_owner', ''))}">
                    <label>IBAN aktifliği: açık için on, kapalı için off</label>
                    <input name="iban_active" value="{h(settings.get('iban_active', 'on'))}">
                </section>

                <button class="save" type="submit">Genel Ayarları Kaydet</button>
            </form>

            <section class="box">
                <h2>🪙 Coin Yönetimi</h2>
                <form method="post">
                    <input type="hidden" name="action" value="update_coins">
                    <div class="table-wrap">
                        <table>
                            <tr>
                                <th>Sembol</th>
                                <th>Emoji</th>
                                <th>Ad</th>
                                <th>Ağ</th>
                                <th>Ödeme Adresi</th>
                                <th>Logo URL</th>
                                <th>Aktif</th>
                            </tr>
                            {coin_rows}
                        </table>
                    </div>
                    <br>
                    <button type="submit">Coinleri Kaydet</button>
                </form>
            </section>

            <section class="box">
                <h2>➕ Yeni Coin Ekle</h2>
                <form method="post">
                    <input type="hidden" name="action" value="add_coin">
                    <label>Sembol</label>
                    <input name="symbol" placeholder="BTC" required>
                    <label>Ad</label>
                    <input name="name" placeholder="Bitcoin">
                    <label>Emoji/Renk</label>
                    <input name="emoji" placeholder="🟠">
                    <label>Ağ</label>
                    <input name="network" placeholder="BTC / BEP20 / ERC20">
                    <label>Ödeme Adresi</label>
                    <input name="address">
                    <label>Logo URL</label>
                    <input name="logo">
                    <label>Aktif için on yaz</label>
                    <input name="active" value="on">
                    <br><br>
                    <button type="submit">Coin Ekle</button>
                </form>
            </section>
        </main>
    </body>
    </html>
    """


if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=PORT)
