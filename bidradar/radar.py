# -*- coding: utf-8 -*-
"""
標案雷達 v1 —— 財商腦外科
每天自動掃政府標案開放API，命中「目標區域 + 目標關鍵字」就推播 LINE。
沒設定 LINE 金鑰時，改成在 GitHub 開 Issue 通知（零設定也能跑）。

資料源：pcc-api.openfun.app（g0v 社群整理自政府電子採購網的開放 API）
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

API_BASE = "https://pcc-api.openfun.app/api"
TZ_TAIPEI = timezone(timedelta(hours=8))
HERE = os.path.dirname(os.path.abspath(__file__))

KEYWORDS_PATH = os.path.join(HERE, "keywords.json")
SEEN_PATH = os.path.join(HERE, "seen.json")

HEADERS = {"User-Agent": "BidRadar/1.0 (personal tender alert)"}


# ---------- 小工具 ----------

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def http_get(url, params=None, retries=3):
    for i in range(retries):
        try:
            r = requests.get(url, params=params, headers=HEADERS, timeout=30)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            print(f"[warn] GET 失敗 {url} {e}")
        time.sleep(2 * (i + 1))
    return None


# ---------- 抓資料 ----------

def fetch_by_date(date_str):
    """抓某一天的全部公告（自動翻頁）。date_str 格式 YYYYMMDD"""
    records = []
    page = 1
    while True:
        data = http_get(f"{API_BASE}/listbydate", {"date": date_str, "page": page})
        if not data:
            break
        recs = data.get("records", [])
        records.extend(recs)
        total_pages = int(data.get("total_pages", 1) or 1)
        if page >= total_pages:
            break
        page += 1
        time.sleep(0.6)  # 對免費API客氣一點
    print(f"[info] {date_str} 共 {len(records)} 筆公告")
    return records


# ---------- 過濾 ----------

def record_fields(rec):
    unit = rec.get("unit_name") or rec.get("unit") or ""
    brief = rec.get("brief") or {}
    title = brief.get("title") or rec.get("title") or ""
    rtype = brief.get("type") or rec.get("type") or ""
    unit_id = rec.get("unit_id") or ""
    job_number = rec.get("job_number") or rec.get("filename") or ""
    date = str(rec.get("date") or "")
    return unit, title, rtype, unit_id, job_number, date


def match(rec, cfg):
    unit, title, rtype, *_ = record_fields(rec)
    text = f"{unit} {title}"

    # 排除詞（工程類雜訊）
    for bad in cfg.get("exclude", []):
        if bad and bad in title:
            return False, ""

    # A. 重點小機關：只要是它發的案，全部通報
    for org in cfg.get("watch_all_units", []):
        if org and org in unit:
            return True, f"🎯 {org}"

    # B. 大機關（縣府等）：機關對到 + 案名含目標關鍵字才通報
    for org in cfg.get("watch_topic_units", []):
        if org and org in unit:
            for kw in cfg.get("topics", []):
                if kw and kw in title:
                    return True, f"🔎 {org}×{kw}"

    # C. 全國掃描：案名同時含「區域詞」與「主題詞」
    for region in cfg.get("region_words", []):
        if region and region in text:
            for kw in cfg.get("topics", []):
                if kw and kw in title:
                    return True, f"🗺 {region}×{kw}"

    return False, ""


# ---------- 通知 ----------

def fmt_hit(rec, why):
    unit, title, rtype, unit_id, job_number, date = record_fields(rec)
    q = requests.utils.quote(title[:40])
    link = f"https://pcc.mlwmlw.org/search/{q}"
    return f"{why}｜{rtype}\n【{unit}】\n{title}\n{date}\n{link}"


def push_line(text_blocks):
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.environ.get("LINE_ADMIN_USER_ID", "").strip()
    if not token or not user_id:
        return False
    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # LINE 每則上限約5000字、一次最多5則
    chunks, cur = [], ""
    for b in text_blocks:
        if len(cur) + len(b) + 4 > 4500:
            chunks.append(cur)
            cur = b
        else:
            cur = (cur + "\n\n" + b) if cur else b
    if cur:
        chunks.append(cur)
    ok = True
    for i in range(0, len(chunks), 5):
        payload = {
            "to": user_id,
            "messages": [{"type": "text", "text": c} for c in chunks[i:i + 5]],
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            print(f"[info] LINE push {r.status_code} {r.text[:120]}")
            ok = ok and (r.status_code == 200)
        except Exception as e:
            print(f"[warn] LINE push 失敗 {e}")
            ok = False
    return ok


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


# ---------- 主流程 ----------

HITS_PATH = os.path.join(HERE, "hits.json")
DOCS_DIR = os.path.join(HERE, "docs")


def render_html(all_hits):
    """把歷史命中輸出成戰情板網頁 docs/index.html（可掛 GitHub Pages / 嵌進自家網站）"""
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


def main():
    cfg = load_json(KEYWORDS_PATH, {})
    seen = load_json(SEEN_PATH, [])
    seen_set = set(seen)
    all_hits = load_json(HITS_PATH, [])

    days_back = int(cfg.get("days_back", 2))
    today = datetime.now(TZ_TAIPEI)

    hits = []
    for d in range(days_back):
        date_str = (today - timedelta(days=d)).strftime("%Y%m%d")
        for rec in fetch_by_date(date_str):
            ok, why = match(rec, cfg)
            if not ok:
                continue
            unit, title, rtype, unit_id, job_number, date = record_fields(rec)
            key = f"{unit_id}|{job_number}|{rtype}|{title[:30]}"
            if key in seen_set:
                continue
            seen_set.add(key)
            hits.append(fmt_hit(rec, why))
            q = requests.utils.quote(title[:40])
            all_hits.insert(0, {
                "date": date, "unit": unit, "title": title,
                "type": rtype, "why": why,
                "link": f"https://pcc.mlwmlw.org/search/{q}",
            })

    if hits:
        header = f"📡 標案雷達 {today.strftime('%m/%d')}｜命中 {len(hits)} 筆"
        blocks = [header] + hits
        sent = push_line(blocks)
        if not sent:
            open_github_issue(header, "\n\n---\n\n".join(hits))
        print("\n\n".join(blocks))
    else:
        print("[info] 今日無命中，安靜是常態，命中是驚喜。")

    # 狀態檔只留最近 8000 筆；戰情板留最近 200 筆
    save_json(SEEN_PATH, list(seen_set)[-8000:])
    all_hits = all_hits[:200]
    save_json(HITS_PATH, all_hits)
    render_html(all_hits)


if __name__ == "__main__":
    sys.exit(main())
