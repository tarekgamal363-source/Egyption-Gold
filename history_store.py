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
            return resp.json().get("record", [])
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
