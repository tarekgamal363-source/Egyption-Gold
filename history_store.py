"""
history_store.py
------------------
تخزين تاريخ الأسعار في مكان خارجي دائم (jsonbin.io) بدل السيرفر نفسه،
عشان البيانات متتمسحش لما Render يقفل السيرفر وقت عدم الاستخدام.

خطوات الإعداد (مرة واحدة بس):
1. اعمل حساب مجاني على https://jsonbin.io
2. من صفحة "API Keys" خد الـ "X-Master-Key" بتاعك
3. من الداشبورد اعمل Bin جديد فاضي بالمحتوى: []
   (زرار "Create Bin"، اكتب [] في المحتوى، احفظ)
4. من رابط الـ Bin هتلاقي ID طويل (مثلاً 65f1... في آخر الرابط)، انسخه
5. في Render → Environment، ضيف المتغيرين دول:
   JSONBIN_API_KEY = (المفتاح بتاعك)
   JSONBIN_BIN_ID  = (الـ ID بتاع الـ Bin)

لو المتغيرين دول مش موجودين، هيرجع النظام تلقائيًا يخزن على السيرفر
نفسه بس (زي الأول)، يعني هيشتغل التطبيق برضو لكن من غير ذاكرة دائمة.
"""

import os
import json
import requests

JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}" if JSONBIN_BIN_ID else None

LOCAL_FALLBACK_FILE = "price_history.json"


def _using_remote():
    return bool(JSONBIN_API_KEY and JSONBIN_BIN_ID)


def load_history():
    if _using_remote():
        try:
            resp = requests.get(
                f"{JSONBIN_URL}/latest",
                headers={"X-Master-Key": JSONBIN_API_KEY},
                timeout=10,
            )
            resp.raise_for_status()
            record = resp.json().get("record", [])
            # نتجاهل أي عنصر مش بالشكل المتوقع (dict) عشان محتوى غير سليم
            # ما يبوظش التطبيق كله
            if not isinstance(record, list):
                return []
            return [item for item in record if isinstance(item, dict)]
        except Exception:
            return []
    else:
        if os.path.exists(LOCAL_FALLBACK_FILE):
            try:
                with open(LOCAL_FALLBACK_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return []
        return []


def save_history(history_list):
    if _using_remote():
        try:
            requests.put(
                JSONBIN_URL,
                headers={
                    "X-Master-Key": JSONBIN_API_KEY,
                    "Content-Type": "application/json",
                },
                json=history_list,
                timeout=10,
            )
        except Exception:
            pass
    else:
        try:
            with open(LOCAL_FALLBACK_FILE, "w") as f:
                json.dump(history_list, f)
        except Exception:
            pass


# ===== أرشيف يومي خفيف (لعرض أسبوع/شهر) =====
# بدل ما نخزن كل نقطة دقيقة بدقيقة للأبد (كبير جدًا)، بنحتفظ بس بشمعة
# واحدة (أعلى/أقل/فتح/قفل) لكل يوم لكل مؤشر - حجم صغير جدًا حتى لسنين.
DAILY_BIN_ID = os.environ.get("JSONBIN_DAILY_BIN_ID")
DAILY_URL = f"https://api.jsonbin.io/v3/b/{DAILY_BIN_ID}" if DAILY_BIN_ID else None
DAILY_LOCAL_FALLBACK_FILE = "daily_history.json"


def _daily_using_remote():
    return bool(JSONBIN_API_KEY and DAILY_BIN_ID)


def load_daily_history():
    if _daily_using_remote():
        try:
            resp = requests.get(
                f"{DAILY_URL}/latest",
                headers={"X-Master-Key": JSONBIN_API_KEY},
                timeout=10,
            )
            resp.raise_for_status()
            record = resp.json().get("record", {})
            return record if isinstance(record, dict) else {}
        except Exception:
            return {}
    else:
        if os.path.exists(DAILY_LOCAL_FALLBACK_FILE):
            try:
                with open(DAILY_LOCAL_FALLBACK_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}


def save_daily_history(daily_dict):
    if _daily_using_remote():
        try:
            requests.put(
                DAILY_URL,
                headers={"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"},
                json=daily_dict,
                timeout=10,
            )
        except Exception:
            pass
    else:
        try:
            with open(DAILY_LOCAL_FALLBACK_FILE, "w") as f:
                json.dump(daily_dict, f)
        except Exception:
            pass


def upsert_daily_point(daily_dict, field, date_str, value):
    """بيحدّث شمعة اليوم لحقل معيّن (فتح/أعلى/أقل/قفل) بأحدث قيمة"""
    if value is None:
        return daily_dict
    field_history = daily_dict.setdefault(field, {})
    today = field_history.get(date_str)
    if today is None:
        field_history[date_str] = {"open": value, "high": value, "low": value, "close": value}
    else:
        today["high"] = max(today["high"], value)
        today["low"] = min(today["low"], value)
        today["close"] = value
    return daily_dict
