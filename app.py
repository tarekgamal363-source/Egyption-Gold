"""
app.py
------
سيرفر بسيط بيقرا أسعار iSagha ويعرضها كـ API لتطبيقك.

بيشتغل إزاي:
- كل ما حد يفتح الرابط /api/prices، السيرفر بيجيب آخر أسعار.
- عشان مايضغطش على موقع iSagha كتير، بيحتفظ بنسخة (cache) لمدة دقيقة،
  ولو حد فتح التطبيق تاني قبل ما الدقيقة تخلص بياخد نفس النسخة المحفوظة.

الملفات المطلوبة جنب بعض في نفس المجلد:
    app.py               <- الملف ده
    isagha_scraper.py     <- السكريبت اللي عملناه قبل كده
    requirements.txt      <- المكتبات المطلوبة
"""

import os
import time
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from isagha_scraper import get_prices
from bullion_scraper import get_bullion_data, get_bullion_detail
from calendar_scraper import get_calendar
from news_scraper import get_news
from oil_scraper import get_oil_price

app = Flask(__name__)
CORS(app)  # عشان التطبيق يقدر يكلم السيرفر من أي مكان

CACHE_SECONDS = 60
_cache = {"data": None, "timestamp": 0}
_bullion_cache = {"data": None, "timestamp": 0}
BULLION_CACHE_SECONDS = 900  # الصفحة دي بتتحدث أبطأ، فمفيش داعي نقرأها كل دقيقة

_calendar_cache = {"data": None, "timestamp": 0}
CALENDAR_CACHE_SECONDS = 1800  # نصف ساعة

_news_cache = {"data": None, "timestamp": 0}
NEWS_CACHE_SECONDS = 600  # 10 دقايق

_oil_cache = {"data": None, "timestamp": 0}
OIL_CACHE_SECONDS = 300  # 5 دقايق

# ===== ذاكرة تاريخية بسيطة لبناء شموع حقيقية بمرور الوقت =====
# ⚠️ ملاحظة: على خطة Render المجانية، الملف ده ممكن يتمسح لو السيرفر
# اتعمله إعادة تشغيل (redeploy أو نوم لعدم النشاط لفترة طويلة). يعني
# التاريخ هيبدأ من الصفر تاني في الحالة دي، لكن هيفضل يتجمع تلقائيًا
# من غير أي تدخل منك طول ما السيرفر شغال.
HISTORY_FILE = "price_history.json"
MAX_HISTORY_POINTS = 2000


def _load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_snapshot(xau_usd=None, karat21_sell=None, oil_usd=None):
    history = _load_history()
    history.append({
        "ts": time.time(),
        "xau_usd": xau_usd,
        "karat21_sell": karat21_sell,
        "oil_usd": oil_usd,
    })
    history = history[-MAX_HISTORY_POINTS:]
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f)
    except Exception:
        pass


