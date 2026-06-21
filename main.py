import os, time, random, requests, threading
from flask import Flask, request, redirect, session

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
PANEL_USERNAME = os.getenv("PANEL_USERNAME", "dembele00")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "babako06")
PORT = int(os.getenv("PORT", "8080"))
OFFSET = None

app = Flask(__name__)
app.secret_key = "zaqel-panel-secret"

user_state = {}
orders = {}

settings = {
    "fee_crypto_to_crypto": os.getenv("FEE_CRYPTO_TO_CRYPTO", "1"),
    "fee_iban_to_crypto": os.getenv("FEE_IBAN_TO_CRYPTO", "3"),
    "fee_crypto_to_iban": os.getenv("FEE_CRYPTO_TO_IBAN", "2"),

    "min_crypto_to_crypto": os.getenv("MIN_CRYPTO_TO_CRYPTO", "100"),
    "min_iban_to_crypto": os.getenv("MIN_IBAN_TO_CRYPTO", "100"),
    "min_crypto_to_iban": os.getenv("MIN_CRYPTO_TO_IBAN", "100"),

    "support": "📞 Destek için admin ile iletişime geç.",
    "working_hours": "09:00 - 23:59",

    "trx_address": "",
    "ltc_address": "",
    "usdt_address": "",

    "bank_name": "",
    "iban": "",
    "iban_owner": "",
    "iban_active": "on",

    "iban_warning": "⚠️ Verilen IBAN numarasına para gönderen kişinin TC Kimlik numarasını açıklama kısmında belirtmesi zorunludur. Aksi takdirde dönüşüm işlemi gerçekleştirilmeyecektir.",
}

COINS = {
    "TRX": "🔴 TRON (TRX)",
    "LTC": "⚪ Litecoin (LTC)",
    "USDT": "🔵 USDT (TRC20)",
}

def api(method, data):
    return requests.post(f"https://api.telegram.org/bot{TOKEN}/{method}", json=data).json()

def send(chat_id, text, keyboard=None):
    data = {"chat_id": chat_id, "text": text}
    if keyboard:
        data["reply_markup"] = keyboard
    return api("sendMessage", data)

def answer(cb_id):
    api("answerCallbackQuery", {"callback_query_id": cb_id})

def menu(chat_id):
    send(chat_id, "👋 Zaqel Swap'a hoş geldiniz.\n\nGüvenli, hızlı ve manuel onaylı takas platformu.", {
        "inline_keyboard": [
            [{"text": "🔄 Swap Başlat", "callback_data": "swap"}],
            [{"text": "📦 Siparişlerim", "callback_data": "orders"}],
            [{"text": "💰 Komisyonlar", "callback_data": "fees"}],
            [{"text": "ℹ️ Nasıl Çalışır?", "callback_data": "help"}],
            [{"text": "📞 Destek", "callback_data": "support"}],
        ]
    })

def swap_menu(chat_id):
    send(chat_id, "🔄 İşlem türünü seçiniz:", {
        "inline_keyboard": [
            [{"text": "🏦 IBAN → Kripto", "callback_data": "type_iban_to_crypto"}],
            [{"text": "💳 Kripto → IBAN", "callback_data": "type_crypto_to_iban"}],
            [{"text": "🔄 Kripto → Kripto", "callback_data": "type_crypto_to_crypto"}],
            [{"text": "⬅️ Ana Menü", "callback_data": "main"}],
        ]
    })

def coin_menu(chat_id, prefix, exclude=None):
    rows = []
    for c, label in COINS.items():
        if c != exclude:
            rows.append([{"text": label, "callback_data": f"{prefix}_{c}"}])
    rows.append([{"text": "⬅️ Geri", "callback_data": "swap"}])
    send(chat_id, "Coin seçiniz:", {"inline_keyboard": rows})

