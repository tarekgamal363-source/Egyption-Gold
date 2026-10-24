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
from candles_source import get_candles, _resolve_symbol, _search_brent, BRENT_CANDIDATES

app = Flask(__name__)
CORS(app)  # عشان التطبيق يقدر يكلم السيرفر من أي مكان

# ===== حد للطلبات (حماية بسيطة من الإغراق) =====
# الحد عالي نسبيًا لأن شبكات الموبايل بتخلي ناس كتير يشاركوا نفس الـ IP
_rate = {}
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "300"))
SENSITIVE_LIMIT_PER_MIN = 10


@app.before_request
def _rate_limit():
    path = request.path
    if request.method == "OPTIONS" or not path.startswith("/api/") or path.startswith("/api/cron/"):
        return None
    ip = (request.headers.get("X-Forwarded-For", "").split(",")[0].strip()) or request.remote_addr or "?"
    sensitive = path in ("/api/delete-account", "/api/notify-reply")
    key = (ip, sensitive)
    now = time.time()
    hits = [t for t in _rate.get(key, []) if now - t < 60]
    if len(hits) >= (SENSITIVE_LIMIT_PER_MIN if sensitive else RATE_LIMIT_PER_MIN):
        _rate[key] = hits
        return jsonify({"error": "too_many_requests"}), 429
    hits.append(now)
    _rate[key] = hits
    if len(_rate) > 5000:  # تنظيف الذاكرة
        for k in [k for k, v in _rate.items() if not v or now - v[-1] > 60]:
            _rate.pop(k, None)
    return None


CACHE_SECONDS = 60
_cache = {"data": None, "timestamp": 0}
_bullion_cache = {"data": None, "timestamp": 0}
BULLION_CACHE_SECONDS = 900  # الصفحة دي بتتحدث أبطأ، فمفيش داعي نقرأها كل دقيقة

_calendar_cache = {"data": None, "timestamp": 0}
CALENDAR_CACHE_SECONDS = 120  # دقيقتين - المصدر الجديد (biquote) بيسمح بطلبات كتير، فمفيش داعي نستنى كتير

_news_cache = {"data": None, "timestamp": 0}
NEWS_CACHE_SECONDS = 600  # 10 دقايق

_oil_cache = {"data": None, "timestamp": 0}
OIL_CACHE_SECONDS = 1800  # نص ساعة: النسخة المجانية من المصدر بتحدّث السعر مرة في اليوم أصلًا، وده بيوفر الحد الشهري للطلبات

def _cached(cache, ttl, fn):
    """يرجّع النسخة المحفوظة لو لسه صالحة، وإلا يجيب جديد (ولو فشل يرجّع القديمة)"""
    now = time.time()
    if cache["data"] is None or now - cache["timestamp"] > ttl:
        try:
            cache["data"] = fn()
            cache["timestamp"] = now
        except Exception:
            if cache["data"] is None:
                raise
    return cache["data"]


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


@app.route("/api/oil")
def oil():
    now = time.time()
    is_stale = _oil_cache["data"] is None or (now - _oil_cache["timestamp"] > OIL_CACHE_SECONDS)

    if is_stale:
        try:
            fresh_data = get_oil_price()
            _oil_cache["data"] = fresh_data
            _oil_cache["timestamp"] = now
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
    field = request.args.get("field", "xau_usd")  # xau_usd أو oil_usd
    range_param = request.args.get("range", "day")  # hour / day / week / month / year / 5y
    try:
        return jsonify(get_candles(field, range_param))
    except Exception as e:
        return jsonify({"error": f"تعذر جلب الشموع: {str(e)}", "candles": []}), 502


@app.route("/api/candles-debug")
def candles_debug():
    """للتشخيص: بيعرض رمز برنت اللي اتحدد ونتايج البحث"""
    info = {"candidates": BRENT_CANDIDATES, "search": _search_brent()}
    try:
        info["brent_symbol"] = _resolve_symbol("oil_usd")
    except Exception as e:
        info["brent_symbol"] = None
        info["error"] = str(e)
    return jsonify(info)


@app.route("/api/notify-reply", methods=["POST"])
def notify_reply_route():
    """بيتنادى من لوحة الإدارة بعد الرد: بيتحقق إن اللي بينادي هو صاحب التطبيق فعلًا"""
    import notifications
    data = request.get_json(silent=True) or {}
    token = data.get("id_token")
    cid = data.get("complaint_id")
    if not token or not cid:
        return jsonify({"error": "bad request"}), 400
    try:
        return jsonify(notifications.notify_reply(token, cid))
    except PermissionError:
        return jsonify({"error": "forbidden"}), 403
    except Exception as e:
        print("notify-reply failed:", e)
        return jsonify({"pushed": False, "reason": "error"}), 500


@app.route("/api/delete-account", methods=["POST"])
def delete_account_route():
    """حذف الحساب وكل بيانات المستخدم (مطلوب من جوجل بلاي). المستخدم بيتحقق بالتوكن بتاعه هو بس."""
    import notifications
    data = request.get_json(silent=True) or {}
    token = data.get("id_token")
    if not token:
        return jsonify({"error": "bad request"}), 400
    try:
        return jsonify(notifications.delete_account(token))
    except PermissionError:
        return jsonify({"error": "reauth_required"}), 401
    except Exception as e:
        print("delete-account failed:", type(e).__name__)
        return jsonify({"error": "failed"}), 500


@app.route("/api/cron/notify")
def cron_notify():
    """cron-job.org يناديه كل 5 دقايق: يبعت إشعارات الساعة/قبل الحدث/بعد الحدث"""
    secret = (os.environ.get("CRON_SECRET") or "").strip()
    given = (request.args.get("key") or "").strip()
    if not secret or given != secret:
        # معلومات تشخيص بسيطة (مش بتكشف السر): هل المتغير موجود، وهل الطول متطابق
        return jsonify({"error": "unauthorized", "secret_set": bool(secret),
                        "length_match": bool(secret) and len(given) == len(secret)}), 401
    import notifications
    try:
        if request.args.get("test"):
            r = notifications.send_to_all("🔔 إشعار تجريبي", "الإشعارات شغالة عندك ✅", tag="test")
            return jsonify(r)
        prices_data = oil_data = cal_data = None
        # بنستخدم نفس الكاش بتاع الصفحات عشان الـ cron (كل 5 دقايق) ميستهلكش حد الطلبات عند المصادر
        try: prices_data = _cached(_cache, CACHE_SECONDS, get_prices)
        except Exception as e: print("notify: prices failed", e)
        try: oil_data = _cached(_oil_cache, OIL_CACHE_SECONDS, get_oil_price)
        except Exception as e: print("notify: oil failed", e)
        try: cal_data = _cached(_calendar_cache, CALENDAR_CACHE_SECONDS, get_calendar)
        except Exception as e: print("notify: calendar failed", e)
        res = notifications.run_cycle(prices_data, oil_data, cal_data, force=request.args.get("force"))
        return jsonify({"ok": True, **res})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)[:200]}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
