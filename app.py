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
from flask import Flask, jsonify
from flask_cors import CORS
from isagha_scraper import get_prices
from bullion_scraper import get_bullion_data, get_bullion_detail
from calendar_scraper import get_calendar
from news_scraper import get_news

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
