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


if __name__ == "__main__":
    import json
    print(json.dumps(get_bullion_data(), ensure_ascii=False, indent=2))
