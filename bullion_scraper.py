"""
bullion_scraper.py
-------------------
يقرأ صفحة مقارنة أسعار السبائك من sabayekegypt.com
ويطلع أسعار حقيقية لعدة شركات معتمدة بأوزان مختلفة:
- سبائك الذهب (بي تي سي، جولد إيرا، سام، سليمة جولد...)
- الجنيه الذهب وأجزاؤه ومضاعفاته لنفس الشركات

المتطلبات:
    pip install requests beautifulsoup4

الاستخدام:
    from bullion_scraper import get_bullion_data
    data = get_bullion_data()
"""

import re
import time
import requests
from bs4 import BeautifulSoup

URL = "https://www.sabayekegypt.com/gold-bullion/"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _clean_number(text: str):
    if not text:
        return None
    text = text.replace(",", "").strip()
    if text in ("-", "—", ""):
        return None
    match = re.search(r"-?\d+(\.\d+)?", text)
    return float(match.group()) if match else None


def _find_table_after_heading(soup, keyword):
    """يدور على أقرب عنوان فيه الكلمة المفتاحية وياخد أول جدول بعده"""
    heading = soup.find(
        lambda tag: tag.name in ("h1", "h2", "h3") and keyword in tag.get_text()
    )
    if not heading:
        return None
    return heading.find_next("table")


def _parse_comparison_table(table):
    """
    يحول جدول المقارنة (شركة × أوزان) لقاموس:
    { "اسم الشركة": {"1 جرام": 7564.0, "5 جرام": 37320.0, ...}, ... }
    """
    if table is None:
        return {}

    header_cells = table.find("thead").find_all("th") if table.find("thead") else table.find("tr").find_all("th")
    weight_labels = [th.get_text(strip=True) for th in header_cells[1:]]  # تجاهل أول عمود (اسم الشركة)

    body = table.find("tbody") or table
    rows = body.find_all("tr")

    result = {}
    for row in rows:
        cells = row.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        company_cell = cells[0]
        company_name = company_cell.get_text(strip=True)
        if not company_name:
            continue

        prices = {}
        for label, cell in zip(weight_labels, cells[1:]):
            value = _clean_number(cell.get_text(strip=True))
            if value is not None:
                prices[label] = value

        if prices:
            result[company_name] = prices

    return result


def get_bullion_data():
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    bars_table = _find_table_after_heading(soup, "أفضل شركات السبائك")
    coins_table = _find_table_after_heading(soup, "الجنيه الذهب و العملات الذهبية")

    return {
        "source": URL,
        "bars": _parse_comparison_table(bars_table),
        "coins": _parse_comparison_table(coins_table),
    }


# اسم الشركة زي ما بيظهر في جدول المقارنة → الرابط بتاعها في الموقع
# (الروابط المؤكدة من الموقع: btc, goldera, dewanaldahab, elgallagold, mbgold, gfg)
COMPANY_SLUGS = {
    "BTC": "btc",
    "بي تي سي": "btc",
    "جولد إيرا": "goldera",
    "جولد ايرا": "goldera",
    "Gold Era": "goldera",
    "ديوان الذهب": "dewanaldahab",
    "سويس جولد": "swissgold",
    "سليمة جولد": "selemagold",
    "نجم الدين": "nagmadin",
    "إم بي جولد": "mbgold",
    "ام بي جولد": "mbgold",
    "MB GOLD": "mbgold",
    "الجلال جولد": "elgallagold",
    "الجلا جولد": "elgallagold",
    "ماستر جولد": "mastergold",
    "سام": "sampreciousmetals",
    "SAM": "sampreciousmetals",
    "الراعي جولد": "alraaeigold",
    "ذهب الأجيال": "gfg",
    "GFG": "gfg",
}


def _norm(s: str):
    """توحيد الاسم للمقارنة: حروف صغيرة، من غير مسافات، وتوحيد الهمزات والتاء المربوطة"""
    s = (s or "").lower()
    s = re.sub(r"[\s\-_]+", "", s)
    s = re.sub("[أإآ]", "ا", s).replace("ة", "ه").replace("ى", "ي")
    return s


