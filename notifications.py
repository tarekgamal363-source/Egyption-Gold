"""
notifications.py
----------------
إشعارات Push (Firebase Cloud Messaging) مربوطة بحسابات المستخدمين:
1) رسالة كل ساعة: سعر الذهب العالمي + عيار 21 في مصر + برنت + اتجاه (صاعد/هابط)
2) تنبيه قبل الحدث الاقتصادي المهم بـ 15 دقيقة
3) إشعار بعد الحدث أول ما النتيجة الفعلية تظهر

التشغيل: cron-job.org يستدعي /api/cron/notify?key=... كل 5 دقايق (السيرفر نفسه بينام فمفيش جدولة داخلية).
الحالة (إيه اللي اتبعت قبل كده) محفوظة في Firestore فمفيش تكرار حتى لو السيرفر اتعمل له Restart.

متغيرات البيئة على Render:
    FIREBASE_SERVICE_ACCOUNT  محتوى ملف الـ JSON بتاع Service Account (كله كنص)
    CRON_SECRET               أي كلمة سر طويلة تختارها (تحمي رابط الـ cron)
    QUIET_HOURS (اختياري)     افتراضي "0-7" = مفيش رسايل الساعة من 12 بالليل لـ 8 الصبح بتوقيت مصر
"""

import os
import json
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

CAIRO = ZoneInfo("Africa/Cairo")

_app = None
_db = None


def _init():
    global _app, _db
    if _db is not None:
        return _db
    import firebase_admin
    from firebase_admin import credentials, firestore
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not raw:
        raise RuntimeError("FIREBASE_SERVICE_ACCOUNT غير موجود في Environment على Render")
    info = json.loads(raw)
    _app = firebase_admin.initialize_app(credentials.Certificate(info))
    _db = firestore.client()
    return _db


def _subscribers():
    db = _init()
    docs = db.collection("push_subscribers").where("enabled", "==", True).stream()
    out = []
    for d in docs:
        x = d.to_dict() or {}
        if x.get("token"):
            out.append((d.id, x["token"]))
    return out


def send_to_all(title, body, tag="eg-gold", url="./"):
    """يبعت لكل المشتركين، ويقفل اشتراك أي توكن مات"""
    from firebase_admin import messaging
    subs = _subscribers()
    if not subs:
        return {"sent": 0, "failed": 0, "subscribers": 0}
    db = _init()
    sent = failed = 0
    for i in range(0, len(subs), 500):
        chunk = subs[i:i + 500]
        msgs = [
            messaging.Message(
                token=tok,
                data={"title": title, "body": body, "tag": tag, "url": url},
                webpush=messaging.WebpushConfig(headers={"Urgency": "high", "TTL": "3600"}),
            )
            for _, tok in chunk
        ]
        resp = messaging.send_each(msgs)
        for (uid, _), r in zip(chunk, resp.responses):
            if r.success:
                sent += 1
            else:
                failed += 1
                name = type(r.exception).__name__ if r.exception else ""
                if name in ("UnregisteredError", "SenderIdMismatchError", "InvalidArgumentError"):
                    db.collection("push_subscribers").document(uid).set({"enabled": False}, merge=True)
    return {"sent": sent, "failed": failed, "subscribers": len(subs)}


# ---------- الحالة ----------
def _load_state():
    db = _init()
    snap = db.collection("notify_state").document("main").get()
    return snap.to_dict() if snap.exists else {}


def _save_state(state):
    db = _init()
    for k in ("sent_pre", "sent_post"):
        state[k] = (state.get(k) or [])[-300:]
    db.collection("notify_state").document("main").set(state)


def _arrow(new, old):
    if new is None or old is None:
        return ""
    if new > old:
        return " 🔼"
    if new < old:
        return " 🔽"
    return " ▫️"


def _fmt(n, d=0):
    try:
        return f"{float(n):,.{d}f}"
    except (TypeError, ValueError):
        return "—"


