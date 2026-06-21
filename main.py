import os, time, random, json, requests

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

FEES = {
    "crypto_to_crypto": os.getenv("FEE_CRYPTO_TO_CRYPTO", "1"),
    "iban_to_crypto": os.getenv("FEE_IBAN_TO_CRYPTO", "3"),
    "crypto_to_iban": os.getenv("FEE_CRYPTO_TO_IBAN", "2"),
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
        "status": "⏳ Admin onayı bekleniyor"
    }

    typetext = {
        "crypto_to_crypto": "🔄 Kripto → Kripto",
        "iban_to_crypto": "🏦 IBAN → Kripto",
        "crypto_to_iban": "💳 Kripto → IBAN",
    }[s["type"]]

    user_text = f"📄 Sipariş Özeti\n\nSipariş No: #{oid}\nTür: {typetext}\n"

    if s["type"] == "crypto_to_crypto":
        user_text += f"Gönderilen: {s['amount']} {s['from_coin']}\nAlınacak: {s['to_coin']}\nAlıcı Adresi:\n{s['wallet']}\n"

    elif s["type"] == "iban_to_crypto":
        user_text += f"IBAN Tutarı: {s['amount']} TL\nAlınacak Coin: {s['to_coin']}\nAlıcı Adresi:\n{s['wallet']}\n"

    elif s["type"] == "crypto_to_iban":
        user_text += f"Gönderilen Coin: {s['from_coin']}\nMiktar: {s['amount']}\nIBAN:\n{s['iban']}\nAd Soyad: {s['name']}\n"

    user_text += f"\nKomisyon: %{FEES[s['type']]}\nDurum: ⏳ Admin onayı bekleniyor"

    admin_text = f"🚨 Yeni Sipariş\n\nNo: #{oid}\nKullanıcı: @{username}\n{user_text}"

    send(chat_id, user_text)
    if ADMIN_CHAT_ID:
        send(ADMIN_CHAT_ID, admin_text + f"\n\nTamamlamak için:\n/tamamla {oid}")
    user_state.pop(chat_id, None)

def my_orders(chat_id):
    found = []
    for oid, o in orders.items():
        if o["chat_id"] == chat_id:
            found.append(f"#{oid} — {o['status']}")

    send(chat_id, "📦 Siparişlerin:\n\n" + "\n".join(found) if found else "📦 Henüz siparişin yok.")

def complete_order(order_id):
    if order_id not in orders:
        return False

    orders[order_id]["status"] = "✅ Tamamlandı"
    send(orders[order_id]["chat_id"], f"✅ Siparişin tamamlandı.\n\nSipariş No: #{order_id}")
    return True

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
                    if len(parts) < 2:
                        send(chat_id, "Kullanım: /tamamla <sipariş_no>")
                    else:
                        try:
                            oid = int(parts[1])
                            send(chat_id, "✅ Sipariş tamamlandı." if complete_order(oid) else "❌ Sipariş bulunamadı.")
                        except:
                            send(chat_id, "❌ Geçersiz sipariş no.")

                elif chat_id in user_state:
                    s = user_state[chat_id]
                    step = s.get("step")

                    if step == "amount":
                        s["amount"] = text

                        if s["type"] in ["crypto_to_crypto", "iban_to_crypto"]:
                            s["step"] = "wallet"
                            send(chat_id, "📥 Alacağın coin için cüzdan adresini gir:")
                        elif s["type"] == "crypto_to_iban":
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
                    send(chat_id, f"💰 Komisyonlar:\n\n🔄 Kripto → Kripto: %{FEES['crypto_to_crypto']}\n🏦 IBAN → Kripto: %{FEES['iban_to_crypto']}\n💳 Kripto → IBAN: %{FEES['crypto_to_iban']}")

                elif data == "help":
                    send(chat_id, "ℹ️ Nasıl çalışır?\n\n1. İşlem türünü seç.\n2. Coin ve miktar bilgilerini gir.\n3. Sipariş oluşur.\n4. Admin manuel olarak işlemi tamamlar.")

                elif data == "support":
                    send(chat_id, "📞 Destek için admin ile iletişime geç.")

                elif data == "type_crypto_to_crypto":
                    user_state[chat_id] = {"type": "crypto_to_crypto"}
                    send(chat_id, "📤 Göndereceğin coini seç:")
                    coin_menu(chat_id, "from")

                elif data == "type_iban_to_crypto":
                    user_state[chat_id] = {"type": "iban_to_crypto"}
                    send(chat_id, "📥 Alacağın kriptoyu seç:")
                    coin_menu(chat_id, "to")

                elif data == "type_crypto_to_iban":
                    user_state[chat_id] = {"type": "crypto_to_iban"}
                    send(chat_id, "📤 Göndereceğin kriptoyu seç:")
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
