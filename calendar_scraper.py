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

import os
import requests
from bls_scraper import get_bls_actuals
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

FEED_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
CAIRO_TZ = ZoneInfo("Africa/Cairo")
NY_TZ = ZoneInfo("America/New_York")

# مواعيد رسمية معلنة مسبقًا من مصادر أمريكا الحكومية نفسها (BLS + الفيدرالي)،
# مش من فيد الأسبوع بس - عشان الصفحة تعرض شهور قدام مش أسبوع واحد بس.
# المصدر: bls.gov/schedule و federalreserve.gov/monetarypolicy/fomccalendars.htm
# ⚠️ الأرقام (forecast/previous) مش متاحة قبل الموعد بوقت طويل، هتظهر لاحقًا لما
# نقرب من التاريخ (من فيد الأسبوع). دلوقتي بيظهر بس الموعد + الشرح.
KNOWN_US_EVENTS = [
    # (الاسم بالعربي, تاريخ ووقت أمريكا الشرقية, نوع الحدث للشرح, الأهمية)
    ("قرار الفائدة الأمريكية (FOMC)", datetime(2026, 9, 16, 14, 0), "fed", "High"),
    ("تقرير الوظائف الأمريكي (Employment Situation)", datetime(2026, 9, 4, 8, 30), "nfp", "High"),
    ("مؤشر أسعار المستهلكين (CPI)", datetime(2026, 9, 11, 8, 30), "cpi", "High"),
    ("مؤشر أسعار المنتجين (PPI)", datetime(2026, 9, 10, 8, 30), "ppi", "Medium"),

    ("تقرير الوظائف الأمريكي (Employment Situation)", datetime(2026, 10, 2, 8, 30), "nfp", "High"),
    ("مؤشر أسعار المستهلكين (CPI)", datetime(2026, 10, 14, 8, 30), "cpi", "High"),
    ("مؤشر أسعار المنتجين (PPI)", datetime(2026, 10, 15, 8, 30), "ppi", "Medium"),
    ("قرار الفائدة الأمريكية (FOMC)", datetime(2026, 10, 28, 14, 0), "fed", "High"),

    ("تقرير الوظائف الأمريكي (Employment Situation)", datetime(2026, 11, 6, 8, 30), "nfp", "High"),
    ("مؤشر أسعار المستهلكين (CPI)", datetime(2026, 11, 10, 8, 30), "cpi", "High"),
    ("مؤشر أسعار المنتجين (PPI)", datetime(2026, 11, 13, 8, 30), "ppi", "Medium"),

    ("تقرير الوظائف الأمريكي (Employment Situation)", datetime(2026, 12, 4, 8, 30), "nfp", "High"),
    ("قرار الفائدة الأمريكية (FOMC)", datetime(2026, 12, 9, 14, 0), "fed", "High"),
    ("مؤشر أسعار المستهلكين (CPI)", datetime(2026, 12, 10, 8, 30), "cpi", "High"),
    ("مؤشر أسعار المنتجين (PPI)", datetime(2026, 12, 15, 8, 30), "ppi", "Medium"),

    # يناير 2027 - موعد الفيدرالي معلن كـ"مبدئي" لسه، ممكن يتغير بفارق يوم أو اتنين
    ("قرار الفائدة الأمريكية (FOMC) - موعد مبدئي", datetime(2027, 1, 27, 14, 0), "fed", "High"),
]

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
    (["non-farm", "nonfarm", "nfp", "employment change", "employment situation", "unemployment claims", "unemployment rate"],
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

# تصنيف كل نوع حدث: هل ارتفاع القيمة عن المتوقع "سلبي" على الذهب (لأنه بيقوي الدولار/يرفع
# احتمال الفائدة) ولا "إيجابي" (لأنه بيدل على ضعف اقتصادي بيدعم الذهب كملاذ آمن)
INVERSE_EVENTS = ["cpi", "consumer price", "ppi", "producer price", "gdp",
                  "retail sales", "pmi", "ism manufacturing", "ism services",
                  "non-farm", "nonfarm", "nfp", "employment change", "employment situation",
                  "consumer confidence", "consumer sentiment", "pce", "personal consumption",
                  "interest rate", "fomc", "fed",
                  "housing starts", "building permits", "industrial production",
                  "capacity utilization", "durable goods", "factory orders",
                  "new home sales", "existing home sales", "pending home sales",
                  "empire state", "philly fed", "philadelphia fed", "chicago pmi",
                  "flash pmi", "michigan consumer sentiment", "leading index",
                  "job openings", "jolts", "adp employment", "adp non-farm",
                  "average hourly earnings", "wage growth", "gdp price index",
                  "core cpi", "core ppi", "core pce", "core retail sales",
                  "business inventories", "wholesale inventories", "construction spending"]
DIRECT_EVENTS = ["unemployment rate", "unemployment claims", "jobless claims",
                 "continuing claims", "challenger job cuts"]


def _event_category(title: str):
    t = title.lower()
    if any(k in t for k in DIRECT_EVENTS):
        return "direct"
    if any(k in t for k in INVERSE_EVENTS):
        return "inverse"
    return None  # مش معروف نوعه، متحطش تفسير تلقائي


def _gold_sentiment(category, comparison):
    """
    comparison: 'up' (القيمة الجديدة أعلى من المرجع) / 'down' (أقل) / 'flat' (زي بعض)
    بترجع (النص, اللون المقترح)
    """
    if category is None or comparison is None:
        return None

    if comparison == "flat":
        return ("حيادي على الذهب - القراءة زي المتوقع تمامًا", "neutral")

    if category == "inverse":
        if comparison == "up":
            return ("سلبي على الذهب - رقم أقوى من المتوقع بيدعم الدولار ويقلل جاذبية الذهب", "negative")
        else:
            return ("إيجابي على الذهب - رقم أضعف من المتوقع بيدعم الذهب كملاذ آمن", "positive")
    else:  # direct
        if comparison == "up":
            return ("إيجابي على الذهب - ضعف أكبر في سوق العمل بيدعم الذهب كملاذ آمن", "positive")
        else:
            return ("سلبي على الذهب - سوق عمل أقوى من المتوقع بيقلل جاذبية الذهب", "negative")


def _scenario_breakdown(category):
    """
    بيرجع الاحتمالات التلاتة الممكنة لأي حدث (زي المتوقع / أقل / أعلى) وتأثير كل واحد
    على الذهب - بغض النظر عن القراءة الفعلية، عشان يبقى مرجع تعليمي واضح لكل حدث.
    """
    if category is None:
        return None

    same = "حيادي - مفيش تأثير كبير متوقع على الذهب"

    if category == "inverse":
        lower = "إيجابي للذهب - رقم أضعف من المتوقع بيدعم الذهب كملاذ آمن"
        higher = "سلبي للذهب - رقم أقوى من المتوقع بيدعم الدولار ويقلل جاذبية الذهب"
    else:  # direct
        lower = "سلبي للذهب - تحسّن أكبر من المتوقع في سوق العمل بيقلل جاذبية الذهب"
        higher = "إيجابي للذهب - ضعف أكبر من المتوقع في سوق العمل بيدعم الذهب كملاذ آمن"

    return {"same": same, "lower": lower, "higher": higher}


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


def _parse_event_datetime(date_str):
    """
    يحاول يقرأ التاريخ الراجع من المصدر بأي صيغة كانت (مش بس ISO)،
    عشان لو المصدر غيّر شكل التاريخ الأحداث متختفيش كلها فجأة.
    """
    if not date_str:
        return None

    # المحاولة 1: صيغة ISO القياسية
    try:
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        pass

    # المحاولة 2: صيغ شائعة تانية للتاريخ والوقت الأمريكي
    common_formats = [
        "%m-%d-%Y %I:%M%p",
        "%m/%d/%Y %I:%M%p",
        "%Y-%m-%d %H:%M:%S",
        "%m-%d-%Y %H:%M",
    ]
    for fmt in common_formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


MANUAL_OVERRIDES_BIN_ID = os.environ.get("CALENDAR_OVERRIDES_BIN_ID")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY")


def load_manual_overrides():
    """نفس _load_manual_overrides بس بإسم عام (public) عشان app.py يقدر يستخدمها"""
    return _load_manual_overrides()


def save_manual_override(date_cairo, title_keyword, fields):
    """
    بيضيف/يعدّل بيانات حدث في الـ Bin ويحفظ.
    fields: dict ممكن يحتوي على أي من: actual, forecast, previous, impact_text, impact_color
    (impact_color: positive / negative / neutral)
    """
    if not (MANUAL_OVERRIDES_BIN_ID and JSONBIN_API_KEY):
        raise RuntimeError("CALENDAR_OVERRIDES_BIN_ID أو JSONBIN_API_KEY مش متظبطين")

    overrides = _load_manual_overrides()
    key = f"{date_cairo}|{title_keyword}"
    existing = overrides.get(key, {})
    if not isinstance(existing, dict):
        existing = {}
    existing.update({k: v for k, v in fields.items() if v not in (None, "")})
    overrides[key] = existing

    resp = requests.put(
        f"https://api.jsonbin.io/v3/b/{MANUAL_OVERRIDES_BIN_ID}",
        headers={"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"},
        json=overrides,
        timeout=10,
    )
    resp.raise_for_status()
    return overrides


def _load_manual_overrides():
    """
    بيقرأ بيانات مُدخلة يدويًا من jsonbin.io (لو متظبطة)، عشان تقدر تكتب
    القيم بإيدك أول ما توصلك من مصادر تانية، من غير ما تستنى المصدر التلقائي.

    شكل البيانات المتوقع في الـ Bin (JSON):
    {
      "2026-09-11|CPI": {"actual": "0.4%", "forecast": "0.3%", "previous": "0.2%",
                          "impact_text": "سلبي على الذهب لأن...", "impact_color": "negative"}
    }
    المفتاح = التاريخ (YYYY-MM-DD) + "|" + جزء من اسم الحدث (يكفي كلمة مميزة منه)
    """
    if not (MANUAL_OVERRIDES_BIN_ID and JSONBIN_API_KEY):
        return {}
    try:
        resp = requests.get(
            f"https://api.jsonbin.io/v3/b/{MANUAL_OVERRIDES_BIN_ID}/latest",
            headers={"X-Master-Key": JSONBIN_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        record = resp.json().get("record", {})
        return record if isinstance(record, dict) else {}
    except Exception:
        return {}


def _find_override(overrides, date_cairo, title):
    title_lower = title.lower()
    for key, value in overrides.items():
        if "|" not in key:
            continue
        key_date, key_keyword = key.split("|", 1)
        if key_date == date_cairo and key_keyword.lower() in title_lower:
            # توافقية مع القيم القديمة (نص بسيط بدل dict)
            if isinstance(value, str):
                return {"actual": value}
            return value if isinstance(value, dict) else None
    return None


def get_calendar(min_impact="Low", countries=("USD",)):
    """
    min_impact: "Low" (كل حاجة) أو "Medium" أو "High" فقط
    countries: قائمة العملات/الدول المطلوبة (افتراضيًا أمريكا فقط لأنها الأكثر تأثيرًا على الذهب)
    """
    raw_events = []
    fetch_debug = []
    # المصدر ده بس عنده صفحة "الأسبوع الحالي" - مفيش صفحة منفصلة لـ"الأسبوع الجاي"
    # (الرابط اللي كنا بنجربه كان غلط أصلاً وبيرجع 404)
    for url in (FEED_URL,):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            items = resp.json()
            raw_events.extend(items)
            fetch_debug.append({"url": url, "status": "ok", "count": len(items)})
        except Exception as exc:
            fetch_debug.append({"url": url, "status": "failed", "error": str(exc)})
            continue

    impact_order = {"Low": 0, "Medium": 1, "High": 2, "Holiday": 0}
    min_level = impact_order.get(min_impact, 0)

    manual_overrides = _load_manual_overrides()

    try:
        bls_actuals = get_bls_actuals()
    except Exception:
        bls_actuals = {}

    now = datetime.now(timezone.utc)
    events = []
    past_events = []

    for e in raw_events:
        if countries and e.get("country") not in countries:
            continue
        if impact_order.get(e.get("impact"), 0) < min_level:
            continue

        dt = _parse_event_datetime(e.get("date"))
        if dt is None:
            continue

        # لو التاريخ الراجع من المصدر من غير فرق توقيت مكتوب (naive)،
        # افترض إنه بتوقيت أمريكا الشرقية (ET) - ده المتعارف عليه في المصدر ده -
        # قبل ما نحوّله لتوقيت مصر، عشان منجيش نحسبه غلط.
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=NY_TZ)

        dt_cairo = dt.astimezone(CAIRO_TZ)

        override = _find_override(manual_overrides, dt_cairo.strftime("%Y-%m-%d"), e.get("title", "")) or {}

        raw_forecast = e.get("forecast") or override.get("forecast")
        raw_previous = e.get("previous") or override.get("previous")
        forecast = _parse_number(raw_forecast)
        previous = _parse_number(raw_previous)

        # لو المصدر الأساسي مش عنده القيمة الفعلية، جرب BLS الرسمي (لمؤشرات محددة بس)
        # ملاحظة: بنطبق ده بس على الأحداث اللي خلصت فعلاً، عشان منحطش رقم الشهر
        # الماضي غلط على حدث لسه ما حصلش
        is_future_check = dt.astimezone(timezone.utc) >= now
        title_for_bls = e.get("title", "")
        bls_value = None
        if not is_future_check:
            if "CPI" in title_for_bls and "Core" not in title_for_bls:
                if "y/y" in title_for_bls:
                    bls_value = bls_actuals.get("cpi_yy")
                elif "m/m" in title_for_bls:
                    bls_value = bls_actuals.get("cpi_mm")
            elif "PPI" in title_for_bls and "Core" not in title_for_bls and "m/m" in title_for_bls:
                bls_value = bls_actuals.get("ppi_mm")
            elif "non-farm" in title_for_bls.lower() or "nonfarm" in title_for_bls.lower() or "employment situation" in title_for_bls.lower():
                bls_value = bls_actuals.get("nfp")
            elif "unemployment rate" in title_for_bls.lower():
                bls_value = bls_actuals.get("unemployment_rate")

        # لو أنت كتبت القيمة الفعلية يدويًا وتوصلنا قبل المصدر التلقائي، بناخد بيها
        # الأولوية: القيمة الأصلية من الفيد > BLS الرسمي > القيمة المكتوبة يدويًا
        raw_actual = e.get("actual") or bls_value or override.get("actual")
        used_manual = bool(override.get("actual")) and not e.get("actual") and not bls_value
        actual = _parse_number(raw_actual)

        trend = None
        if forecast is not None and previous is not None:
            if forecast > previous:
                trend = "up"
            elif forecast < previous:
                trend = "down"
            else:
                trend = "flat"

        category = _event_category(e.get("title", ""))

        base_event = {
            "title": e.get("title"),
            "country": e.get("country"),
            "impact": e.get("impact"),
            "impact_ar": _impact_arabic(e.get("impact")),
            "date_cairo": dt_cairo.strftime("%Y-%m-%d"),
            "time_cairo": dt_cairo.strftime("%H:%M"),
            "weekday_ar": ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"][dt_cairo.weekday()],
            "forecast": raw_forecast,
            "previous": raw_previous,
            "actual": raw_actual,
            "manual_impact_text": override.get("impact_text"),
            "manual_impact_color": override.get("impact_color"),
            "actual_is_manual": used_manual,
            "trend_forecast_vs_previous": trend,
            "explanation": _explain(e.get("title", "")),
            "scenarios": _scenario_breakdown(category),
        }

        is_future = dt.astimezone(timezone.utc) >= now
        if is_future:
            # قبل الحدث: نتوقع التأثير بناءً على العلاقة بين المتوقع والقراءة السابقة
            sentiment = _gold_sentiment(category, trend)
            base_event["expected_gold_impact"] = sentiment[0] if sentiment else None
            events.append(base_event)
        else:
            # بعد الحدث: نحسب التأثير الفعلي بمقارنة النتيجة الفعلية بالمتوقع
            outcome_note = None
            actual_vs_forecast = None
            if actual is not None and forecast is not None:
                if actual > forecast:
                    outcome_note = "جاءت النتيجة الفعلية أعلى من المتوقع"
                    actual_vs_forecast = "higher"
                elif actual < forecast:
                    outcome_note = "جاءت النتيجة الفعلية أقل من المتوقع"
                    actual_vs_forecast = "lower"
                else:
                    outcome_note = "جاءت النتيجة الفعلية مطابقة للمتوقع"
                    actual_vs_forecast = "same"
            else:
                outcome_note = "لسه القيمة الفعلية متاحة، هتظهر تلقائيًا أول ما المصدر ينشرها"

            base_event["outcome_note"] = outcome_note
            base_event["actual_vs_forecast"] = actual_vs_forecast  # same / lower / higher / None
            past_events.append(base_event)

    # شيل التكرار لو نفس الحدث ظهر في الفيدين (نادر لكن ممكن عند حدود الأسبوع)
    def _dedupe(evs):
        seen = set()
        result = []
        for ev in evs:
            key = (ev["title"], ev["date_cairo"], ev["time_cairo"])
            if key not in seen:
                seen.add(key)
                result.append(ev)
        return result

    def _has_any_data(ev):
        """لو الحدث مفيهوش ولا سابق ولا متوقع ولا فعلي، معندوش أي فايدة نعرضه"""
        return bool(ev.get("previous") or ev.get("forecast") or ev.get("actual"))

    unique_events = _dedupe([ev for ev in events if _has_any_data(ev)])
    unique_events.sort(key=lambda x: (x["date_cairo"], x["time_cairo"]))

    unique_past_events = _dedupe([ev for ev in past_events if _has_any_data(ev)])
    unique_past_events.sort(key=lambda x: (x["date_cairo"], x["time_cairo"]), reverse=True)
    unique_past_events = unique_past_events[:15]  # آخر 15 حدث سابق بس

    # ملحوظة: شلنا إضافة "المواعيد المعروفة" البعيدة اللي مفيهاش أي بيانات
    # (لا سابق ولا متوقع ولا فعلي) بناءً على طلبك - مفيش داعي نعرض حدث فاضي.
    unique_events.sort(key=lambda x: (x["date_cairo"], x["time_cairo"]))
    return {
        "source": FEED_URL,
        "timezone": "Africa/Cairo",
        "events": unique_events,
        "past_events": unique_past_events,
        "fetch_debug": fetch_debug,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_calendar(), ensure_ascii=False, indent=2))
