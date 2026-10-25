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
            out.append((d.id, x["token"], x.get("platform") or "web"))
    return out


def _build_message(token, platform, title, body, tag, url, ttl=3600):
    """رسالة مناسبة لنوع الجهاز: ويب (data فقط) أو تطبيق أندرويد (notification جاهزة)"""
    from firebase_admin import messaging
    from datetime import timedelta
    if platform == "android":
        return messaging.Message(
            token=token,
            notification=messaging.Notification(title=title, body=body),
            data={"url": url, "tag": tag},
            android=messaging.AndroidConfig(
                priority="high",
                ttl=timedelta(seconds=ttl),
                notification=messaging.AndroidNotification(
                    channel_id="default", tag=tag, color="#D4A94C",
                ),
            ),
        )
    return messaging.Message(
        token=token,
        data={"title": title, "body": body, "tag": tag, "url": url},
        webpush=messaging.WebpushConfig(headers={"Urgency": "high", "TTL": str(ttl)}),
    )


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
        msgs = [_build_message(tok, plat, title, body, tag, url, 3600) for _, tok, plat in chunk]
        resp = messaging.send_each(msgs)
        for (uid, _, _p), r in zip(chunk, resp.responses):
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
    """▲ صاعد / ▼ هابط / ▬ ثابت (بالمقارنة بآخر رسالة ساعة)"""
    if new is None or old is None:
        return ""
    if new > old:
        return " ▲"
    if new < old:
        return " ▼"
    return " ▬"


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


_IMPACT_RANK = {"Low": 1, "Medium": 2, "High": 3}
_IMPACT_EMOJI = {"High": "🔴", "Medium": "🟠", "Low": "🟡"}


def _split_scenario(text):
    """'سلبي للذهب - السبب...' -> ('سلبي للذهب', 'السبب...')"""
    if not text:
        return "", ""
    head, _, tail = text.partition(" - ")
    return head.strip(), tail.strip()


def _verdict_icon(head):
    if head.startswith("إيجابي"):
        return "📈"
    if head.startswith("سلبي"):
        return "📉"
    return "➖"


def _pre_message(e):
    em = _IMPACT_EMOJI.get(e.get("impact"), "")
    title = f"⏰ بعد 15 دقيقة {em} {e['title']}"
    lines = [e.get("explanation") or ""]
    nums = []
    if e.get("forecast"):
        nums.append(f"المتوقع: {e['forecast']}")
    if e.get("previous"):
        nums.append(f"السابق: {e['previous']}")
    if nums:
        lines.append(" · ".join(nums))
    sc = e.get("scenarios")
    ref = "السابق" if e.get("comparison_basis") == "previous" else "المتوقع"
    if sc and e.get("comparison_basis"):
        lines.append("تأثيره على الذهب حسب النتيجة:")
        for key, label in (("higher", f"أعلى من {ref}"), ("lower", f"أقل من {ref}")):
            head, _ = _split_scenario(sc.get(key))
            lines.append(f"{_verdict_icon(head)} {label}: {head}")
        if ref == "السابق":
            lines.append("(مفيش رقم متوقع رسمي، فالمقارنة بالسابق وتقديرها أقل دقة)")
        else:
            lines.append("(التأثير بيتحدد بالنتيجة الفعلية مقارنة بالمتوقع، مش بالرقم نفسه)")
    else:
        lines.append("مفيش رقم متوقع ولا سابق للحدث ده، فتأثيره بيتحدد بعد ظهور النتيجة.")
    return title, "\n".join(x for x in lines if x)


def _post_message(e):
    em = _IMPACT_EMOJI.get(e.get("impact"), "")
    title = f"📢 نتيجة {em} {e['title']}"
    lines = []
    nums = [f"الفعلي: {e['actual']}"]
    if e.get("forecast"):
        nums.append(f"المتوقع: {e['forecast']}")
    if e.get("previous"):
        nums.append(f"السابق: {e['previous']}")
    lines.append(" · ".join(nums))
    cmp_ = e.get("actual_vs_forecast")
    sc = e.get("scenarios")
    ref = "السابق" if e.get("comparison_basis") == "previous" else "المتوقع"
    if cmp_ and sc and e.get("comparison_basis"):
        when = {"higher": f"أعلى من {ref}", "lower": f"أقل من {ref}", "same": f"مطابقة لـ{ref}"}[cmp_]
        head, reason = _split_scenario(sc.get(cmp_))
        lines.append(f"النتيجة {when} → {_verdict_icon(head)} {head}")
        if reason:
            lines.append(reason)
        if ref == "السابق":
            lines.append("(مفيش رقم متوقع رسمي، فالمقارنة بالسابق وتقديرها أقل دقة)")
    else:
        lines.append("مفيش رقم نقارن بيه، فمقدرش أحدد تأثيره على الذهب بدقة.")
    return title, "\n".join(lines)


