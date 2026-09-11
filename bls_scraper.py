"""
bls_scraper.py
----------------
يجيب القيم الفعلية لمؤشرات CPI و PPI مباشرة من الموقع الرسمي لمكتب
إحصاءات العمل الأمريكي (BLS) - نفس الجهة اللي بتصدر البيانات دي أصلاً،
مش من وسيط. الروابط دي ثابتة وبتتحدث لوحدها كل شهر لما BLS ينشر تقرير جديد.

المتطلبات:
    pip install requests beautifulsoup4

الاستخدام:
    from bls_scraper import get_bls_actuals
    data = get_bls_actuals()
    # بترجع: {"cpi_mm": "0.3%", "cpi_yy": "3.0%", "ppi_mm": "0.4%", ...} أو None لو مش لاقي
"""

import re
import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

CPI_URL = "https://www.bls.gov/news.release/cpi.nr0.htm"
PPI_URL = "https://www.bls.gov/news.release/ppi.nr0.htm"
EMPSIT_URL = "https://www.bls.gov/news.release/empsit.nr0.htm"

# كل الأفعال اللي BLS ممكن تستخدمها للتعبير عن الزيادة/النقصان في نص التقرير
_UP_WORDS = r"(?:increased|rose|advanced|climbed|moved up|went up)"
_DOWN_WORDS = r"(?:decreased|fell|declined|dropped|moved down|went down)"


def _get_page_text(url):
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)


def _extract_percent_change(text, pattern_subject):
    """
    بيدور على جملة زي 'The Consumer Price Index ... increased 0.3 percent ... in September'
    وبيرجع القيمة كنص زي '0.3%' أو '-0.2%' لو الفعل كان نقصان، أو None لو مش لاقي
    """
    up_pattern = rf"{pattern_subject}.{{0,80}}?{_UP_WORDS}\s+([\d.]+)\s*percent"
    down_pattern = rf"{pattern_subject}.{{0,80}}?{_DOWN_WORDS}\s+([\d.]+)\s*percent"
    unchanged_pattern = rf"{pattern_subject}.{{0,80}}?(?:was unchanged|remained unchanged)"

    m = re.search(up_pattern, text, re.IGNORECASE)
    if m:
        return f"{m.group(1)}%"

    m = re.search(down_pattern, text, re.IGNORECASE)
    if m:
        return f"-{m.group(1)}%"

    m = re.search(unchanged_pattern, text, re.IGNORECASE)
    if m:
        return "0.0%"

    return None


def _extract_nfp(text):
    """
    بيدور على جملة زي 'Total nonfarm payroll employment rose by 150,000 in September'
    وبيرجع رقم الوظائف كنص زي '150K'
    """
    m = re.search(
        r"nonfarm payroll employment (rose|increased|grew|added|changed little|fell|decreased)\s*(?:by)?\s*([\d,]+)?",
        text, re.IGNORECASE
    )
    if not m:
        return None
    verb, number = m.group(1), m.group(2)
    if not number:
        return None
    number = number.replace(",", "")
    value_k = round(int(number) / 1000)
    sign = "-" if verb.lower() in ("fell", "decreased") else ""
    return f"{sign}{value_k}K"


def _extract_unemployment_rate(text):
    m = re.search(
        r"unemployment rate.{0,40}?(?:was|remained|held at|rose to|fell to|edged up to|edged down to)\s+([\d.]+)\s*percent",
        text, re.IGNORECASE
    )
    if m:
        return f"{m.group(1)}%"
    return None


def get_bls_actuals():
    result = {}

    try:
        cpi_text = _get_page_text(CPI_URL)
        result["cpi_mm"] = _extract_percent_change(
            cpi_text, r"Consumer Price Index for All Urban Consumers \(CPI-U\)"
        )
        result["cpi_yy"] = _extract_percent_change(
            cpi_text, r"all items index"
        )
    except Exception as e:
        result["cpi_error"] = str(e)

    try:
        ppi_text = _get_page_text(PPI_URL)
        result["ppi_mm"] = _extract_percent_change(
            ppi_text, r"Producer Price Index for final demand"
        )
    except Exception as e:
        result["ppi_error"] = str(e)

    try:
        empsit_text = _get_page_text(EMPSIT_URL)
        result["nfp"] = _extract_nfp(empsit_text)
        result["unemployment_rate"] = _extract_unemployment_rate(empsit_text)
    except Exception as e:
        result["empsit_error"] = str(e)

    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_bls_actuals(), ensure_ascii=False, indent=2))
