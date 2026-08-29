"""
calendar_scraper.py
--------------------
يجيب التقويم الاقتصادي الحقيقي (تقارير وقرارات أمريكا بشكل أساسي)
من مصدر عام مجاني (ForexFactory feed)، ويحوّل التوقيت لتوقيت مصر،
ويضيف شرح مبسط لكل حدث وأهميته بالنسبة للذهب.

⚠️ ملاحظة مهمة:
هذا المصدر مجاني وعام، لكنه بيدّي بس "القراءة السابقة" لكل حدث (مش آخر 5 قراءات).
لعمل "آخر 5 قراءات واتجاه عام" حقيقي، محتاجين مصدر مدفوع (زي Trading Economics)
أو نبني قاعدة بيانات بتخزن كل قراءة بنفسنا أسبوع بعد أسبوع لحد ما تتجمع 5 قراءات.

المتطلبات:
    pip install requests

الاستخدام:
    from calendar_scraper import get_calendar
    data = get_calendar()
"""

import requests
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
FEED_URL_NEXT = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
CAIRO_TZ = ZoneInfo("Africa/Cairo")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

# شرح مبسط لكل نوع حدث + سبب تأثيره على الذهب (بحث بالكلمة المفتاحية في اسم الحدث)
EXPLANATIONS = [
    (["cpi", "consumer price index", "inflation"],
     "مؤشر التضخم. ارتفاعه عن المتوقع بيرفع احتمال بقاء الفائدة مرتفعة، وده عادة بيضغط على الذهب لأنه أصل مايدرش فايدة."),
    (["non-farm", "nonfarm", "nfp", "employment change", "unemployment claims", "unemployment rate"],
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
    (["consumer confidence", "consumer sentiment"],
     "مؤشر ثقة المستهلك. بيعكس نظرة الأمريكيين لاقتصادهم، وبيأثر على توقعات الإنفاق والفائدة."),
]

DEFAULT_EXPLANATION = "حدث اقتصادي أمريكي مهم بيتابعه المتداولون لأنه بيأثر على توقعات الفائدة والدولار، وبالتالي على سعر الذهب."


def _explain(title: str) -> str:
    t = title.lower()
    for keywords, text in EXPLANATIONS:
        if any(k in t for k in keywords):
            return text
    return DEFAULT_EXPLANATION


def _parse_number(s):
    if not s:
        return None
    s = str(s).replace("%", "").replace("K", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def _impact_arabic(impact: str) -> str:
    mapping = {
        "High": "عالي",
        "Medium": "متوسط",
        "Low": "منخفض",
        "Holiday": "إجازة",
    }
    return mapping.get(impact, impact or "غير محدد")


def get_calendar(min_impact="Low", countries=("USD",)):
    """
    min_impact: "Low" (كل حاجة) أو "Medium" أو "High" فقط
    countries: قائمة العملات/الدول المطلوبة (افتراضيًا أمريكا فقط لأنها الأكثر تأثيرًا على الذهب)
    """
    raw_events = []
    # نجيب أسبوع بعد أسبوع (نيوزويك) عشان لو دلوقتي ويكند ومفيش أحداث باقية
    # في أسبوع النهارده، الصفحة متبقاش فاضية
    for url in (FEED_URL, FEED_URL_NEXT):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            raw_events.extend(resp.json())
        except Exception:
            continue

    impact_order = {"Low": 0, "Medium": 1, "High": 2, "Holiday": 0}
    min_level = impact_order.get(min_impact, 0)

    now = datetime.now(timezone.utc)
    events = []

    for e in raw_events:
        if countries and e.get("country") not in countries:
            continue
        if impact_order.get(e.get("impact"), 0) < min_level:
            continue

        try:
            dt = datetime.fromisoformat(e["date"])
        except (KeyError, ValueError, TypeError):
            continue

        dt_cairo = dt.astimezone(CAIRO_TZ)
        if dt.astimezone(timezone.utc) < now:
            continue  # نعرض الأحداث القادمة بس (من الأقرب للأبعد)

        forecast = _parse_number(e.get("forecast"))
        previous = _parse_number(e.get("previous"))
        trend = None
        if forecast is not None and previous is not None:
            if forecast > previous:
                trend = "up"
            elif forecast < previous:
                trend = "down"
            else:
                trend = "flat"

        events.append({
            "title": e.get("title"),
            "country": e.get("country"),
            "impact": e.get("impact"),
            "impact_ar": _impact_arabic(e.get("impact")),
            "date_cairo": dt_cairo.strftime("%Y-%m-%d"),
            "time_cairo": dt_cairo.strftime("%H:%M"),
            "weekday_ar": ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"][dt_cairo.weekday()],
            "forecast": e.get("forecast"),
            "previous": e.get("previous"),
            "actual": e.get("actual"),
            "trend_forecast_vs_previous": trend,
            "explanation": _explain(e.get("title", "")),
        })

    # شيل التكرار لو نفس الحدث ظهر في الفيدين (نادر لكن ممكن عند حدود الأسبوع)
    seen = set()
    unique_events = []
    for ev in events:
        key = (ev["title"], ev["date_cairo"], ev["time_cairo"])
        if key not in seen:
            seen.add(key)
            unique_events.append(ev)

    unique_events.sort(key=lambda x: (x["date_cairo"], x["time_cairo"]))
    return {"source": FEED_URL, "timezone": "Africa/Cairo", "events": unique_events}


if __name__ == "__main__":
    import json
    print(json.dumps(get_calendar(), ensure_ascii=False, indent=2))
