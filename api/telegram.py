from http.server import BaseHTTPRequestHandler
import datetime as dt
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

def get_fresh_data():
    # 1. Try live GitHub raw with cache-busting timestamp
    try:
        t_now = int(dt.datetime.now().timestamp())
        url = f"https://raw.githubusercontent.com/josemiguelotaduy-ctrl/nahia-ads-test/main/data.json?_t={t_now}"
        req = urllib.request.Request(url, headers={"User-Agent": "NahiaTelegramBot"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            return json.load(resp)
    except Exception:
        pass
    # 2. Fallback to bundled local data.json
    if os.path.exists(DATA_PATH):
        try:
            with open(DATA_PATH) as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def build_live_context(d):
    if not d:
        return "Gasto y métricas sincronizándose actualmente."

    s = d.get("summary", {})
    m_as = d.get("meta_adsets", [])
    g_c = d.get("google_campaigns", [])
    daily = d.get("daily", [])

    tot_spend = float(s.get("total_spend", 0))
    today_spend = float(s.get("today_spend", 0))
    net_sales = float(s.get("net_sales", 0))
    orders = int(s.get("orders", 0))
    test_clicks = int(s.get("test_clicks", 0))
    roas = (net_sales / tot_spend) if tot_spend > 0 else 0

    ma = next((a for a in m_as if "ArmA" in a.get("name", "")), {"clicks": 0, "spend": 0, "conv": 0, "atc": 0})
    mb = next((a for a in m_as if "ArmB" in a.get("name", "")), {"clicks": 0, "spend": 0, "conv": 0, "atc": 0})
    ret = next((a for a in m_as if "Retargeting" in a.get("name", "")), {"clicks": 0, "spend": 0, "conv": 0, "atc": 0})

    g1a = next((c for c in g_c if "ArmA" in c.get("name", "")), {"clicks": 0, "spend": 0})
    g1b = next((c for c in g_c if "ArmB" in c.get("name", "")), {"clicks": 0, "spend": 0})
    g2 = next((c for c in g_c if "Search" in c.get("name", "")), {"clicks": 0, "spend": 0})

    today_d = daily[-1] if daily else {}
    today_sales = today_d.get("net_sales", 0)
    today_orders = today_d.get("orders", 0)
    today_meta = today_d.get("meta_spend", 0)
    today_google = today_d.get("google_spend", 0)

    return f"""
RESUMEN GENERAL NOVIEMBRE:
- Gasto acumulado Nov: {tot_spend:.2f}€ de los 1.000€ de presupuesto (quedan {max(0, 1000 - tot_spend):.0f}€).
- Ventas totales Shopify Nov: {net_sales:.0f}€ ({orders} pedidos). ROAS global: {roas:.1f}x.
- Clics totales enviados a la web: {test_clicks} clics cualificados.

MÉTRICAS ESPECÍFICAS DE HOY:
- Gasto de hoy: {today_spend:.2f}€ (Google: {today_google:.2f}€, Meta: {today_meta:.2f}€). Tope diario seguro: 32,50€/día.
- Ventas de hoy: {today_sales:.0f}€ ({today_orders} pedidos en la tienda).

BATALLA A/B EN DIRECTO:
• Meta Ads:
  - Arm B (Catálogo Dinámico 238 SKU): {mb.get('spend', 0)}€ gastados, {mb.get('clicks', 0)} clics (CPC muy bajo 0,14€), {mb.get('atc', 0)} carritos, {mb.get('conv', 0)} compras. ¡VA GANANDO CON CLARIDAD!
  - Arm A (Carrusel Editorial): {ma.get('spend', 0)}€ gastados, {ma.get('clicks', 0)} clics (CPC más caro), {ma.get('atc', 0)} carritos, 0 compras. Va lento.
  - Retargeting Caliente (Warm 30d): {ret.get('spend', 0)}€ gastados, {ret.get('clicks', 0)} clics, {ret.get('conv', 0)} compras directas. Convirtiendo a ROAS muy alto.
• Google Ads:
  - Shopping Arm A (Manual CPC): {g1a.get('spend', 0)}€, {g1a.get('clicks', 0)} clics. Mucho volumen y clics a 0,33€.
  - Shopping Arm B (Smart Bidding): {g1b.get('spend', 0)}€, {g1b.get('clicks', 0)} clics. Algoritmo aprendiendo.
  - Search Marcas Lujo: {g2.get('spend', 0)}€, {g2.get('clicks', 0)} clics.
"""

def call_gemini(user_prompt, summary_ctx, key):
    system_instruction = f"""
Estás chateando por Telegram con Jose Miguel, fundador de Nahia Home (tu socio). Eres su director de marketing digital.

REGLAS DE TONO (OBLIGATORIO):
- Chatea como un socio real por WhatsApp/Telegram: MENSAJES CORTOS (máximo 2 a 4 frases directas).
- Cero saludos pesados tipo "Hola Jose Miguel". Entra directo al grano.
- Cero listas largas o informes formales con 10 viñetas. Responde exactamente a lo que te pregunte.
- Criterio directo: si te pregunta cómo vamos, dale la foto rápida (ventas, gasto y quién va ganando). Si pregunta por un canal en concreto (ej. carrusel, catálogo, google), dale el dato exacto de ese canal.

DATOS EN TIEMPO REAL DEL TEST:
{summary_ctx}

REGLAS DE NEGOCIO (APLÍCALAS, NO LAS RECITES):
- Tope: 1.000 €/mes combinados.
- Fase 1 (1-10 Nov): ritmo de ~32,50 €/día. El 10 de Noviembre se apagan los perdedores y se concentra el presupuesto.
- Estética Westwing: cero menciones de envío gratis en anuncios y cero ofertas.
"""
    payload = {
        "contents": [
            {"parts": [{"text": f"{system_instruction}\n\nMensaje de Jose Miguel:\n{user_prompt}"}]}
        ],
        "generationConfig": {
            "maxOutputTokens": 180,
            "temperature": 0.65
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
        return f"Disculpa Jose, hubo un error temporal conectando con Gemini: {e}"

def handle_incoming_message(text, env):
    t = text.strip().lower()
    action_note = ""

    if any(w in t for w in ["pausa", "pausar", "para", "parar", "apaga", "apagar"]):
        if "todo" in t:
            try:
                for mid in ["120252159334580646", "120252159334630646"]:
                    meta_set_status(env, mid, "PAUSED")
                for gid in ["24417748931", "24417749450", "24417751670"]:
                    google_set_status(env, gid, "PAUSED")
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

    # Load fresh stats (live cloud)
    data = get_fresh_data()
    summary_ctx = build_live_context(data)

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