def _slug_for_company(company_name: str):
    if company_name in COMPANY_SLUGS:
        return COMPANY_SLUGS[company_name]
    n = _norm(company_name)
    if not n:
        return None
    normalized = [(_norm(k), v) for k, v in COMPANY_SLUGS.items()]
    for k, v in normalized:
        if k == n:
            return v
    # مطابقة جزئية: الأطول الأول عشان الاسم الأدق يكسب
    for k, v in sorted(normalized, key=lambda kv: -len(kv[0])):
        if len(k) >= 3 and (k in n or n in k):
            return v
    return None


def _extract_weight_token(weight_label: str):
    """بيحول تسمية الوزن زي 'ربع جنيه ذهب (2 جرام)' أو '1 جرام' لرقم الوزن المستخدم في الرابط"""
    paren = re.search(r"\(([\d.]+)\s*جرام\)", weight_label)
    if paren:
        return paren.group(1)
    m = re.search(r"([\d.]+)", weight_label)
    return m.group(1) if m else None


_LIST_CACHE = {"ts": 0.0, "data": None}
_PAGE_CACHE = {}
_NUM = r"([\d,]+(?:\.\d+)?)"


def _cached_list():
    """جدول المقارنة (شركة × وزن → سعر البيع). بنحفظه 5 دقايق عشان منزودش الطلبات على الموقع"""
    now = time.time()
    if _LIST_CACHE["data"] is None or now - _LIST_CACHE["ts"] > 300:
        _LIST_CACHE["data"] = get_bullion_data()
        _LIST_CACHE["ts"] = now
    return _LIST_CACHE["data"]


def _page_text(url):
    now = time.time()
    hit = _PAGE_CACHE.get(url)
    if hit and now - hit[0] < 300:
        return hit[1]
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)
    if len(_PAGE_CACHE) > 60:
        _PAGE_CACHE.clear()
    _PAGE_CACHE[url] = (now, text)
    return text


