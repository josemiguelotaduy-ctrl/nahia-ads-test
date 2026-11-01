#!/usr/bin/env python3
"""
Cloud-native 21:00 (9:00 PM Madrid) Ultra-Simple Telegram Summary
"""
import datetime as dt
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import build_test_dashboard

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(ROOT, "data.json")
TZ = ZoneInfo("Europe/Madrid")


def build_report():
    data = json.load(open(DATA_PATH))
    S = data.get("summary", {})
    g_camps = data.get("google_campaigns", [])
    m_as = data.get("meta_adsets", [])

    tot_spend = float(S.get("total_spend", 0))
    rem = max(0.0, 1000.0 - tot_spend)
    net_sales = float(S.get("net_sales", 0))
    orders = int(S.get("orders", 0))

    ma = next((a for a in m_as if "ArmA" in a["name"]), {"clicks": 0, "conv": 0, "spend": 0})
    mb = next((a for a in m_as if "ArmB" in a["name"]), {"clicks": 0, "conv": 0, "spend": 0})
    if mb["conv"] > ma["conv"] or (mb["conv"] == ma["conv"] and mb["clicks"] >= ma["clicks"]):
        meta_line = f"Catálogo Dinámico va delante ({mb['clicks']} clics, {mb['conv']} compras)"
    else:
        meta_line = f"Carrusel Editorial va delante ({ma['clicks']} clics, {ma['conv']} compras)"

    g1a = next((c for c in g_camps if "ArmA" in c["name"]), {"clicks": 0, "conv": 0})
    g1b = next((c for c in g_camps if "ArmB" in c["name"]), {"clicks": 0, "conv": 0})
    g2 = next((c for c in g_camps if "Search" in c["name"]), {"clicks": 0, "conv": 0})
    tot_g_clicks = g1a["clicks"] + g1b["clicks"] + g2["clicks"]
    if tot_g_clicks == 0:
        goog_line = "Arrancando impresiones hoy"
    else:
        goog_line = f"{tot_g_clicks} clics (Shopping A: {g1a['clicks']}, Shopping B: {g1b['clicks']}, Search: {g2['clicks']})"

    day_num = dt.datetime.now(TZ).day
    if day_num < 10:
        tip = f"Todo en orden a 32,50 €/día. En {10 - day_num} días (10 Nov) apagamos los perdedores."
    else:
        tip = "Revisa qué brazo tiene más ventas para concentrar ahí el presupuesto."

    return "\n".join([
        "🏛 <b>Nahia Home · Resumen del Día</b>",
        "",
        f"💰 <b>Ventas Nov:</b> {net_sales:.0f} € ({orders} pedidos)",
        f"💸 <b>Gastado:</b> {tot_spend:.2f} € de 1.000 € <i>(quedan {rem:.0f} €)</i>",
        "",
        "🏆 <b>Cómo va el Test:</b>",
        f"• <b>Meta:</b> {meta_line}",
        f"• <b>Google:</b> {goog_line}",
        "",
        f"💡 <b>Consejo:</b> {tip}",
        "",
        "🔗 <a href='https://josemiguelotaduy-ctrl.github.io/nahia-ads-test/'>Ver Dashboard</a> · <i>Escríbeme «resumen», «meta», «google», «pausa...» o lo que necesites.</i>",
    ])


def main():
    build_test_dashboard.main()
    env = build_test_dashboard.load_env()
    text = build_report()
    bot_token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = env.get("TELEGRAM_CHAT_ID", "").strip()
    if bot_token and chat_id:
        send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(send_url, data=payload)
        resp = json.load(urllib.request.urlopen(req, timeout=20))
        print("Cloud Telegram sent:", resp.get("ok"))


if __name__ == "__main__":
    main()
