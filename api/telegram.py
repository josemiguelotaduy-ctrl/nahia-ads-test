from http.server import BaseHTTPRequestHandler
import json
import os
import re
import urllib.parse
import urllib.request

DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data.json")

def send_reply(bot_token, chat_id, text):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": str(chat_id),
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=payload)
    urllib.request.urlopen(req, timeout=15)

def meta_set_status(env, obj_id, status):
    url = f"https://graph.facebook.com/v21.0/{obj_id}"
    data = urllib.parse.urlencode({"access_token": env.get("META_ACCESS_TOKEN", ""), "status": status}).encode()
    req = urllib.request.Request(url, data=data)
    return json.load(urllib.request.urlopen(req, timeout=15))

def google_headers(env):
    tok_data = urllib.parse.urlencode({
        "client_id": env.get("GOOGLE_ADS_CLIENT_ID", ""),
        "client_secret": env.get("GOOGLE_ADS_CLIENT_SECRET", ""),
        "refresh_token": env.get("GOOGLE_ADS_REFRESH_TOKEN", ""),
        "grant_type": "refresh_token",
    }).encode()
    g_tok = json.load(urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=tok_data)))["access_token"]
    return {
        "Authorization": f"Bearer {g_tok}",
        "developer-token": env.get("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
        "login-customer-id": "4863032592",
        "Content-Type": "application/json",
    }

def google_set_status(env, camp_id, status):
    cid = env.get("GOOGLE_ADS_CUSTOMER_ID", "9529309545").replace("-", "")
    ops = [{
        "campaignOperation": {
            "update": {"resourceName": f"customers/{cid}/campaigns/{camp_id}", "status": status},
            "updateMask": "status",
        }
    }]
    req = urllib.request.Request(
        f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:mutate",
        data=json.dumps({"operations": ops}).encode(),
        headers=google_headers(env)
    )
    return json.load(urllib.request.urlopen(req, timeout=15))

def call_gemini(user_prompt, summary_ctx, key):
    system_instruction = f"""
Estás chateando por Telegram con Jose Miguel, fundador de Nahia Home (tu socio). Eres su director de marketing digital.

ESTILO DE CHAT TELEGRAM (OBLIGATORIO):
- Escribe exactamente como chatea una persona real por Telegram: MENSAJES CORTOS (máximo 2 a 4 frases).
- NADA de parrafadas, discursos largos, ni listas rígidas con emojis.
- NADA de saludos repetitivos como "Hola Jose Miguel" en cada mensaje.
- Sé directo, cercano, con criterio y naturalidad, como un compañero por WhatsApp.
- Si te pregunta tu opinión o cómo ve el día, dile lo que piensas con franqueza y claridad.

DATOS EN VIVO DEL TEST HOY:
{summary_ctx}

REGLAS DE NAHIA HOME (INTERIORIZADAS, NO LAS RECITES):
- Techo: 1.000 €/mes combinados.
- Fase 1: 32,50 €/día hasta el corte del 10 de noviembre.
- Estética Westwing: cero menciones de envío gratis en anuncios y cero ofertas.
- Dashboard independiente: https://josemiguelotaduy-ctrl.github.io/nahia-ads-test/
"""
    payload = {
        "contents": [
            {"parts": [{"text": f"{system_instruction}\n\nMensaje de Jose Miguel:\n{user_prompt}"}]}
        ],
        "generationConfig": {
            "maxOutputTokens": 160,
            "temperature": 0.7
        }
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-flash-lite:generateContent?key={key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            data = json.load(res)
            reply = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            reply = re.sub(r"^```html\s*", "", reply)
            reply = re.sub(r"^```\s*", "", reply)
            reply = re.sub(r"\s*```$", "", reply)
            return reply
    except Exception as e:
        return f"He recibido tu mensaje pero hubo un fallo conectando con la IA: {e}"

def handle_incoming_message(text, env):
    t = text.strip().lower()
    action = "CHAT"
    action_note = ""

    if any(w in t for w in ["pausa", "pausar", "para", "parar", "apaga", "apagar"]):
        if "todo" in t:
            try:
                for mid in ["120252159334580646", "120252159334630646"]:
                    meta_set_status(env, mid, "PAUSED")
                for gid in ["24417748931", "24417749450", "24417751670"]:
                    google_set_status(env, gid, "PAUSED")
                action = "PAUSE_ALL"
                action_note = "Pausadas todas las campañas en Google Ads y Meta Ads."
            except Exception as e:
                action_note = f"Error al pausar: {e}"
        elif "carrusel" in t or "arm a" in t:
            try:
                meta_set_status(env, "120252159334770646", "PAUSED")
                action_note = "Pausado Meta Arm A (Carrusel Editorial)."
            except Exception as e:
                action_note = f"Error: {e}"
        elif "catalogo" in t or "catálogo" in t or "arm b" in t:
            try:
                meta_set_status(env, "120252159335070646", "PAUSED")
                action_note = "Pausado Meta Arm B (Catálogo Dinámico 238)."
            except Exception as e:
                action_note = f"Error: {e}"

    elif any(w in t for w in ["activa", "activar", "enciende", "encender", "reanuda"]):
        if "todo" in t:
            try:
                for mid in ["120252159334580646", "120252159334630646", "120252159334770646", "120252159335070646", "120252159335300646"]:
                    meta_set_status(env, mid, "ACTIVE")
                for gid in ["24417748931", "24417749450", "24417751670"]:
                    google_set_status(env, gid, "ENABLED")
                action_note = "Activadas todas las campañas del test en Google y Meta."
            except Exception as e:
                action_note = f"Error al activar: {e}"

    # Load latest stats
    summary_ctx = "Gasto hoy: 4.41€ (Meta), 0€ (Google). 26 clics, 1 venta (80.90€)."
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH) as f:
                d = json.load(f)
                s = d.get("summary", {})
                summary_ctx = (
                    f"Gasto hoy: {s.get('today_spend',0)}€ (Meta: {s.get('meta_spend',0)}€, Google: {s.get('google_spend',0)}€). "
                    f"Clics test: {s.get('test_clicks',0)}. Ventas Shopify hoy: {s.get('orders',0)} pedidos ({s.get('net_sales',0)}€). "
                    f"Ritmo Fase 1 previsto: 32.50€/día."
                )
        except Exception:
            pass

    gemini_key = env.get("GEMINI_API_KEY", "")
    reply = call_gemini(text, summary_ctx, gemini_key)
    if action_note:
        reply = f"{reply}\n\n⚡ <i>Acción ejecutada: {action_note}</i>"
    return reply


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write("Nahia Home Ads Telegram Webhook is active 24/7.".encode("utf-8"))

    def do_POST(self):
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_len).decode("utf-8")
            update = json.loads(body)

            msg = update.get("message") or update.get("edited_message")
            if msg and "text" in msg:
                chat_id = str(msg["chat"]["id"])
                user_text = msg["text"]

                env = os.environ
                bot_token = env.get("TELEGRAM_BOT_TOKEN", "9162420006:AAEgSZmlbVU7KO_LoDdU6LYtN51GhWee_xY")
                allowed_chat = env.get("TELEGRAM_CHAT_ID", "1166601467")

                if chat_id == str(allowed_chat):
                    reply = handle_incoming_message(user_text, env)
                    send_reply(bot_token, chat_id, reply)

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(f"Error handled: {e}".encode("utf-8"))