def create_order(chat_id, username):
    s = user_state[chat_id]
    oid = random.randint(10000, 99999)

    orders[oid] = {
        "chat_id": chat_id,
        "username": username,
        **s,
        "status": "⏳ Bekliyor"
    }

    type_name = {
        "crypto_to_crypto": "🔄 Kripto → Kripto",
        "iban_to_crypto": "🏦 IBAN → Kripto",
        "crypto_to_iban": "💳 Kripto → IBAN",
    }[s["type"]]

    fee = {
        "crypto_to_crypto": settings["fee_crypto_to_crypto"],
        "iban_to_crypto": settings["fee_iban_to_crypto"],
        "crypto_to_iban": settings["fee_crypto_to_iban"],
    }[s["type"]]

    min_amount = {
        "crypto_to_crypto": settings["min_crypto_to_crypto"],
        "iban_to_crypto": settings["min_iban_to_crypto"],
        "crypto_to_iban": settings["min_crypto_to_iban"],
    }[s["type"]]

    text = f"📄 Sipariş Özeti\n\nNo: #{oid}\nTür: {type_name}\nKomisyon: %{fee}\nMinimum İşlem: {min_amount} TL\n"

    if s["type"] == "crypto_to_crypto":
        text += f"\nGönderilen: {s['amount']} {s['from_coin']}\nAlınacak: {s['to_coin']}\nAlıcı adres:\n{s['wallet']}\n"

    elif s["type"] == "iban_to_crypto":
        text += f"\nÖdenecek TL: {s['amount']} TL\nAlınacak: {s['to_coin']}\nAlıcı adres:\n{s['wallet']}\n\n"
        text += f"🏦 Ödeme IBAN:\nBanka: {settings['bank_name']}\nIBAN: {settings['iban']}\nAlıcı: {settings['iban_owner']}\n"
        text += f"\n{settings['iban_warning']}\n"

    elif s["type"] == "crypto_to_iban":
        text += f"\nGönderilen: {s['amount']} {s['from_coin']}\nIBAN:\n{s['iban']}\nAd Soyad: {s['name']}\n"

    text += "\nDurum: ⏳ Admin onayı bekleniyor"

    send(chat_id, text)

    if ADMIN_CHAT_ID:
        send(ADMIN_CHAT_ID, f"🚨 Yeni Sipariş\n\nKullanıcı: @{username}\n{text}\n\nTamamlamak için:\n/tamamla {oid}")

    user_state.pop(chat_id, None)

def my_orders(chat_id):
    found = [f"#{oid} — {o['status']}" for oid, o in orders.items() if o["chat_id"] == chat_id]
    send(chat_id, "📦 Siparişlerin:\n\n" + "\n".join(found) if found else "📦 Henüz siparişin yok.")

def bot_loop():
    global OFFSET
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
                        menu(chat_id)

                    elif text == "/siparislerim":
                        my_orders(chat_id)

                    elif text.startswith("/tamamla") and str(chat_id) == str(ADMIN_CHAT_ID):
                        parts = text.split()
                        if len(parts) >= 2 and int(parts[1]) in orders:
                            oid = int(parts[1])
                            orders[oid]["status"] = "✅ Tamamlandı"
                            send(orders[oid]["chat_id"], f"✅ Siparişin tamamlandı.\n\nSipariş No: #{oid}")
                            send(chat_id, "✅ Sipariş tamamlandı.")
                        else:
                            send(chat_id, "❌ Sipariş bulunamadı.")

                    elif chat_id in user_state:
                        s = user_state[chat_id]
                        step = s.get("step")

                        if step == "amount":
                            s["amount"] = text
                            if s["type"] in ["crypto_to_crypto", "iban_to_crypto"]:
                                s["step"] = "wallet"
                                send(chat_id, "📥 Alacağın coin için cüzdan adresini gir:")
                            else:
                                s["step"] = "iban"
                                send(chat_id, "🏦 IBAN adresini gir:")

                        elif step == "wallet":
                            s["wallet"] = text
                            create_order(chat_id, username)

                        elif step == "iban":
                            s["iban"] = text
                            s["step"] = "name"
                            send(chat_id, "👤 IBAN sahibinin ad soyad bilgisini gir:")

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
                        send(chat_id, f"💰 Komisyonlar:\n\n🔄 Kripto → Kripto: %{settings['fee_crypto_to_crypto']}\n🏦 IBAN → Kripto: %{settings['fee_iban_to_crypto']}\n💳 Kripto → IBAN: %{settings['fee_crypto_to_iban']}")
                    elif data == "help":
                        send(chat_id, f"ℹ️ Nasıl çalışır?\n\n1. İşlem türünü seç.\n2. Bilgileri gir.\n3. Sipariş oluşturulur.\n4. Admin manuel olarak işlemi tamamlar.\n\nÇalışma saatleri: {settings['working_hours']}")
                    elif data == "support":
                        send(chat_id, settings["support"])

                    elif data == "type_crypto_to_crypto":
                        user_state[chat_id] = {"type": "crypto_to_crypto"}
                        coin_menu(chat_id, "from")
                    elif data == "type_iban_to_crypto":
                        if settings["iban_active"] != "on":
                            send(chat_id, "❌ Şu anda IBAN ile ödeme geçici olarak kapalıdır.")
                        else:
                            user_state[chat_id] = {"type": "iban_to_crypto"}
                            coin_menu(chat_id, "to")
                    elif data == "type_crypto_to_iban":
                        user_state[chat_id] = {"type": "crypto_to_iban"}
                        coin_menu(chat_id, "from")

                    elif data.startswith("from_"):
                        coin = data.replace("from_", "")
                        s = user_state[chat_id]
                        s["from_coin"] = coin
                        if s["type"] == "crypto_to_crypto":
                            coin_menu(chat_id, "to", exclude=coin)
                        else:
                            s["step"] = "amount"
                            send(chat_id, "💰 Göndereceğin miktarı gir:")

                    elif data.startswith("to_"):
                        coin = data.replace("to_", "")
                        s = user_state[chat_id]
                        s["to_coin"] = coin
                        s["step"] = "amount"
                        send(chat_id, "💰 Miktarı gir:")

            time.sleep(1)

        except Exception as e:
            print("ERROR:", e)
            time.sleep(5)

