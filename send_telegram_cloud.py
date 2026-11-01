#!/usr/bin/env python3
"""
Cloud-native 21:00 (9:00 PM Madrid) Telegram Executive Report + Budget Guard
Runs in GitHub Actions so it works even when the MacBook is closed/off.
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
    today = dt.datetime.now(TZ).date().isoformat()
    S = data.get("summary", {})
    g_camps = data.get("google_campaigns", [])
    m_as = data.get("meta_adsets", [])
    m_ads = data.get("meta_ads", [])

    cap_rem = max(0.0, 1000.0 - float(S.get("total_spend", 0)))
    day_num = int(today.split("-")[2])
    suggestions = []
    if day_num < 10:
        days_to_cut = 10 - day_num
        suggestions.append(
            f"• <b>Fase 1 en curso ({days_to_cut} días para el corte del 10 Nov):</b> Mantener los brazos de prueba activos a 32,50 €/día para acumular significancia estadística antes de pausar perdedores."
        )
    elif day_num == 10:
        suggestions.append(
            "• 🚨 <b>HOY ES DÍA 10 (Corte Fase 2):</b> Momento de pausar el brazo perdedor de Google Shopping, el Ad Set perdedor de Meta M1 y los copies con menor CTR/ROAS."
        )

    g1a = next((c for c in g_camps if "ManualCPC_ArmA" in c["name"]), None)
    g1b = next((c for c in g_camps if "MaxConvValue_ArmB" in c["name"]), None)
    if g1a and g1b and (g1a["spend"] > 0 or g1b["spend"] > 0):
        roas_a = g1a["value"] / g1a["spend"] if g1a["spend"] > 0 else 0
        roas_b = g1b["value"] / g1b["spend"] if g1b["spend"] > 0 else 0
        cpc_a = g1a["spend"] / g1a["clicks"] if g1a["clicks"] > 0 else 0
        cpc_b = g1b["spend"] / g1b["clicks"] if g1b["clicks"] > 0 else 0
        leader = "Arm A (Manual CPC)" if (roas_a > roas_b or (roas_a == roas_b and g1a["clicks"] > g1b["clicks"])) else "Arm B (Smart Bidding)"
        suggestions.append(
            f"• <b>Google Shopping A/B:</b> Lidera <b>{leader}</b> (Arm A: {g1a['clicks']} clics a {cpc_a:.2f}€ CPC, ROAS {roas_a:.2f} vs Arm B: {g1b['clicks']} clics a {cpc_b:.2f}€ CPC, ROAS {roas_b:.2f})."
        )

    ma = next((a for a in m_as if "ArmA" in a["name"]), None)
    mb = next((a for a in m_as if "ArmB" in a["name"]), None)
    if ma and mb and (ma["spend"] > 0 or mb["spend"] > 0):
        m_leader = "Arm A (Carrusel Editorial)" if (ma["value"] > mb["value"] or ma["atc"] > mb["atc"] or ma["clicks"] >= mb["clicks"]) else "Arm B (Catálogo Dinámico 238)"
        suggestions.append(
            f"• <b>Meta Prospecting A/B:</b> Lidera <b>{m_leader}</b> (Carrusel: {ma['clicks']} clics, {ma['atc']} ATC, {ma['conv']} compras vs Catálogo: {mb['clicks']} clics, {mb['atc']} ATC, {mb['conv']} compras)."
        )

    active_ads_sorted = sorted(m_ads, key=lambda x: (x["conv"], x["atc"], x["clicks"]), reverse=True)
    if active_ads_sorted and active_ads_sorted[0]["clicks"] > 0:
        top_ad = active_ads_sorted[0]
        suggestions.append(
            f"• <b>Mejor Anuncio Westwing en Meta:</b> <code>{top_ad['name']}</code> ({top_ad['clicks']} clics, {top_ad['atc']} ATC, {top_ad['conv']} compras)."
        )

    tot_spend = float(S.get("total_spend", 0))
    net_sales = float(S.get("net_sales", 0))
    roas = net_sales / tot_spend if tot_spend > 0 else 0.0

    msg = [
        f"🏛 <b>NAHIA HOME · Ads Test Lab ({today})</b>",
        "",
        "🗓 <b>ACUMULADO NOVIEMBRE (MTD):</b>",
        f"• Ventas Netas Shopify (s/IVA): <b>{net_sales:.2f} €</b> ({S.get('orders', 0)} pedidos)",
        f"• Gasto Ads MTD: <b>{tot_spend:.2f} € / 1.000,00 €</b> (Google: {S.get('google_spend', 0):.2f} € · Meta: {S.get('meta_spend', 0):.2f} €)",
        f"• Presupuesto Restante: <b>{cap_rem:.2f} €</b> ({tot_spend/10:.1f}% usado)",
        f"• ROAS Global MTD: <b>{roas:.2f}x</b>",
        "",
        "🔬 <b>ESTADO DEL TEST A/B (Acumulado Nov):</b>",
    ]
    for c in g_camps:
        roas_c = c["value"] / c["spend"] if c["spend"] > 0 else 0
        msg.append(f"• [Google] <code>{c['name'].replace('_Nov2026_', '_')}</code>: {c['spend']:.2f}€ | {c['clicks']} clics | {c['conv']:.0f} conv | ROAS {roas_c:.2f}x")
    for a in m_as:
        roas_a = a["value"] / a["spend"] if a["spend"] > 0 else 0
        msg.append(f"• [Meta] <code>{a['name'][:26]}</code>: {a['spend']:.2f}€ | {a['clicks']} clics | {a['atc']} ATC | {a['conv']} compras | ROAS {roas_a:.2f}x")

    msg += [
        "",
        "💡 <b>SUGERENCIAS Y PRÓXIMOS PASOS:</b>",
        *suggestions,
        "",
        "☁️ <b>Ads Test Lab Dashboard:</b>",
        "https://josemiguelotaduy-ctrl.github.io/nahia-ads-test/",
    ]
    return "\n".join(msg)


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
