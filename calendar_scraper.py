"""
calendar_scraper.py
--------------------
يجيب التقويم الاقتصادي من biquote.io - API حقيقي ومجاني (من غير مفتاح)
بيدّي القيمة الفعلية والمتوقعة والسابقة لـ90 يوم فات و90 يوم قدام، بحد
أقصى 15,000 طلب/دقيقة. ده مصدر مباشر (مش استخراج صفحة ويب) فمفيش مشاكل
حظر أو صفحات بتتغير شكلها.

المتطلبات:
    pip install requests

الاستخدام:
    from calendar_scraper import get_calendar
    data = get_calendar()
"""

import requests
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

CALENDAR_URL = "https://biquote.io/api/calendar"
CAIRO_TZ = ZoneInfo("Africa/Cairo")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

WEEKDAYS_AR = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]

# شرح مبسط لكل نوع حدث + سبب تأثيره على الذهب (بحث بالكلمة المفتاحية في اسم الحدث)
EXPLANATIONS = [
    (["cpi", "consumer price", "inflation"],
     "مؤشر التضخم. ارتفاعه عن المتوقع بيرفع احتمال بقاء الفائدة مرتفعة، وده عادة بيضغط على الذهب لأنه أصل مايدرش فايدة."),
    (["non-farm", "nonfarm", "nfp", "payroll", "employment change", "unemployment claims", "unemployment rate", "jobless claims"],
     "بيانات سوق العمل الأمريكي. سوق عمل قوي بيدعم الدولار وبيضغط على الذهب، والعكس صحيح."),
    (["fomc", "fed", "interest rate", "federal funds"],
     "قرار أو تصريحات البنك المركزي الأمريكي بخصوص الفائدة. من أهم الأحداث المؤثرة على الذهب مباشرة."),
    (["gdp"],
     "الناتج المحلي الإجمالي. مؤشر لصحة الاقتصاد الأمريكي ككل، بيأثر على توقعات الفائدة وبالتالي الذهب."),
    (["pce", "personal consumption"],
     "مقياس التضخم المفضل عند البنك المركزي الأمريكي. بيأثر بشكل مباشر على قرارات الفائدة القادمة."),
    (["retail sales"],
     "مبيعات التجزئة. مؤشر على قوة الإنفاق الاستهلاكي، وبالتالي على صحة الاقتصاد وتوقعات الفائدة."),
    (["pmi", "ism manufacturing", "ism services"],
     "مؤشر مديري المشتريات. يعكس نشاط القطاع الصناعي أو الخدمي، ومؤشر مبكر لاتجاه الاقتصاد."),
    (["ppi", "producer price"],
     "مؤشر أسعار المنتجين، مؤشر تضخم مبكر بيسبق أثره أحيانًا مؤشر أسعار المستهلكين (CPI)."),
    (["consumer confidence", "consumer sentiment", "michigan"],
     "مؤشر ثقة المستهلك. بيعكس نظرة الأمريكيين لاقتصادهم، وبيأثر على توقعات الإنفاق والفائدة."),
]
DEFAULT_EXPLANATION = "حدث اقتصادي أمريكي بيتابعه المتداولون لأنه بيأثر على توقعات الفائدة والدولار، وبالتالي على سعر الذهب."

# تصنيف: هل ارتفاع القيمة عن المتوقع "سلبي" على الذهب ولا "إيجابي"
INVERSE_EVENTS = ["cpi", "consumer price", "ppi", "producer price", "gdp",
                  "retail sales", "pmi", "ism manufacturing", "ism services",
                  "non-farm", "nonfarm", "nfp", "payroll", "employment change",
                  "consumer confidence", "consumer sentiment", "michigan",
                  "pce", "personal consumption", "interest rate", "fomc", "fed"]
DIRECT_EVENTS = ["unemployment rate", "unemployment claims", "jobless claims", "continuing claims"]


def _explain(title):
    t = title.lower()
    for keywords, text in EXPLANATIONS:
        if any(k in t for k in keywords):
            return text
    return DEFAULT_EXPLANATION


def _event_category(title):
    t = title.lower()
    if any(k in t for k in DIRECT_EVENTS):
        return "direct"
    if any(k in t for k in INVERSE_EVENTS):
        return "inverse"
    return None


def _scenario_breakdown(category):
    if category is None:
        return None
    same = "حيادي - مفيش تأثير كبير متوقع على الذهب"
    if category == "inverse":
        lower = "إيجابي للذهب - رقم أضعف من المتوقع بيدعم الذهب كملاذ آمن"
        higher = "سلبي للذهب - رقم أقوى من المتوقع بيدعم الدولار ويقلل جاذبية الذهب"
    else:
        lower = "سلبي للذهب - تحسّن أكبر من المتوقع في سوق العمل بيقلل جاذبية الذهب"
        higher = "إيجابي للذهب - ضعف أكبر من المتوقع في سوق العمل بيدعم الذهب كملاذ آمن"
    return {"same": same, "lower": lower, "higher": higher}


def _gold_sentiment_text(category, comparison):
    scenarios = _scenario_breakdown(category)
    if not scenarios or not comparison:
        return None
    return scenarios.get(comparison)


