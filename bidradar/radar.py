# -*- coding: utf-8 -*-
"""標案雷達 v2.1 —— 財商腦外科（雙資料源＋狀態診斷版）"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

_env_hosts = os.environ.get("BIDRADAR_API_HOSTS", "").strip()
API_HOSTS = _env_hosts.split(",") if _env_hosts else [
    "https://pcc-api.openfun.app/api",
    "https://pcc.g0v.ronny.tw/api",
]
TZ_TAIPEI = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))

KEYWORDS_PATH = os.path.join(HERE, "keywords.json")
SEEN_PATH = os.path.join(HERE, "seen.json")
HITS_PATH = os.path.join(HERE, "hits.json")
DOCS_DIR = os.path.join(HERE, "docs")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) BidRadar/2.1",
    "Accept": "application/json",
}


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def http_get(url, params=None, retries=2):
    last = ""
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=40)
            if r.status_code == 200:
                try:
                    return r.json(), "ok"
                except Exception:
                    last = "JSON解析失敗 body=" + r.text[:80].replace("\n", " ")
            else:
                last = f"HTTP {r.status_code} body=" + r.text[:80].replace("\n", " ")
        except Exception as e:
            last = f"連線錯誤 {e}"
        time.sleep(1.5 * (i + 1))
    return None, last


def fetch_by_date(date_str):
    for host in API_HOSTS:
        name = host.split("/")[2]
        data, msg = http_get(f"{host}/listbydate", {"date": date_str})
        if data is not None:
            recs = data.get("records") or []
            print(f"[info] {date_str} 共 {len(recs)} 筆（來源 {name}）")
            return recs
        print(f"[warn] {date_str} {name} 失敗：{msg}")
    print(f"[error] {date_str} 兩個來源都失敗")
    return []


def record_fields(rec):
    unit = rec.get("unit_name") or ""
    brief = rec.get("brief") or {}
    if isinstance(brief, str):
        try:
            brief = json.loads(brief)
        except Exception:
            brief = {}
    title = brief.get("title") or ""
    rtype = brief.get("type") or ""
    unit_id = rec.get("unit_id") or ""
    job_number = rec.get("job_number") or rec.get("filename") or ""
    date = str(rec.get("date") or "")
    url = rec.get("url") or ""
    return unit, title, rtype, unit_id, job_number, date, url


def match(rec, cfg):
    unit, title = record_fields(rec)[0], record_fields(rec)[1]
    text = f"{unit} {title}"
    for bad in cfg.get("exclude", []):
        if bad and bad in title:
            return False, ""
    for org in cfg.get("watch_all_units", []):
        if org and org in unit:
            return True, f"🎯 {org}"
    for org in cfg.get("watch_topic_units", []):
        if org and org in unit:
            for kw in cfg.get("topics", []):
                if kw and kw in title:
                    return True, f"🔎 {org}×{kw}"
    for region in cfg.get("region_words", []):
        if region and region in text:
            for kw in cfg.get("topics", []):
                if kw and kw in title:
                    return True, f"🗺 {region}×{kw}"
    return False, ""


def render_html(all_hits):
    os.makedirs(DOCS_DIR, exist_ok=True)
    rows = []
    for h in all_hits[:200]:
        rows.append(
            "<tr>"
            f"<td>{h.get('date','')}</td>"
            f"<td>{h.get('unit','')}</td>"
            f"<td><a href='{h.get('link','#')}' target='_blank'>{h.get('title','')}</a></td>"
            f"<td>{h.get('type','')}</td>"
            f"<td>{h.get('why','')}</td>"
            "</tr>"
        )
    updated = datetime.now(TZ_TAIPEI).strftime("%Y/%m/%d %H:%M")
    html = f"""<!DOCTYPE html>
<html lang="zh-Hant"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>📡 標案雷達戰情板｜財商腦外科</title>
<style>
 body{{font-family:'Noto Sans TC',sans-serif;background:#111;color:#eee;margin:0;padding:20px}}
 h1{{font-size:22px;margin:0 0 4px}} h1 span{{color:#e63946}}
 .sub{{color:#999;font-size:13px;margin-bottom:16px}}
 table{{width:100%;border-collapse:collapse;font-size:14px}}
 th,td{{border-bottom:1px solid #333;padding:10px
