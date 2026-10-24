"""
oil_scraper.py
---------------
يجيب سعر برنت بالدولار: من API Ninjas أولًا، ولو وقع أو فشل ياخد آخر سعر من biquote.io.

محتاج مفتاح API مجاني:
1. اعمل حساب على https://api-ninjas.com (مجاني، من غير كارت)
2. من الداشبورد بتاعك هتلاقي API Key، انسخه
3. حطه في متغير بيئة (Environment Variable) اسمه OIL_API_KEY في Render:
   Render Dashboard → مشروعك → Environment → Add Environment Variable
   Key: OIL_API_KEY   Value: (المفتاح بتاعك)

المتطلبات:
    pip install requests

الاستخدام:
    from oil_scraper import get_oil_price
    data = get_oil_price()
"""

import os
import requests

API_URL = "https://api.api-ninjas.com/v1/oilprice"


def _from_api_ninjas():
    api_key = os.environ.get("OIL_API_KEY")
    if not api_key:
        raise RuntimeError("OIL_API_KEY غير موجود")
    resp = requests.get(API_URL, headers={"X-Api-Key": api_key}, params={"type": "brent"}, timeout=15)
    if not resp.ok:
        # نظهر رد المصدر نفسه عشان نعرف السبب (مفتاح منتهي؟ حد يومي؟ ...)
        raise RuntimeError(f"API Ninjas {resp.status_code}: {resp.text[:160]}")
    data = resp.json()
    if data.get("price") is None:
        raise RuntimeError("API Ninjas رجّع رد من غير سعر")
    return {
        "name": data.get("name", "Brent Crude Oil"),
        "price_usd": data.get("price"),
        "previous_close": data.get("previous_close"),
        "change_24h": data.get("change_24h"),
        "change_24h_percent": data.get("change_24h_percent"),
        "updated_unix": data.get("updated"),
        "source": "api-ninjas",
    }


def _from_biquote():
    """بديل: آخر سعر برنت من نفس مصدر الشموع (biquote.io) لو API Ninjas وقع"""
    import time
    from candles_source import _resolve_symbol, _fetch_bars
    sym = _resolve_symbol("oil_usd")
    daily = _fetch_bars(sym, "1d", 3)
    if not daily:
        raise RuntimeError("biquote رجّع بيانات فاضية لبرنت")
    try:
        last = _fetch_bars(sym, "5m", 2)
    except Exception:
        last = []
    price = (last[-1] if last else daily[-1])["close"]
    prev = daily[-2]["close"] if len(daily) >= 2 else None
    chg = (price - prev) if prev else None
    return {
        "name": "Brent Crude Oil",
        "price_usd": round(price, 2),
        "previous_close": round(prev, 2) if prev else None,
        "change_24h": round(chg, 2) if chg is not None else None,
        "change_24h_percent": round(chg / prev * 100, 2) if prev else None,
        "updated_unix": int(time.time()),
        "source": "biquote",
    }


def get_oil_price():
    errors = []
    for fn in (_from_api_ninjas, _from_biquote):
        try:
            return fn()
        except Exception as e:
            errors.append(f"{fn.__name__}: {e}")
            print("oil source failed:", errors[-1])
    raise RuntimeError(" | ".join(errors)[:300])


if __name__ == "__main__":
    import json
    print(json.dumps(get_oil_price(), ensure_ascii=False, indent=2))
