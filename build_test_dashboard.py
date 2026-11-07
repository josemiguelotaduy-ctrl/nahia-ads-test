#!/usr/bin/env python3
"""
Standalone November 2026 Ads A/B Test Lab Builder (100% separate from the P&L dashboard).
Publishes to https://josemiguelotaduy-ctrl.github.io/nahia-ads-test/
"""
import csv
import datetime as dt
import io
import json
import os
import subprocess
import urllib.parse
import urllib.request
from collections import defaultdict
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(ROOT, "..", ".env")
TZ = ZoneInfo("Europe/Madrid")
START_DATE = "2026-11-01"


def load_env():
    env = dict(os.environ)
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    env[k] = v.strip().strip('"').strip("'")
    return env


def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    return json.load(urllib.request.urlopen(req, timeout=45))


def main():
    env = load_env()
    today_str = dt.datetime.now(TZ).date().isoformat()
    if today_str < START_DATE:
        today_str = START_DATE

    daily = defaultdict(lambda: {"google_spend": 0.0, "meta_spend": 0.0, "net_sales": 0.0, "orders": 0})
    d_cur = dt.date.fromisoformat(START_DATE)
    d_end = dt.date.fromisoformat(today_str)
    while d_cur <= d_end:
        _ = daily[d_cur.isoformat()]
        d_cur += dt.timedelta(days=1)

    # 1. Fetch November Shopify sales via ShopifyQL (takes ~1s)
    try:
        store = env["SHOPIFY_STORE"]
        tok = http_json(
            f"https://{store}/admin/oauth/access_token",
            urllib.parse.urlencode({
                "grant_type": "client_credentials",
                "client_id": env["SHOPIFY_CLIENT_ID"],
                "client_secret": env["SHOPIFY_CLIENT_SECRET"],
            }).encode(),
        )["access_token"]
        q_sql = f'{{ shopifyqlQuery(query: "FROM sales SHOW orders, net_sales, shipping_charges, total_sales TIMESERIES day SINCE {START_DATE} UNTIL today") {{ tableData {{ rows }} }} }}'
        res_s = http_json(
            f"https://{store}/admin/api/2025-10/graphql.json",
            json.dumps({"query": q_sql}).encode(),
            {"X-Shopify-Access-Token": tok, "Content-Type": "application/json"},
        )
        rows = (((res_s.get("data") or {}).get("shopifyqlQuery") or {}).get("tableData") or {}).get("rows", [])
        for r in rows:
            d_s = r["day"]
            if d_s >= START_DATE:
                daily[d_s]["orders"] = int(float(r.get("orders", 0)))
                daily[d_s]["net_sales"] = round(float(r.get("net_sales", 0)) + float(r.get("shipping_charges", 0)), 2)
    except Exception as e:
        print("Shopify fetch warning:", e)

    # 2. Fetch Meta Ads (Account daily spend in Nov + AdSets + 8 Westwing Ads)
    meta_adsets = []
    meta_ads = []
    try:
        nov_rng = json.dumps({"since": START_DATE, "until": today_str})
        act = env["META_AD_ACCOUNT_ID"]
        mtok = env["META_ACCESS_TOKEN"]
        # Daily account spend
        u_day = f"https://graph.facebook.com/v21.0/{act}/insights?" + urllib.parse.urlencode({
            "fields": "spend",
            "time_increment": 1,
            "time_range": nov_rng,
            "access_token": mtok,
        })
        for r in http_json(u_day).get("data", []):
            daily[r["date_start"]]["meta_spend"] += round(float(r.get("spend", 0)), 2)

        # AdSets
        as_data = http_json(f"https://graph.facebook.com/v21.0/{act}/adsets?" + urllib.parse.urlencode({
            "fields": "id,name,status,effective_status,daily_budget,campaign{name}",
            "limit": 100,
            "access_token": mtok,
        })).get("data", [])
        ins_as_map = {
            r["adset_id"]: r
            for r in http_json(f"https://graph.facebook.com/v21.0/{act}/insights?" + urllib.parse.urlencode({
                "fields": "adset_id,spend,impressions,clicks,actions,action_values",
                "level": "adset",
                "time_range": nov_rng,
                "limit": 100,
                "access_token": mtok,
            })).get("data", [])
        }
        for a in as_data:
            cname = (a.get("campaign") or {}).get("name", "")
            if "Nov2026" in cname:
                ins = ins_as_map.get(a["id"], {})
                act_m = {x["action_type"]: float(x["value"]) for x in ins.get("actions", [])}
                av_m = {x["action_type"]: float(x["value"]) for x in ins.get("action_values", [])}
                meta_adsets.append({
                    "id": a["id"],
                    "name": a["name"],
                    "campaign": cname,
                    "status": a.get("effective_status", a.get("status", "")),
                    "daily_budget": round(float(a.get("daily_budget", 0)) / 100.0, 2),
                    "spend": round(float(ins.get("spend", 0)), 2),
                    "impr": int(float(ins.get("impressions", 0))),
                    "clicks": int(float(ins.get("clicks", 0))),
                    "atc": int(act_m.get("omni_add_to_cart", 0)),
                    "conv": int(act_m.get("omni_purchase", 0)),
                    "value": round(av_m.get("omni_purchase", 0.0), 2),
                })

        # 8 Westwing Ads
        ads_data = http_json(f"https://graph.facebook.com/v21.0/{act}/ads?" + urllib.parse.urlencode({
            "fields": "id,name,status,effective_status,adset{name},campaign{name}",
            "limit": 100,
            "access_token": mtok,
        })).get("data", [])
        ins_ad_map = {
            r["ad_id"]: r
            for r in http_json(f"https://graph.facebook.com/v21.0/{act}/insights?" + urllib.parse.urlencode({
                "fields": "ad_id,spend,impressions,clicks,actions,action_values",
                "level": "ad",
                "time_range": nov_rng,
                "limit": 100,
                "access_token": mtok,
            })).get("data", [])
        }
        for ad in ads_data:
            cname = (ad.get("campaign") or {}).get("name", "")
            if "Nov2026" in cname:
                ins = ins_ad_map.get(ad["id"], {})
                act_m = {x["action_type"]: float(x["value"]) for x in ins.get("actions", [])}
                av_m = {x["action_type"]: float(x["value"]) for x in ins.get("action_values", [])}
                meta_ads.append({
                    "id": ad["id"],
                    "name": ad["name"],
                    "adset": (ad.get("adset") or {}).get("name", ""),
                    "status": ad.get("effective_status", ad.get("status", "")),
                    "spend": round(float(ins.get("spend", 0)), 2),
                    "impr": int(float(ins.get("impressions", 0))),
                    "clicks": int(float(ins.get("clicks", 0))),
                    "atc": int(act_m.get("omni_add_to_cart", 0)),
                    "conv": int(act_m.get("omni_purchase", 0)),
                    "value": round(av_m.get("omni_purchase", 0.0), 2),
                })
        meta_ads.sort(key=lambda x: (x["clicks"], x["impr"], x["name"]), reverse=True)
    except Exception as e:
        print("Meta fetch warning:", e)

    # 3. Fetch Google Ads: Sheet CSV (24/7 reliable cloud data) + API v26
    google_campaigns = []
    google_adgroups = []
    google_ads = []

    sheet_url = env.get("GOOGLE_ADS_SHEET_CSV", "https://docs.google.com/spreadsheets/d/e/2PACX-1vTigRKjvzR3V2H9ZvjaItfpOBkziVIGav0rxEvlbIouN_mrxctnAsJUmfjtmpqL-R2zevo2oVcj4Nn8/pub?gid=271399287&single=true&output=csv")
    if sheet_url:
        try:
            raw_csv = urllib.request.urlopen(sheet_url, timeout=30).read().decode("utf-8")
            for r in csv.DictReader(io.StringIO(raw_csv)):
                d_s = r.get("date", "")
                if d_s >= START_DATE and d_s <= today_str:
                    c_name = r.get("campaign", "")
                    cost = float(r.get("cost", 0) or 0)
                    clicks = int(float(r.get("clicks", 0) or 0))
                    impr = int(float(r.get("impressions", 0) or 0))
                    conv = float(r.get("conversions", 0) or 0)
                    val = float(r.get("conversions_value", 0) or 0)
                    daily[d_s]["google_spend"] += round(cost, 2)
                    existing = next((c for c in google_campaigns if c["name"] == c_name), None)
                    if existing:
                        existing["spend"] += round(cost, 2)
                        existing["impr"] += impr
                        existing["clicks"] += clicks
                        existing["conv"] += round(conv, 2)
                        existing["value"] += round(val, 2)
                    else:
                        google_campaigns.append({
                            "id": "sheet_" + c_name,
                            "name": c_name,
                            "status": "ENABLED",
                            "daily_budget": 0.0,
                            "spend": round(cost, 2),
                            "impr": impr,
                            "clicks": clicks,
                            "conv": round(conv, 2),
                            "value": round(val, 2),
                        })
        except Exception as e:
            print("Google Sheet fetch warning:", e)

    try:
        tok_data = urllib.parse.urlencode({
            "client_id": env["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": env["GOOGLE_ADS_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }).encode()
        g_tok = http_json("https://oauth2.googleapis.com/token", data=tok_data)["access_token"]
        cid = env.get("GOOGLE_ADS_CUSTOMER_ID", "9529309545").replace("-", "")
        g_headers = {
            "Authorization": f"Bearer {g_tok}",
            "developer-token": env["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "login-customer-id": "4863032592",
            "Content-Type": "application/json",
        }
        # Daily account spend in Nov
        q_day = f"SELECT segments.date, metrics.cost_micros FROM customer WHERE segments.date BETWEEN '{START_DATE}' AND '{today_str}'"
        api_daily_sp = {}
        for row in http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                             data=json.dumps({"query": q_day}).encode(), headers=g_headers).get("results", []):
            d_s = row["segments"]["date"]
            api_daily_sp[d_s] = round(float(row.get("metrics", {}).get("costMicros", 0)) / 1e6, 2)
        if api_daily_sp:
            for d_s, sp in api_daily_sp.items():
                daily[d_s]["google_spend"] = sp

        # Campaigns metadata + metrics
        q_cm = "SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros FROM campaign WHERE (campaign.name LIKE '%Nov2026%' OR campaign.name = 'Sales-Shopping-1') AND campaign.status != 'REMOVED'"
        res_cm = http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                           data=json.dumps({"query": q_cm}).encode(), headers=g_headers).get("results", [])
        q_cmet = f"SELECT campaign.id, metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions, metrics.conversions_value FROM campaign WHERE (campaign.name LIKE '%Nov2026%' OR campaign.name = 'Sales-Shopping-1') AND segments.date BETWEEN '{START_DATE}' AND '{today_str}'"
        res_cmet = http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                             data=json.dumps({"query": q_cmet}).encode(), headers=g_headers).get("results", [])
        c_map = defaultdict(lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "conv": 0.0, "value": 0.0})
        for r in res_cmet:
            m = r.get("metrics", {})
            c_map[r["campaign"]["id"]]["spend"] += float(m.get("costMicros", 0)) / 1e6
            c_map[r["campaign"]["id"]]["impr"] += int(float(m.get("impressions", 0)))
            c_map[r["campaign"]["id"]]["clicks"] += int(float(m.get("clicks", 0)))
            c_map[r["campaign"]["id"]]["conv"] += float(m.get("conversions", 0))
            c_map[r["campaign"]["id"]]["value"] += float(m.get("conversionsValue", 0))
        if res_cm:
            google_campaigns = []
        for r in res_cm:
            c = r["campaign"]
            mm = c_map[c["id"]]
            google_campaigns.append({
                "id": c["id"],
                "name": c["name"],
                "status": c["status"],
                "daily_budget": round(float(r["campaignBudget"].get("amountMicros", 0)) / 1e6, 2),
                "spend": round(mm["spend"], 2),
                "impr": mm["impr"],
                "clicks": mm["clicks"],
                "conv": round(mm["conv"], 2),
                "value": round(mm["value"], 2),
            })

        # Ad Groups metadata + metrics
        q_agm = "SELECT campaign.name, ad_group.id, ad_group.name, ad_group.status FROM ad_group WHERE campaign.name LIKE '%Nov2026%' AND ad_group.status != 'REMOVED'"
        res_agm = http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                            data=json.dumps({"query": q_agm}).encode(), headers=g_headers).get("results", [])
        q_agmet = f"SELECT ad_group.id, metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions, metrics.conversions_value FROM ad_group WHERE campaign.name LIKE '%Nov2026%' AND segments.date BETWEEN '{START_DATE}' AND '{today_str}'"
        res_agmet = http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                              data=json.dumps({"query": q_agmet}).encode(), headers=g_headers).get("results", [])
        ag_map = defaultdict(lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "conv": 0.0, "value": 0.0})
        for r in res_agmet:
            m = r.get("metrics", {})
            ag_map[r["adGroup"]["id"]]["spend"] += float(m.get("costMicros", 0)) / 1e6
            ag_map[r["adGroup"]["id"]]["impr"] += int(float(m.get("impressions", 0)))
            ag_map[r["adGroup"]["id"]]["clicks"] += int(float(m.get("clicks", 0)))
            ag_map[r["adGroup"]["id"]]["conv"] += float(m.get("conversions", 0))
            ag_map[r["adGroup"]["id"]]["value"] += float(m.get("conversionsValue", 0))
        for r in res_agm:
            ag = r["adGroup"]
            mm = ag_map[ag["id"]]
            google_adgroups.append({
                "id": ag["id"],
                "name": ag["name"],
                "campaign": r["campaign"]["name"],
                "status": ag["status"],
                "spend": round(mm["spend"], 2),
                "impr": mm["impr"],
                "clicks": mm["clicks"],
                "conv": round(mm["conv"], 2),
                "value": round(mm["value"], 2),
            })

        # Google Search 12 RSAs
        q_adm = "SELECT ad_group.name, ad_group_ad.ad.id, ad_group_ad.status, ad_group_ad.ad.final_urls, ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.path1, ad_group_ad.ad.responsive_search_ad.path2 FROM ad_group_ad WHERE campaign.name = 'G2_Nov2026_Search_LuxuryBrands_Exact' AND ad_group_ad.status != 'REMOVED'"
        res_adm = http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                            data=json.dumps({"query": q_adm}).encode(), headers=g_headers).get("results", [])
        q_admet = f"SELECT ad_group_ad.ad.id, metrics.cost_micros, metrics.clicks, metrics.impressions, metrics.conversions, metrics.conversions_value FROM ad_group_ad WHERE campaign.name = 'G2_Nov2026_Search_LuxuryBrands_Exact' AND segments.date BETWEEN '{START_DATE}' AND '{today_str}'"
        res_admet = http_json(f"https://googleads.googleapis.com/v26/customers/{cid}/googleAds:search",
                              data=json.dumps({"query": q_admet}).encode(), headers=g_headers).get("results", [])
        gad_map = defaultdict(lambda: {"spend": 0.0, "impr": 0, "clicks": 0, "conv": 0.0, "value": 0.0})
        for r in res_admet:
            m = r.get("metrics", {})
            aid = r["adGroupAd"]["ad"]["id"]
            gad_map[aid]["spend"] += float(m.get("costMicros", 0)) / 1e6
            gad_map[aid]["impr"] += int(float(m.get("impressions", 0)))
            gad_map[aid]["clicks"] += int(float(m.get("clicks", 0)))
            gad_map[aid]["conv"] += float(m.get("conversions", 0))
            gad_map[aid]["value"] += float(m.get("conversionsValue", 0))
        for r in res_adm:
            ag_n = r["adGroup"]["name"]
            ad = r["adGroupAd"]["ad"]
            rsa = ad.get("responsiveSearchAd", {})
            h0 = (rsa.get("headlines") or [{}])[0].get("text", "")
            angle = "Copy 1 (Curated Collection)" if "Collection" in h0 else "Copy 2 (Artisanal Edit)"
            mm = gad_map[ad["id"]]
            google_ads.append({
                "id": ad["id"],
                "adgroup": ag_n,
                "angle": angle,
                "display_url": f"nahiahome.com/{rsa.get('path1','')}/{rsa.get('path2','')}",
                "final_url": (ad.get("finalUrls") or [""])[0],
                "status": r["adGroupAd"]["status"],
                "spend": round(mm["spend"], 2),
                "impr": mm["impr"],
                "clicks": mm["clicks"],
                "conv": round(mm["conv"], 2),
                "value": round(mm["value"], 2),
            })
    except Exception as e:
        print("Google Ads fetch warning:", e)

    daily_list = [{"d": k, **v} for k, v in sorted(daily.items())]
    g_spend = round(sum(x["google_spend"] for x in daily_list), 2)
    m_spend = round(sum(x["meta_spend"] for x in daily_list), 2)
    tot_spend = round(g_spend + m_spend, 2)
    today_row = daily[today_str]
    today_spend = round(today_row["google_spend"] + today_row["meta_spend"], 2)

    m_test_clicks = sum(a["clicks"] for a in meta_adsets)
    m_test_atc = sum(a["atc"] for a in meta_adsets)
    g_test_clicks = sum(c["clicks"] for c in google_campaigns)

    payload = {
        "generated": dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "total_spend": tot_spend,
            "google_spend": g_spend,
            "meta_spend": m_spend,
            "today_spend": today_spend,
            "daily_rate": 32.50,
            "net_sales": round(sum(x["net_sales"] for x in daily_list), 2),
            "orders": sum(x["orders"] for x in daily_list),
            "test_clicks": m_test_clicks + g_test_clicks,
            "meta_test_clicks": m_test_clicks,
            "meta_test_atc": m_test_atc,
            "google_test_clicks": g_test_clicks,
        },
        "daily": daily_list,
        "google_campaigns": google_campaigns,
        "google_adgroups": google_adgroups,
        "google_ads": google_ads,
        "meta_adsets": meta_adsets,
        "meta_ads": meta_ads,
    }

    with open(os.path.join(ROOT, "data.json"), "w") as f:
        json.dump(payload, f, indent=2)

    html = open(os.path.join(ROOT, "template.html")).read().replace("__DATA__", json.dumps(payload))
    with open(os.path.join(ROOT, "index.html"), "w") as f:
        f.write(html)

    print(f"OK -> ads_test_dashboard/index.html built (Nov Spend: €{tot_spend:.2f}, Meta Test Clicks: {m_test_clicks})")

    # Push to separate GitHub repo nahia-ads-test
    if os.path.exists(os.path.join(ROOT, ".git")):
        subprocess.run(["git", "add", "-A"], cwd=ROOT)
        subprocess.run(["git", "commit", "-m", f"Update Ads Test Lab {payload['generated']}"], cwd=ROOT)
        subprocess.run(["git", "push", "origin", "main"], cwd=ROOT)
        print("Synced and pushed to https://josemiguelotaduy-ctrl.github.io/nahia-ads-test/")


if __name__ == "__main__":
    main()