def _discover_slug(kind, weight_token, company_name):
    """لو رابط الشركة اتغير أو مش في القايمة: نقراه من صفحة الوزن نفسها في الموقع (أول رابط اسمه بيطابق الشركة)"""
    base = "https://www.sabayekegypt.com/gold-bullion/" if kind == "bars" else "https://www.sabayekegypt.com/gold-coin/"
    page_url = f"{base}{weight_token}/"
    resp = requests.get(page_url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    target = _norm(company_name)
    pat = re.compile(r"/" + re.escape(weight_token) + r"/([^/?#]+)/?$")
    for a in soup.find_all("a", href=True):
        m = pat.search(a["href"])
        if not m:
            continue
        label = _norm(a.get_text(" ", strip=True) + " " + (a.get("title") or ""))
        if target and label and (target in label or label in target):
            return m.group(1)
    return None


def _all_values(text, label_regex):
    """كل القيم اللي جاية بعد اسم الحقل، بترتيب ظهورها في الصفحة"""
    out = []
    for m in re.finditer(label_regex + r"\s*" + _NUM, text):
        v = _clean_number(m.group(1))
        if v is not None:
            out.append(v)
    return out


def get_bullion_detail(kind: str, weight_label: str, company_name: str):
    """
    kind: 'bars' أو 'coins'
    weight_label: تسمية الوزن زي ما هي راجعة من get_bullion_data()، مثلاً '1 جرام'
    company_name: اسم الشركة زي ما هو راجع من get_bullion_data()

    صفحة الشركة في الموقع فيها أقسام لكل الأوزان (سبائك ثم عملات)، وكل قسم فيه:
    سعر السبيكة / سعر المصنعية للجرام / الكاش باك / سعر إعادة البيع.
    فمينفعش ناخد أول رقم في الصفحة (ده كان بيطلع سعر الـ 1 جرام دايمًا).
    بنجمع كل قيم كل حقل بترتيب ظهورها، وبنختار القسم الصح:
      - سبائك: القسم اللي سعر سبيكته أقرب لسعر الوزن ده في جدول المقارنة.
      - عملات: ترتيب الفئة في جدول المقارنة = ترتيب القسم (والعدد لازم يتطابق).
    ولو مفيش تطابق واضح بنرجّع error بدل ما نعرض رقم غلط.
    """
    slug = _slug_for_company(company_name)
    weight_token = _extract_weight_token(weight_label)
    if not slug or not weight_token:
        return {"error": "تعذر تحديد الشركة أو الوزن"}

    base = "https://www.sabayekegypt.com/gold-bullion/" if kind == "bars" else "https://www.sabayekegypt.com/gold-coin/"
    url = f"{base}{weight_token}/{slug}/"
    weight_value = float(weight_token)

    try:
        text = _page_text(url)
    except requests.HTTPError as e:
        if e.response is None or e.response.status_code != 404:
            return {"error": "تعذر فتح صفحة الموقع"}
        found = _discover_slug(kind, weight_token, company_name)
        if not found:
            return {"error": "الشركة دي مش موجودة في الموقع بالوزن ده"}
        url = f"{base}{weight_token}/{found}/"
        text = _page_text(url)
    listing = _cached_list()
    bars_c = (listing.get("bars") or {}).get(company_name) or {}
    coins_c = (listing.get("coins") or {}).get(company_name) or {}

    # بنحصر القراءة في منطقة أقسام الأوزان بس (من أول "سعر السبيكة" لآخر "بدون غلاف")
    # عشان جدول الملخص في أول الصفحة وأسئلة الصفحة في آخرها ميبوظوش الترتيب
    first = re.search(r"سعر\s*السبيكة\s*" + _NUM, text)
    ends = list(re.finditer(r"بدون\s*غلاف\s*" + _NUM, text))
    region = text
    strict = False
    if first and ends and ends[-1].end() > first.start():
        region = text[first.start():ends[-1].end()]
        strict = True

    sells = _all_values(region, r"سعر\s*السبيكة")
    fees = _all_values(region, r"سعر\s*المصنعية\s*للجرام")
    resales = _all_values(region, r"سعر\s*إعادة\s*البيع")
    cashbacks = _all_values(region, r"الكاش\s*باك")

    n_bars = len(sells)
    n_coins = len(fees) - n_bars
    total = n_bars + n_coins
    if n_bars == 0 or n_coins < 0 or len(fees) < total or len(resales) < total or len(cashbacks) < total:
        return {"error": "شكل صفحة الموقع اتغير، تعذر قراءة التفاصيل"}
    if strict and not (len(fees) == len(resales) == len(cashbacks) == total):
        return {"error": "عدد الأقسام في الصفحة مش متطابق، تعذر قراءة التفاصيل"}

    # لو مفيش منطقة واضحة بناخد آخر total قيمة
    fees = fees[-total:]
    resales = resales[-total:]
    cashbacks = cashbacks[-total:]

    if kind == "bars":
        expected = bars_c.get(weight_label)
        if not expected:
            return {"error": "الوزن ده مش موجود في جدول المقارنة"}
        idx = min(range(n_bars), key=lambda k: abs(sells[k] - expected))
        if abs(sells[idx] - expected) / expected > 0.005:
            return {"error": "تعذر مطابقة السعر مع قسم الوزن في الصفحة"}
        sell = sells[idx]
    else:
        keys = list(coins_c.keys())
        if weight_label not in keys or len(keys) != n_coins:
            return {"error": "تعذر مطابقة فئة الجنيه الذهب مع الصفحة"}
        idx = n_bars + keys.index(weight_label)
        sell = coins_c[weight_label]

    fee_per_gram = fees[idx]
    cashback_per_gram = cashbacks[idx]
    buyback = resales[idx]

    gold_price = round(sell - (fee_per_gram * weight_value), 2)
    if gold_price <= 0 or buyback > sell * 1.02:
        return {"error": "الأرقام المقروءة غير منطقية، تعذر عرض التفاصيل"}

    return {
        "source": url,
        "company": company_name,
        "weight_label": weight_label,
        "weight_grams": weight_value,
        "sell_price": sell,
        "buyback_price": buyback,
        "manufacturing_fee_per_gram": fee_per_gram,
        "cashback_per_gram": cashback_per_gram,
        "gold_price_estimated": gold_price,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_bullion_data(), ensure_ascii=False, indent=2))
