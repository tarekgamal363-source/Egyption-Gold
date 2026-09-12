"""
bls_scraper.py
----------------
يجيب أحدث نتائج فعلية لمؤشرات أمريكا الرسمية (CPI بشكل أساسي) من الصفحة
الرئيسية لموقع BLS (bls.gov) - اتأكدنا من شكل النص الحقيقي فيها، مثال فعلي:

"In August, the Consumer Price Index for All Urban Consumers rose 0.4
percent, seasonally adjusted (SA), and rose 3.4 percent over the last
12 months, not seasonally adjusted (NSA)."

المتطلبات:
    pip install requests beautifulsoup4

الاستخدام:
    from bls_scraper import get_bls_actuals
    data = get_bls_actuals()
    # بترجع: {"cpi_mm": "0.4%", "cpi_yy": "3.4%"} أو None للقيم مش موجودة
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

BLS_HOME_URL = "https://www.bls.gov/"

_UP_WORDS = r"(?:rose|increased|advanced|climbed)"
_DOWN_WORDS = r"(?:fell|decreased|declined|dropped)"


def _extract_cpi_mm(text):
    """m/m: 'Consumer Price Index for All Urban Consumers rose 0.4 percent'"""
    m = re.search(
        rf"Consumer Price Index for All Urban Consumers\s+{_UP_WORDS}\s+([\d.]+)\s*percent",
        text, re.IGNORECASE
    )
    if m:
        return f"{m.group(1)}%"
    m = re.search(
        rf"Consumer Price Index for All Urban Consumers\s+{_DOWN_WORDS}\s+([\d.]+)\s*percent",
        text, re.IGNORECASE
    )
    if m:
        return f"-{m.group(1)}%"
    return None


def _extract_cpi_yy(text):
    """y/y: '...and rose 3.4 percent over the last 12 months'"""
    m = re.search(
        rf"{_UP_WORDS}\s+([\d.]+)\s*percent over the last 12 months",
        text, re.IGNORECASE
    )
    if m:
        return f"{m.group(1)}%"
    m = re.search(
        rf"{_DOWN_WORDS}\s+([\d.]+)\s*percent over the last 12 months",
        text, re.IGNORECASE
    )
    if m:
        return f"-{m.group(1)}%"
    return None


def _extract_payroll(text):
    """'Payroll employment rose 162,000 in August' - نمط شائع في نفس الصفحة"""
    m = re.search(
        rf"[Pp]ayroll employment\s+{_UP_WORDS}\s+([\d,]+)",
        text
    )
    if m:
        return f"+{m.group(1).replace(',', '')}"
    m = re.search(
        rf"[Pp]ayroll employment\s+{_DOWN_WORDS}\s+([\d,]+)",
        text
    )
    if m:
        return f"-{m.group(1).replace(',', '')}"
    return None


def _extract_unemployment_rate(text):
    m = re.search(
        r"unemployment rate.{0,50}?([\d.]+)\s*percent",
        text, re.IGNORECASE
    )
    if m:
        return f"{m.group(1)}%"
    return None


def get_bls_actuals():
    result = {}
    try:
        resp = requests.get(BLS_HOME_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

        result["cpi_mm"] = _extract_cpi_mm(text)
        result["cpi_yy"] = _extract_cpi_yy(text)
        result["nfp"] = _extract_payroll(text)
        result["unemployment_rate"] = _extract_unemployment_rate(text)
        result["ppi_mm"] = None  # الصفحة الرئيسية مش دايمًا فيها PPI، هنسيبها فاضية دلوقتي

    except Exception as e:
        result["error"] = str(e)

    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_bls_actuals(), ensure_ascii=False, indent=2))
