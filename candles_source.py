"""
candles_source.py
-----------------
شموع حقيقية ومستمرة (OHLC: فتح / أعلى / أقل / قفل) للذهب (XAUUSD) وبرنت من biquote.io
- مصدر مجاني بدون مفتاح، بيانات بتتحدث لحظيًا، فمفيش تسجيل ذاتي ولا قاعدة بيانات.
- المدى: ساعة / يوم / أسبوع / شهر / سنة / 5 سنين (الشموع الأكبر بتتجمع من اليومي).

الاستخدام:
    from candles_source import get_candles
    get_candles("xau_usd", "day")
"""

import os
import time
from datetime import datetime, timezone

import requests

BASE = "https://biquote.io/api"
HEADERS = {"User-Agent": "Mozilla/5.0 EgyptianGold/1.0", "Accept": "application/json"}

GOLD_SYMBOL = "XAUUSD"
# رموز برنت المحتملة في فيدات MT5 - بنجرب بالترتيب ونحفظ أول واحد يشتغل
BRENT_CANDIDATES = ["UKOIL", "BRENT", "XBRUSD", "UKBRENT", "BRENTCMDUSD", "BCOUSD", "UKOILRoll"]

# range -> (interval, عدد الشموع المطلوبة من المصدر, تجميع: None / "week" / "month", عدد الشموع المعروضة)
RANGES = {
    "hour":  ("5m", 12, None, 12),     # آخر ساعة، كل شمعة 5 دقايق
    "day":   ("30m", 48, None, 48),    # آخر 24 ساعة، كل شمعة نص ساعة
    "week":  ("4h", 42, None, 42),     # آخر أسبوع، كل شمعة 4 ساعات
    "month": ("1d", 30, None, 30),     # آخر شهر، كل شمعة يوم
    "year":  ("1d", 400, "week", 53),  # آخر سنة، كل شمعة أسبوع
    "5y":    ("1d", 1000, "month", 60) # أقصى ما يتيحه المصدر، كل شمعة شهر
}

_cache = {}          # (field, range) -> {"data":..., "ts":...}
_symbol_cache = {}   # field -> symbol
CACHE_TTL = {"hour": 30, "day": 60, "week": 300, "month": 600, "year": 3600, "5y": 3600}


def _to_unix(v):
    """يحول openTime (ملي ثانية / ثواني / نص ISO) لثواني Unix"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v / 1000) if v > 1e11 else int(v)
    s = str(v).strip()
    if s.isdigit():
        return _to_unix(int(s))
    try:
        s = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _fetch_bars(symbol, interval, limit):
    r = requests.get(f"{BASE}/{symbol}/ohlc", params={"interval": interval, "limit": limit},
                     headers=HEADERS, timeout=20)
    r.raise_for_status()
    data = r.json()
    bars = data.get("bars") if isinstance(data, dict) else data
    out = []
    for b in bars or []:
        t = _to_unix(b.get("openTime") or b.get("time"))
        try:
            o, h, l, c = float(b["open"]), float(b["high"]), float(b["low"]), float(b["close"])
        except (KeyError, TypeError, ValueError):
            continue
        if t is None:
            continue
        out.append({"time": t, "open": o, "high": h, "low": l, "close": c})
    out.sort(key=lambda x: x["time"])  # المصدر بيرجع الأحدث الأول
    return out


def _search_brent():
    """يدور في قائمة رموز biquote على أي رمز برنت"""
    found = []
    for q in ("brent", "ukoil", "oil"):
        try:
            r = requests.get(f"{BASE}/symbols/search", params={"q": q}, headers=HEADERS, timeout=15)
            r.raise_for_status()
            d = r.json()
            items = d if isinstance(d, list) else (d.get("symbols") or d.get("results") or d.get("data") or [])
            for it in items:
                if isinstance(it, str):
                    name, desc = it, ""
                else:
                    name = it.get("symbol") or it.get("name") or ""
                    desc = str(it.get("description") or it.get("desc") or "")
                blob = f"{name} {desc}".upper()
                if "BRENT" in blob or "UKO" in blob:
                    found.append(name)
        except Exception:
            continue
    return found


def _resolve_symbol(field):
    if field == "xau_usd":
        return GOLD_SYMBOL
    if field in _symbol_cache:
        return _symbol_cache[field]
    candidates = []
    env = os.environ.get("BRENT_SYMBOL")
    if env:
        candidates.append(env)
    candidates += BRENT_CANDIDATES
    tried = set()
    for sym in candidates + _search_brent():
        if sym in tried:
            continue
        tried.add(sym)
        try:
            if _fetch_bars(sym, "1d", 3):
                _symbol_cache[field] = sym
                return sym
        except Exception:
            continue
    raise RuntimeError("تعذر إيجاد رمز برنت في المصدر (جرب /api/candles-debug)")


def _aggregate(bars, mode):
    """تجميع شموع يومية لأسبوعية أو شهرية"""
    buckets = {}
    for b in bars:
        dt = datetime.fromtimestamp(b["time"], timezone.utc)
        if mode == "week":
            iso = dt.isocalendar()
            key = (iso[0], iso[1])
        else:
            key = (dt.year, dt.month)
        buckets.setdefault(key, []).append(b)
    out = []
    for key in sorted(buckets):
        g = buckets[key]
        out.append({
            "time": g[0]["time"],
            "open": g[0]["open"],
            "high": max(x["high"] for x in g),
            "low": min(x["low"] for x in g),
            "close": g[-1]["close"],
        })
    return out


def get_candles(field, range_param):
    if field not in ("xau_usd", "oil_usd"):
        raise ValueError("field غير مدعوم")
    if range_param not in RANGES:
        range_param = "day"
    key = (field, range_param)
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached["ts"] < CACHE_TTL[range_param]:
        return cached["data"]

    interval, limit, agg, show = RANGES[range_param]
    try:
        symbol = _resolve_symbol(field)
        bars = _fetch_bars(symbol, interval, limit)
        if agg:
            bars = _aggregate(bars, agg)
        bars = bars[-show:]
        data = {
            "field": field, "range": range_param, "symbol": symbol, "interval": interval,
            "aggregated": agg, "candles": bars, "source": "biquote.io",
        }
    except Exception:
        if cached:  # لو المصدر وقع لحظيًا نستخدم آخر نسخة ناجحة
            return cached["data"]
        raise
    _cache[key] = {"data": data, "ts": now}
    return data