def logged_in():
    return session.get("login") == True

@app.route("/")
def home():
    return "Zaqel Bot aktif ✅"

@app.route("/login", methods=["GET", "POST"])
def login():
    error = ""
    if request.method == "POST":
        if request.form.get("username") == PANEL_USERNAME and request.form.get("password") == PANEL_PASSWORD:
            session["login"] = True
            return redirect("/admin")
        error = "Hatalı giriş"

    return f"""
    <html><body style="font-family:Arial;background:#111;color:white;padding:40px">
    <h1>🔐 Zaqel Admin Giriş</h1>
    <form method="post">
    Kullanıcı adı<br><input name="username"><br><br>
    Şifre<br><input name="password" type="password"><br><br>
    <button>Giriş Yap</button>
    </form>
    <p style="color:red">{error}</p>
    </body></html>
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
        for k in settings.keys():
            settings[k] = request.form.get(k, "")
        return redirect("/admin")

    order_rows = ""
    for oid, o in orders.items():
        order_rows += f"<tr><td>#{oid}</td><td>@{o.get('username')}</td><td>{o.get('type')}</td><td>{o.get('status')}</td></tr>"

    return f"""
    <html>
    <head>
    <title>Zaqel Admin</title>
    <style>
    body {{ font-family: Arial; background:#0f0f0f; color:white; padding:25px; }}
    input, textarea {{ background:#1e1e1e; color:white; border:1px solid #444; padding:8px; width:420px; }}
    textarea {{ height:80px; }}
    button {{ padding:10px 20px; background:#ff3333; color:white; border:0; cursor:pointer; }}
    .box {{ background:#181818; padding:20px; margin-bottom:20px; border-radius:10px; }}
    a {{ color:#ff5555; }}
    table {{ border-collapse:collapse; width:100%; }}
    td, th {{ border:1px solid #444; padding:8px; }}
    </style>
    </head>
    <body>
    <h1>⚙️ Zaqel Admin Panel</h1>
    <a href="/logout">Çıkış</a>

    <form method="post">

    <div class="box">
    <h2>💰 Komisyon Yönetimi</h2>
    Kripto → Kripto %<br><input name="fee_crypto_to_crypto" value="{settings['fee_crypto_to_crypto']}"><br><br>
    IBAN → Kripto %<br><input name="fee_iban_to_crypto" value="{settings['fee_iban_to_crypto']}"><br><br>
    Kripto → IBAN %<br><input name="fee_crypto_to_iban" value="{settings['fee_crypto_to_iban']}"><br><br>
    </div>

    <div class="box">
    <h2>📉 Minimum Ödeme Yönetimi</h2>
    Min Kripto → Kripto TL<br><input name="min_crypto_to_crypto" value="{settings['min_crypto_to_crypto']}"><br><br>
    Min IBAN → Kripto TL<br><input name="min_iban_to_crypto" value="{settings['min_iban_to_crypto']}"><br><br>
    Min Kripto → IBAN TL<br><input name="min_crypto_to_iban" value="{settings['min_crypto_to_iban']}"><br><br>
    </div>

    <div class="box">
    <h2>🏦 IBAN Yönetimi</h2>
    Banka adı<br><input name="bank_name" value="{settings['bank_name']}"><br><br>
    IBAN<br><input name="iban" value="{settings['iban']}"><br><br>
    Alıcı adı soyadı<br><input name="iban_owner" value="{settings['iban_owner']}"><br><br>
    IBAN aktif için 'on', kapalı için 'off'<br><input name="iban_active" value="{settings['iban_active']}"><br><br>
    IBAN uyarı mesajı<br><textarea name="iban_warning">{settings['iban_warning']}</textarea><br><br>
    </div>

    <div class="box">
    <h2>🪙 Kripto Adresleri</h2>
    TRX Adresi<br><input name="trx_address" value="{settings['trx_address']}"><br><br>
    LTC Adresi<br><input name="ltc_address" value="{settings['ltc_address']}"><br><br>
    USDT TRC20 Adresi<br><input name="usdt_address" value="{settings['usdt_address']}"><br><br>
    </div>

    <div class="box">
    <h2>⚙️ Genel Ayarlar</h2>
    Destek mesajı<br><textarea name="support">{settings['support']}</textarea><br><br>
    Çalışma saatleri<br><input name="working_hours" value="{settings['working_hours']}"><br><br>
    </div>

    <button>Kaydet</button>
    </form>

    <div class="box">
    <h2>📦 Siparişler</h2>
    <table>
    <tr><th>No</th><th>Kullanıcı</th><th>Tür</th><th>Durum</th></tr>
    {order_rows}
    </table>
    </div>

    </body></html>
    """

threading.Thread(target=bot_loop, daemon=True).start()
app.run(host="0.0.0.0", port=PORT)