def _format_value(value, unit, multiplier):
    if value is None:
        return None
    if unit == "percent":
        return f"{value:g}%"
    # ملحوظة: الرقم الراجع من المصدر يكون أصلاً بوحدة الـ multiplier
    # (يعني لو multiplier="thousands"، الرقم نفسه ده بالآلاف بالفعل)
    # فمش محتاجين نقسم تاني، بس نضيف الحرف المختصر
    if multiplier == "thousands":
        return f"{value:g}K"
    if multiplier == "millions":
        return f"{value:g}M"
    if multiplier == "billions":
        return f"{value:g}B"
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):,}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def _compare(a, b):
    """بيرجع 'higher'/'lower'/'same' بمقارنة a بـ b"""
    if a is None or b is None:
        return None
    if a > b:
        return "higher"
    if a < b:
        return "lower"
    return "same"


def get_calendar(min_impact="Low", countries=("US",)):
    """
    min_impact: "Low" / "Medium" / "High"
    countries: قائمة أكواد الدول (افتراضيًا أمريكا بس لأنها الأكثر تأثيرًا على الذهب)
    """
    impact_map = {"Low": "low", "Medium": "medium", "High": "high"}
    now_utc = datetime.now(timezone.utc)
    from_date = (now_utc - timedelta(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
    to_date = (now_utc + timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

    params = {
        "from": from_date,
        "to": to_date,
        "countries": ",".join(countries),
        "importance": impact_map.get(min_impact, "low"),
        "limit": 500,
    }

    fetch_debug = []
    try:
        resp = requests.get(CALENDAR_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        raw_events = resp.json()
        fetch_debug.append({"url": resp.url, "status": "ok", "count": len(raw_events)})
    except Exception as exc:
        fetch_debug.append({"url": CALENDAR_URL, "status": "failed", "error": str(exc)})
        raw_events = []

    events = []
    past_events = []

    for e in raw_events:
        if e.get("type") == "holiday":
            continue
        title = e.get("name", "")
        try:
            dt_utc = datetime.fromisoformat(e["time"].replace("Z", "+00:00"))
        except (KeyError, ValueError, TypeError):
            continue
        dt_cairo = dt_utc.astimezone(CAIRO_TZ)

        unit = e.get("unit")
        multiplier = e.get("multiplier")
        actual_val = e.get("actual")
        forecast_val = e.get("forecast")
        previous_val = e.get("previous")

        actual_str = _format_value(actual_val, unit, multiplier)
        forecast_str = _format_value(forecast_val, unit, multiplier)
        previous_str = _format_value(previous_val, unit, multiplier)

        # لو مفيش ولا سابق ولا متوقع ولا فعلي، معندناش أي فايدة نعرض الحدث ده
        if not (actual_str or forecast_str or previous_str):
            continue

        category = _event_category(title)
        # لو النظام مش عارف يحدد نوع الحدث ده أصلاً، معندناش تحليل نقدمه فيه
        if category is None:
            continue

        trend = _compare(forecast_val, previous_val)
        impact_raw = (e.get("importance") or "low").capitalize()

        base_event = {
            "title": title,
            "country": e.get("currency", e.get("countryCode", "")),
            "impact": impact_raw,
            "impact_ar": {"High": "عالي", "Medium": "متوسط", "Low": "منخفض"}.get(impact_raw, impact_raw),
            "date_cairo": dt_cairo.strftime("%Y-%m-%d"),
            "time_cairo": dt_cairo.strftime("%H:%M"),
            "weekday_ar": WEEKDAYS_AR[dt_cairo.weekday()],
            "forecast": forecast_str,
            "previous": previous_str,
            "actual": actual_str,
            "actual_is_manual": False,
            "trend_forecast_vs_previous": {"higher": "up", "lower": "down", "same": "flat"}.get(trend),
            "explanation": _explain(title),
            "scenarios": _scenario_breakdown(category),
            "manual_impact_text": None,
            "manual_impact_color": None,
        }

        is_future = dt_utc >= now_utc
        if is_future:
            expected = {"higher": "up", "lower": "down", "same": "flat"}.get(trend)
            base_event["expected_gold_impact"] = _gold_sentiment_text(category, trend)
            events.append(base_event)
        else:
            actual_vs_forecast = _compare(actual_val, forecast_val)
            outcome_map = {
                "higher": "جاءت النتيجة الفعلية أعلى من المتوقع",
                "lower": "جاءت النتيجة الفعلية أقل من المتوقع",
                "same": "جاءت النتيجة الفعلية مطابقة للمتوقع",
            }
            base_event["outcome_note"] = (
                outcome_map.get(actual_vs_forecast)
                if actual_vs_forecast
                else ("لسه القيمة الفعلية متاحة، هتظهر تلقائيًا أول ما تتنشر" if not actual_str else None)
            )
            base_event["actual_vs_forecast"] = actual_vs_forecast
            past_events.append(base_event)

    events.sort(key=lambda x: (x["date_cairo"], x["time_cairo"]))
    past_events.sort(key=lambda x: (x["date_cairo"], x["time_cairo"]), reverse=True)
    past_events = past_events[:20]

    return {
        "source": CALENDAR_URL,
        "timezone": "Africa/Cairo",
        "events": events,
        "past_events": past_events,
        "fetch_debug": fetch_debug,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_calendar(), ensure_ascii=False, indent=2))
