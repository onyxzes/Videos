"""Collect what's trending right now and save it to trends/<date>.json.

Sources:
  - Google Trends daily RSS per country (no key needed)
  - YouTube "mostPopular" chart per country (optional, env YT_API_KEY)
"""
import datetime as dt
import json
import os
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
NS = {"ht": "https://trends.google.com/trending/rss"}


def google_trends(geo: str) -> list[dict]:
    r = requests.get(f"https://trends.google.com/trending/rss?geo={geo}", timeout=30,
                     headers={"User-Agent": "Mozilla/5.0 (trend-reader)"})
    r.raise_for_status()
    out = []
    for item in ET.fromstring(r.content).iter("item"):
        news = [n.findtext("ht:news_item_title", default="", namespaces=NS)
                for n in item.findall("ht:news_item", NS)]
        out.append({"source": f"google_trends_{geo}", "term": item.findtext("title"),
                    "traffic": item.findtext("ht:approx_traffic", default="", namespaces=NS),
                    "context": [n for n in news if n][:2]})
    return out


def youtube_popular(geo: str) -> list[dict]:
    key = os.environ.get("YT_API_KEY")
    if not key:
        return []
    r = requests.get("https://www.googleapis.com/youtube/v3/videos", timeout=30, params={
        "part": "snippet,statistics", "chart": "mostPopular", "regionCode": geo,
        "maxResults": 25, "key": key})
    r.raise_for_status()
    return [{"source": f"youtube_{geo}", "term": v["snippet"]["title"],
             "views": v["statistics"].get("viewCount"), "context": v["snippet"].get("tags", [])[:5]}
            for v in r.json().get("items", [])]


def collect() -> Path:
    cfg = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    items = []
    for geo in cfg.get("trends_geo", ["MX"]):
        for fn in (google_trends, youtube_popular):
            try:
                items += fn(geo)
            except Exception as e:
                print(f"  [trends] {fn.__name__}({geo}) failed: {e}")
    out = ROOT / "trends" / f"{dt.date.today().isoformat()}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [trends] {len(items)} items -> {out.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    collect()
