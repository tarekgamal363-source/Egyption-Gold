"""
news_scraper.py
----------------
يجيب أخبار حقيقية مؤثرة على الذهب (جيوسياسة، الفيدرالي، الصين، النفط...)
من Google News RSS (مصدر عام مجاني، من غير مفتاح API)، ويحول توقيت النشر
لتوقيت مصر.

المتطلبات:
    pip install requests

الاستخدام:
    from news_scraper import get_news
    data = get_news()
"""

import requests
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

CAIRO_TZ = ZoneInfo("Africa/Cairo")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# كل استعلام هنا بيمثل موضوع مختلف مؤثر على الذهب، وليه تصنيف خاص بيه
QUERIES = [
    ("أسعار الذهب اليوم", "أسعار"),
    ("الفيدرالي الأمريكي الفائدة", "اقتصاد عالمي"),
    ("توترات إيران أمريكا", "جيوسياسية"),
    ("الصين شراء احتياطي الذهب", "جيوسياسية"),
    ("أسعار النفط اليوم", "طاقة"),
    ("الدولار الأمريكي اليوم", "اقتصاد عالمي"),
]


def _fetch_rss(query):
    url = "https://news.google.com/rss/search"
    params = {"q": query, "hl": "ar", "gl": "EG", "ceid": "EG:ar"}
    resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return resp.text


def _parse_items(xml_text, category):
    root = ET.fromstring(xml_text)
    items = []
    for item in root.findall(".//item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date_raw = item.findtext("pubDate")
        source_el = item.find("source")
        source = source_el.text if source_el is not None else None

        pub_dt = None
        if pub_date_raw:
            try:
                pub_dt = parsedate_to_datetime(pub_date_raw).astimezone(CAIRO_TZ)
            except (TypeError, ValueError):
                pub_dt = None

        items.append({
            "title": title,
            "link": link,
            "source": source,
            "category": category,
            "published_cairo": pub_dt.strftime("%Y-%m-%d %H:%M") if pub_dt else None,
            "_sort_key": pub_dt.timestamp() if pub_dt else 0,
        })
    return items


def get_news(limit=20):
    all_items = []
    seen_titles = set()

    for query, category in QUERIES:
        try:
            xml_text = _fetch_rss(query)
            for it in _parse_items(xml_text, category):
                if it["title"] not in seen_titles:
                    seen_titles.add(it["title"])
                    all_items.append(it)
        except Exception:
            continue  # لو استعلام واحد فشل، كمل الباقي

    all_items.sort(key=lambda x: x["_sort_key"], reverse=True)
    for it in all_items:
        it.pop("_sort_key", None)

    return {"source": "Google News RSS", "timezone": "Africa/Cairo", "items": all_items[:limit]}


if __name__ == "__main__":
    import json
    print(json.dumps(get_news(), ensure_ascii=False, indent=2))
