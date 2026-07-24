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
 th,td{{border-bottom:1px solid #333;padding:10px 8px;text-align:left;vertical-align:top}}
 th{{color:#d4a017;white-space:nowrap;position:sticky;top:0;background:#111}}
 a{{color:#7ec8ff;text-decoration:none}} a:hover{{text-decoration:underline}}
 tr:hover{{background:#1b1b1b}}
 .empty{{color:#777;padding:40px 0;text-align:center}}
</style></head><body>
<h1>📡 標案雷達 <span>戰情板</span></h1>
<div class="sub">監控：東港周邊七公所全案＋屏東縣政府資訊行銷案｜更新：{updated}</div>
<table><tr><th>日期</th><th>機關</th><th>案名</th><th>類型</th><th>命中</th></tr>
{''.join(rows) if rows else '<tr><td colspan=5 class=empty>雷達開機中，尚無命中。安靜是常態，命中是驚喜。</td></tr>'}
</table></body></html>"""
    with open(os.path.join(DOCS_DIR, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)


def fmt_hit(h):
    return f"{h['why']}｜{h['type']}\n【{h['unit']}】\n{h['title']}\n{h['date']}\n{h['link']}"


def open_github_issue(title, body):
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not token or not repo:
        return False
    url = f"https://api.github.com/repos/{repo}/issues"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json"}
    try:
        r = requests.post(url, headers=headers,
                          json={"title": title, "body": body}, timeout=30)
        print(f"[info] GitHub issue {r.status_code}")
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[warn] 開 Issue 失敗 {e}")
        return False


def main():
    cfg = load_json(KEYWORDS_PATH, {})
    seen = load_json(SEEN_PATH, [])
    seen_set = set(seen)
    all_hits = load_json(HITS_PATH, [])

    days_back = int(cfg.get("days_back", 2))
    today = datetime.now(TZ_TAIPEI)

    new_hits = []
    for d in range(days_back):
        date_str = (today - timedelta(days=d)).strftime("%Y%m%d")
        for rec in fetch_by_date(date_str):
            ok, why = match(rec, cfg)
            if not ok:
                continue
            unit, title, rtype, unit_id, job_number, date, url = record_fields(rec)
            key = f"{unit_id}|{job_number}|{rtype}|{title[:30]}"
            if key in seen_set:
                continue
            seen_set.add(key)
            link = url if url.startswith("http") else (
                "https://pcc.g0v.ronny.tw" + url if url else
                "https://pcc.mlwmlw.org/search/" + requests.utils.quote(title[:40]))
            h = {"date": date, "unit": unit, "title": title,
                 "type": rtype, "why": why, "link": link}
            all_hits.insert(0, h)
            new_hits.append(h)
        time.sleep(0.3)

    if new_hits:
        header = f"📡 標案雷達 {today.strftime('%m/%d')}｜命中 {len(new_hits)} 筆"
        body = "\n\n---\n\n".join(fmt_hit(h) for h in new_hits)
        open_github_issue(header, body)
        print(header)
    else:
        print("[info] 今日無命中，安靜是常態，命中是驚喜。")

    save_json(SEEN_PATH, list(seen_set)[-8000:])
    all_hits = all_hits[:200]
    save_json(HITS_PATH, all_hits)
    render_html(all_hits)


if __name__ == "__main__":
    sys.exit(main())