def _build_candles(history, field, bucket_seconds=3600):
    """يجمع النقاط الخام لشموع (OHLC) كل ساعة (أو أي مدة تحددها)"""
    buckets = {}
    for point in history:
        value = point.get(field)
        if value is None:
            continue
        bucket_key = int(point["ts"] // bucket_seconds)
        buckets.setdefault(bucket_key, []).append((point["ts"], value))

    candles = []
    for bucket_key in sorted(buckets.keys()):
        points = sorted(buckets[bucket_key])
        values = [v for _, v in points]
        candles.append({
            "time": bucket_key * bucket_seconds,
            "open": values[0],
            "high": max(values),
            "low": min(values),
            "close": values[-1],
        })
    return candles


@app.route("/")
def home():
    return "Egyptian Gold API شغال ✅ — جرب /api/prices"


@app.route("/api/prices")
def prices():
    now = time.time()
    is_stale = _cache["data"] is None or (now - _cache["timestamp"] > CACHE_SECONDS)

    if is_stale:
        try:
            fresh_data = get_prices()
            _cache["data"] = fresh_data
            _cache["timestamp"] = now
            _save_snapshot(
                xau_usd=(fresh_data.get("gold_ounce_usd") or {}).get("sell"),
                karat21_sell=(fresh_data.get("karat_21") or {}).get("sell"),
            )
        except Exception as e:
            # لو السحب فشل ولسه عندنا نسخة قديمة، هنبعتها بدل ما نرجع خطأ
            if _cache["data"] is not None:
                pass
            else:
                return jsonify({"error": f"تعذر جلب الأسعار: {str(e)}"}), 502

    response = dict(_cache["data"])
    response["cached_at"] = _cache["timestamp"]
    return jsonify(response)


@app.route("/api/bullion")
def bullion():
    now = time.time()
    is_stale = _bullion_cache["data"] is None or (now - _bullion_cache["timestamp"] > BULLION_CACHE_SECONDS)

    if is_stale:
        try:
            fresh_data = get_bullion_data()
            _bullion_cache["data"] = fresh_data
            _bullion_cache["timestamp"] = now
        except Exception as e:
            if _bullion_cache["data"] is not None:
                pass
            else:
                return jsonify({"error": f"تعذر جلب أسعار السبائك: {str(e)}"}), 502

    response = dict(_bullion_cache["data"])
    response["cached_at"] = _bullion_cache["timestamp"]
    return jsonify(response)


@app.route("/api/bullion-detail")
def bullion_detail():
    from flask import request
    kind = request.args.get("kind", "bars")
    weight = request.args.get("weight")
    company = request.args.get("company")
    if not weight or not company:
        return jsonify({"error": "محتاج تحدد weight و company"}), 400
    try:
        data = get_bullion_detail(kind, weight, company)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"تعذر جلب التفاصيل: {str(e)}"}), 502


@app.route("/api/calendar")
def calendar():
    now = time.time()
    is_stale = _calendar_cache["data"] is None or (now - _calendar_cache["timestamp"] > CALENDAR_CACHE_SECONDS)

    if is_stale:
        try:
            fresh_data = get_calendar()
            _calendar_cache["data"] = fresh_data
            _calendar_cache["timestamp"] = now
        except Exception as e:
            if _calendar_cache["data"] is not None:
                pass
            else:
                return jsonify({"error": f"تعذر جلب التقويم الاقتصادي: {str(e)}"}), 502

    response = dict(_calendar_cache["data"])
    response["cached_at"] = _calendar_cache["timestamp"]
    return jsonify(response)


@app.route("/api/news")
def news():
    now = time.time()
    is_stale = _news_cache["data"] is None or (now - _news_cache["timestamp"] > NEWS_CACHE_SECONDS)

    if is_stale:
        try:
            fresh_data = get_news()
            _news_cache["data"] = fresh_data
            _news_cache["timestamp"] = now
        except Exception as e:
            if _news_cache["data"] is not None:
                pass
            else:
                return jsonify({"error": f"تعذر جلب الأخبار: {str(e)}"}), 502

    response = dict(_news_cache["data"])
    response["cached_at"] = _news_cache["timestamp"]
    return jsonify(response)


@app.route("/api/oil")
def oil():
    now = time.time()
    is_stale = _oil_cache["data"] is None or (now - _oil_cache["timestamp"] > OIL_CACHE_SECONDS)

    if is_stale:
        try:
            fresh_data = get_oil_price()
            _oil_cache["data"] = fresh_data
            _oil_cache["timestamp"] = now
            if fresh_data.get("price_usd") is not None:
                _save_snapshot(oil_usd=fresh_data.get("price_usd"))
        except Exception as e:
            if _oil_cache["data"] is not None:
                pass
            else:
                return jsonify({"error": f"تعذر جلب سعر النفط: {str(e)}"}), 502

    response = dict(_oil_cache["data"])
    response["cached_at"] = _oil_cache["timestamp"]
    return jsonify(response)


@app.route("/api/history")
def history():
    field = request.args.get("field", "xau_usd")  # xau_usd أو karat21_sell أو oil_usd
    bucket = int(request.args.get("bucket_seconds", 3600))
    raw = _load_history()
    candles = _build_candles(raw, field, bucket)
    return jsonify({"field": field, "bucket_seconds": bucket, "candles": candles, "points_logged": len(raw)})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
