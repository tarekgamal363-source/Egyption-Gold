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
COMPANY_SLUGS = {
    "BTC": "btc",
    "بي تي سي": "btc",
    "جولد إيرا": "goldera",
    "Gold Era": "goldera",
    "ديوان الذهب": "dewanaldahab",
    "سويس جولد": "swissgold",
    "سليمة جولد": "selemagold",
    "نجم الدين": "nagmadin",
    "إم بي جولد": "mbgold",
    "الجلال جولد": "elgallagold",
    "ماستر جولد": "mastergold",
    "سام": "sampreciousmetals",
    "SAM": "sampreciousmetals",
    "الراعي جولد": "alraaeigold",
    "GFG": "gfg",
}


def _slug_for_company(company_name: str):
    if company_name in COMPANY_SLUGS:
        return COMPANY_SLUGS[company_name]
    # محاولة مطابقة تقريبية لو الاسم مكتوب بشكل مختلف شوية
    for name, slug in COMPANY_SLUGS.items():
        if name in company_name or company_name in name:
            return slug
    return None


def _extract_weight_token(weight_label: str):
    """بيحول تسمية الوزن زي 'ربع جنيه ذهب (2 جرام)' أو '1 جرام' لرقم الوزن المستخدم في الرابط"""
    paren = re.search(r"\(([\d.]+)\s*جرام\)", weight_label)
    if paren:
        return paren.group(1)
    m = re.search(r"([\d.]+)", weight_label)
    return m.group(1) if m else None


def get_bullion_detail(kind: str, weight_label: str, company_name: str):
    """
    kind: 'bars' أو 'coins'
    weight_label: أي تسمية وزن زي ما هي راجعة من get_bullion_data()، مثلاً '1 جرام'
    company_name: اسم الشركة زي ما هو راجع من get_bullion_data()

    بيرجع dict فيها: سعر البيع، سعر الشراء (إعادة البيع)، المصنعية للجرام،
    الكاش باك للجرام، وسعر الذهب الخام (محسوب = البيع - المصنعية × الوزن)
    """
    slug = _slug_for_company(company_name)
    weight_token = _extract_weight_token(weight_label)
    if not slug or not weight_token:
        return {"error": "تعذر تحديد الشركة أو الوزن"}

    base = "https://www.sabayekegypt.com/gold-bullion/" if kind == "bars" else "https://www.sabayekegypt.com/gold-coin/"
    url = f"{base}{weight_token}/{slug}/"

    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

    sell_m = re.search(r"يبلغ\s*([\d,]+\.?\d*)\s*جنيه", text)
    buyback_m = re.search(r"اعادة البيع\s*([\d,]+\.?\d*)\s*جنيه", text)
    fee_m = re.search(r"مصنعية يساوي\s*([\d,]+\.?\d*)\s*جنيه", text)
    cashback_m = re.search(r"كاش باك\s*([\d,]+\.?\d*)\s*جنيه", text)

    sell = _clean_number(sell_m.group(1)) if sell_m else None
    buyback = _clean_number(buyback_m.group(1)) if buyback_m else None
    fee_per_gram = _clean_number(fee_m.group(1)) if fee_m else None
    cashback_per_gram = _clean_number(cashback_m.group(1)) if cashback_m else None

    weight_value = float(weight_token)
    gold_price = None
    if sell is not None and fee_per_gram is not None:
        gold_price = round(sell - (fee_per_gram * weight_value), 2)

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