def run_cycle(prices=None, oil=None, calendar=None, force=None):
    """بتتنادى كل 5 دقايق. بترجع ملخص صغير."""
    now = datetime.now(CAIRO)
    state = _load_state()
    summary = {"hourly": False, "pre": 0, "post": 0}

    # 1) رسالة الساعة
    hour_key = now.strftime("%Y-%m-%d %H")
    if (force == "hourly" or (state.get("last_hourly") != hour_key and not _quiet_now(now))) and prices:
        def _sell(key):
            return (prices.get(key) or {}).get("sell")
        gold = _sell("gold_ounce_usd")
        k24 = _sell("karat_24")
        k21 = _sell("karat_21")
        usd = _sell("usd_official")
        oil_p = (oil or {}).get("price_usd")
        def _item(label, val, digits, unit, last):
            if val is None:
                return None
            return f"{label} {_fmt(val, digits)}{unit}" + _arrow(val, last)

        row1 = [_item("🪙 الذهب العالمي", gold, 1, "$", state.get("last_gold")),
                _item("🛢️ برنت", oil_p, 2, "$", state.get("last_oil"))]
        row2 = [_item("عيار 24", k24, 0, " ج", state.get("last_k24")),
                _item("عيار 21", k21, 0, " ج", state.get("last_k21"))]
        row3 = [_item("💵 الدولار", usd, 2, " ج", state.get("last_usd"))]
        rows = [" | ".join(x for x in r if x) for r in (row1, row2, row3)]
        body = "\n".join(r for r in rows if r)
        send_to_all("أسعار الساعة — Egyptian Gold", body, tag="hourly")
        for k, v in (("last_gold", gold), ("last_k24", k24), ("last_k21", k21), ("last_oil", oil_p), ("last_usd", usd)):
            if v is not None:
                state[k] = v
        state["last_hourly"] = hour_key
        summary["hourly"] = True

    if calendar:
        min_rank = _IMPACT_RANK.get(os.environ.get("NOTIFY_MIN_IMPACT", "Low"), 1)

        # 2) قبل كل حدث بـ 15 دقيقة: الحدث + شرحه + تأثيره على الذهب (حسب النتيجة مقابل المتوقع)
        sent_pre = state.get("sent_pre") or []
        for e in calendar.get("events", []):
            if _IMPACT_RANK.get(e.get("impact"), 1) < min_rank:
                continue
            dt = _event_dt(e)
            if not dt:
                continue
            mins = (dt - now).total_seconds() / 60
            key = f"{e['date_cairo']}|{e['time_cairo']}|{e['title']}"
            if 0 < mins <= 15 and key not in sent_pre:
                title, body = _pre_message(e)
                send_to_all(title, body, tag="pre-" + key[-40:])
                sent_pre.append(key)
                summary["pre"] += 1
        state["sent_pre"] = sent_pre

        # 3) بعد الحدث: أول ما النتيجة الفعلية تظهر + تأثيرها الفعلي على الذهب
        sent_post = state.get("sent_post") or []
        for e in calendar.get("past_events", []):
            if _IMPACT_RANK.get(e.get("impact"), 1) < min_rank or not e.get("actual"):
                continue
            dt = _event_dt(e)
            if not dt or (now - dt) > timedelta(hours=3):
                continue
            key = f"{e['date_cairo']}|{e['time_cairo']}|{e['title']}"
            if key in sent_post:
                continue
            title, body = _post_message(e)
            send_to_all(title, body, tag="post-" + key[-40:])
            sent_post.append(key)
            summary["post"] += 1
        state["sent_post"] = sent_post

    _save_state(state)
    return summary


def notify_reply(id_token, complaint_id):
    """صاحب التطبيق رد على رسالة → إشعار للمستخدم صاحب الرسالة (لو مفعّل الإشعارات)"""
    from firebase_admin import auth as fb_auth, messaging
    _init()
    decoded = fb_auth.verify_id_token(id_token)
    admin_uid = os.environ.get("ADMIN_UID", "z8Qsa9itzKTZu6IbKau8BDUUbdt2")
    if decoded.get("uid") != admin_uid:
        raise PermissionError("not admin")
    db = _init()
    snap = db.collection("complaints").document(complaint_id).get()
    if not snap.exists:
        return {"pushed": False, "reason": "not_found"}
    c = snap.to_dict() or {}
    reply = (c.get("reply") or "").strip()
    uid = c.get("uid")
    if not reply or not uid:
        return {"pushed": False, "reason": "no_reply"}
    sub = db.collection("push_subscribers").document(uid).get()
    sd = sub.to_dict() if sub.exists else None
    if not sd or not sd.get("enabled") or not sd.get("token"):
        return {"pushed": False, "reason": "not_subscribed"}
    preview = reply if len(reply) <= 140 else reply[:137] + "..."
    try:
        messaging.send(_build_message(
            sd["token"], sd.get("platform") or "web",
            "💬 وصلك رد على رسالتك", preview, "reply-" + complaint_id[:20], "./", 86400,
        ))
        return {"pushed": True}
    except Exception as e:
        return {"pushed": False, "reason": type(e).__name__}


def delete_account(id_token):
    """حذف حساب المستخدم وكل بياناته (مطلوب من جوجل بلاي).
    لازم يكون سجّل دخول من أقل من 10 دقايق (إعادة مصادقة) عشان نحمي الحساب لو التوكن اتسرق."""
    from firebase_admin import auth as fb_auth
    _init()
    decoded = fb_auth.verify_id_token(id_token)
    uid = decoded.get("uid")
    if not uid:
        raise ValueError("bad token")
    if time.time() - int(decoded.get("auth_time", 0)) > 600:
        raise PermissionError("reauth_required")
    db = _init()
    db.collection("push_subscribers").document(uid).delete()
    deleted_msgs = 0
    for d in db.collection("complaints").where("uid", "==", uid).stream():
        d.reference.delete()
        deleted_msgs += 1
    fb_auth.delete_user(uid)
    return {"deleted": True, "messages_deleted": deleted_msgs}
