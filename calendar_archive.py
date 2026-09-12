"""
calendar_archive.py
---------------------
بيخزن كل حدث اقتصادي شفناه (بمتوقعه وسابقه) بشكل دائم في jsonbin.io، عشان
الحدث متفتقدش لما "الأسبوع" عند المصدر (ForexFactory) يتغير - إحنا كده
عندنا نسخة محفوظة بتاعتنا مش هتختفي.

الإعداد (مرة واحدة):
1. اعمل Bin جديد في jsonbin.io محتواه {}
2. في Render → Environment ضيف: CALENDAR_ARCHIVE_BIN_ID = الـ ID بتاعه
   (بيستخدم نفس JSONBIN_API_KEY اللي عندك بالفعل)
"""

import os
import requests

ARCHIVE_BIN_ID = os.environ.get("CALENDAR_ARCHIVE_BIN_ID")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")


def _using_remote():
    return bool(ARCHIVE_BIN_ID and JSONBIN_API_KEY)


def load_archive():
    if not _using_remote():
        return {}
    try:
        resp = requests.get(
            f"https://api.jsonbin.io/v3/b/{ARCHIVE_BIN_ID}/latest",
            headers={"X-Master-Key": JSONBIN_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        record = resp.json().get("record", {})
        return record if isinstance(record, dict) else {}
    except Exception:
        return {}


def save_archive(archive_dict):
    if not _using_remote():
        return
    try:
        requests.put(
            f"https://api.jsonbin.io/v3/b/{ARCHIVE_BIN_ID}",
            headers={"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"},
            json=archive_dict,
            timeout=10,
        )
    except Exception:
        pass


def upsert_events(archive_dict, events):
    """
    بيحدّث الأرشيف بأحداث جديدة (events: list of dicts فيهم title و date_cairo).
    بيحافظ على أي بيانات قديمة موجودة (زي actual) لو الحدث الجديد مبعتهاش.
    """
    for ev in events:
        key = f"{ev['date_cairo']}|{ev['title']}"
        existing = archive_dict.get(key, {})
        merged = dict(existing)
        for field in ("previous", "forecast", "actual", "impact", "impact_ar",
                      "time_cairo", "weekday_ar", "country", "explanation",
                      "scenarios", "trend_forecast_vs_previous"):
            new_value = ev.get(field)
            if new_value is not None:
                merged[field] = new_value
        merged["title"] = ev["title"]
        merged["date_cairo"] = ev["date_cairo"]
        archive_dict[key] = merged
    return archive_dict


def prune_old_entries(archive_dict, keep_days_low_medium=7, keep_days_high=730, keep_days_future=100):
    """
    قاعدة الاحتفاظ:
    - الأحداث عالية الأهمية: تتحفظ لفترة طويلة (سنتين تقريبًا) كأرشيف مرجعي
    - الأحداث متوسطة/منخفضة الأهمية: تتمسح بعد أسبوع من موعدها
    - أي حدث قادم في حدود 100 يوم قدام (~3 شهور) يفضل موجود
    """
    from datetime import datetime, timedelta
    today = datetime.now()
    cutoff_future = (today + timedelta(days=keep_days_future)).strftime("%Y-%m-%d")
    cutoff_high = (today - timedelta(days=keep_days_high)).strftime("%Y-%m-%d")
    cutoff_low_medium = (today - timedelta(days=keep_days_low_medium)).strftime("%Y-%m-%d")

    result = {}
    for k, v in archive_dict.items():
        date_cairo = v.get("date_cairo", "9999-99-99")
        if date_cairo > cutoff_future:
            continue  # بعيد جدًا في المستقبل، متسجلش لسه
        impact = v.get("impact")
        cutoff = cutoff_high if impact == "High" else cutoff_low_medium
        if date_cairo >= cutoff:
            result[k] = v
    return result
