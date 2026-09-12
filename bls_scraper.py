"""
bls_scraper.py
----------------
يجيب أحدث نتائج فعلية لمؤشرات أمريكا الرسمية (CPI، معدل البطالة، الوظائف،
PPI) من الصفحة الرئيسية لموقع BLS (bls.gov) نفسه - المصدر الرسمي الوحيد.

الصفحة فيها قسم ثابت اسمه "Latest Numbers" بصيغة واضحة زي:
    Consumer Price Index (CPI): +0.4% in Aug 2026
    Unemployment Rate: 4.1% in Aug 2026
    Payroll Employment: +162,000(p) in Aug 2026
    Producer Price Index - Final Demand: +0.7%(p) in Aug 2026

المتطلبات:
    pip install requests beautifulsoup4

الاستخدام:
    from bls_scraper import get_bls_actuals
    data = get_bls_actuals()
    # بترجع: {"cpi_mm": "+0.4%", "unemployment_rate": "4.1%",
    #          "nfp": "+162K", "ppi_mm": "+0.7%", ...} أو None للقيم مش موجودة
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

PATTERNS = {
    "cpi_mm": r"Consumer Price Index \(CPI\):\s*([+-][\d.]+%)\s*in\s*([A-Za-z]+ \d{4})",
    "unemployment_rate": r"Unemployment Rate:\s*([\d.]+%)\s*in\s*([A-Za-z]+ \d{4})",
    "nfp": r"Payroll Employment:\s*([+-][\d,]+)(?:\(p\))?\s*in\s*([A-Za-z]+ \d{4})",
    "ppi_mm": r"Producer Price Index\s*-\s*Final Demand:\s*([+-][\d.]+%)(?:\(p\))?\s*in\s*([A-Za-z]+ \d{4})",
    "avg_hourly_earnings": r"Average Hourly Earnings:\s*([+-]\$[\d.]+)(?:\(p\))?\s*in\s*([A-Za-z]+ \d{4})",
}


def get_bls_actuals():
    result = {}
    try:
        resp = requests.get(BLS_HOME_URL, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)

        for key, pattern in PATTERNS.items():
            m = re.search(pattern, text)
            if m:
                result[key] = m.group(1)
                result[f"{key}_period"] = m.group(2)
            else:
                result[key] = None

        # NFP بيتحول لصيغة "K" زي باقي التطبيق (مثال: +162,000 -> +162K)
        if result.get("nfp"):
            nfp_raw = result["nfp"].replace(",", "").replace("+", "")
            try:
                sign = "-" if nfp_raw.startswith("-") else "+"
                value_k = round(abs(int(nfp_raw)) / 1000)
                result["nfp"] = f"{sign}{value_k}K"
            except ValueError:
                pass

    except Exception as e:
        result["error"] = str(e)

    return result


if __name__ == "__main__":
    import json
    print(json.dumps(get_bls_actuals(), ensure_ascii=False, indent=2))