def _quiet_now(now):
    spec = os.environ.get("QUIET_HOURS", "0-7")
    try:
        a, b = [int(x) for x in spec.split("-")]
    except ValueError:
        return False
    return a <= now.hour <= b


def _event_dt(e):
    try:
        return datetime.strptime(f"{e['date_cairo']} {e['time_cairo']}", "%Y-%m-%d %H:%M").replace(tzinfo=CAIRO)
    except Exception:
        return None


def run_cycle(prices=None, oil=None, calendar=None, force=None):
    """بتتنادى كل 5 دقايق. بترجع ملخص صغير."""
    now = datetime.now(CAIRO)
    state = _load_state()
    summary = {"hourly": False, "pre": 0, "post": 0}

    # 1) رسالة الساعة
    hour_key = now.strftime("%Y-%m-%d %H")
    if (force == "hourly" or (state.get("last_hourly") != hour_key and not _quiet_now(now))) and prices:
        gold = (prices.get("gold_ounce_usd") or {}).get("sell")
        k21 = (prices.get("karat_21") or {}).get("sell")
        oil_p = (oil or {}).get("price_usd")
        gold_line = f"🪙 الذهب العالمي {_fmt(gold, 1)}$" + _arrow(gold, state.get("last_gold"))
        k21_line = f"🇪🇬 عيار 21: {_fmt(k21)} ج"
        if oil_p is not None:
            chg = (oil or {}).get("change_24h_percent")
            oil_arrow = _arrow(oil_p, state.get("last_oil")) or (" 🔼" if (chg or 0) > 0 else " 🔽" if (chg or 0) < 0 else "")
            oil_line = f"🛢️ برنت {_fmt(oil_p, 2)}$" + oil_arrow
        else:
            oil_line = ""
        body = " · ".join(x for x in (gold_line, k21_line, oil_line) if x)
        send_to_all("أسعار الساعة — Egyptian Gold", body, tag="hourly")
        state.update({"last_hourly": hour_key, "last_gold": gold, "last_oil": oil_p})
        summary["hourly"] = True

    if calendar:
        # 2) قبل الحدث بـ 15 دقيقة (الأحداث عالية التأثير بس)
        sent_pre = state.get("sent_pre") or []
        for e in calendar.get("events", []):
            if e.get("impact") != "High":
                continue
            dt = _event_dt(e)
            if not dt:
                continue
            mins = (dt - now).total_seconds() / 60
            key = f"{e['date_cairo']}|{e['time_cairo']}|{e['title']}"
            if 0 < mins <= 15 and key not in sent_pre:
                body = f"{e['title']} الساعة {e['time_cairo']} بتوقيت مصر"
                if e.get("forecast"):
                    body += f" · المتوقع: {e['forecast']}"
                if e.get("previous"):
                    body += f" · السابق: {e['previous']}"
                send_to_all("⏰ حدث مهم بعد 15 دقيقة", body, tag="pre")
                sent_pre.append(key)
                summary["pre"] += 1
        state["sent_pre"] = sent_pre

        # 3) بعد الحدث: أول ما النتيجة الفعلية تظهر
        sent_post = state.get("sent_post") or []
        for e in calendar.get("past_events", []):
            if e.get("impact") != "High" or not e.get("actual"):
                continue
            dt = _event_dt(e)
            if not dt or (now - dt) > timedelta(hours=3):
                continue
            key = f"{e['date_cairo']}|{e['time_cairo']}|{e['title']}"
            if key in sent_post:
                continue
            body = f"{e['title']} — الفعلي: {e['actual']}"
            if e.get("forecast"):
                body += f" · المتوقع: {e['forecast']}"
            if e.get("outcome_note"):
                body += f"\n{e['outcome_note']}"
            send_to_all("📢 نتيجة حدث مهم ظهرت", body, tag="post")
            sent_post.append(key)
            summary["post"] += 1
        state["sent_post"] = sent_post

    _save_state(state)
    return summary
