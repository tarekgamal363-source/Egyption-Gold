"""
isagha_scraper.py
------------------
يقرأ صفحة الأسعار العامة من موقع iSagha (market.isagha.com/prices/eg)
ويطلع بس الأرقام اللي التطبيق فعلاً محتاجها:
عيار 18 / 21 / 24 - جنيه الذهب - الأوقية (بالدولار) - الدولار الرسمي.
(مفيش فضة ولا عملات تانية - دي متفلترة بره عمدًا لأن مالهاش علاقة بالتصميم)

⚠️ ملاحظات مهمة قبل الاستخدام:
- ده مش API رسمي، ده استخراج بيانات (scraping) من صفحة عامة.
- لو iSagha غيّروا تصميم الصفحة، السكريبت ممكن يوقف عن العمل ويحتاج تعديل.
- شغّله بشكل معقول (مرة كل دقيقة أو أكتر) عشان متضغطش على السيرفر بتاعهم.
- الأفضل على المدى الطويل: تتواصل مع iSagha وتسأل عن شراكة/API رسمي.

المتطلبات:
    pip install requests beautifulsoup4

الاستخدام:
    python isagha_scraper.py
    (هيطبع JSON فيه بس الحاجات اللي التطبيق محتاجها)
"""

import re
import json
import requests
from bs4 import BeautifulSoup

URL = "https://market.isagha.com/prices/eg"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


def _clean_number(text: str):
    """يحول '6,225.50 ج.م' أو '6225 ج.م' لرقم float نظيف"""
    if not text:
        return None
    text = text.replace("ج.م", "").replace("$", "").replace(",", "").strip()
    match = re.search(r"-?\d+(\.\d+)?", text)
    return float(match.group()) if match else None


def _parse_table(soup, heading_text):
    """يدور على العنوان اللي فيه heading_text وياخد أول جدول بعده"""
    heading = soup.find(lambda tag: tag.name in ("h2", "h3") and heading_text in tag.get_text())
    if not heading:
        return None
    return heading.find_next("table")


def _rows_to_dicts(table, columns):
    if table is None:
        return []
    rows = table.find_all("tr")
    results = []
    for row in rows[1:]:  # تخطي صف العناوين
        cells = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
        if len(cells) < 2:
            continue
        entry = {"label": cells[0]}
        for i, col in enumerate(columns, start=1):
            if i < len(cells):
                entry[col] = _clean_number(cells[i])
        results.append(entry)
    return results


def _find_by_label(rows, keyword):
    for r in rows:
        if keyword in r["label"]:
            return r
    return None


def get_prices():
    resp = requests.get(URL, headers=HEADERS, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # جدول الذهب فقط - الفضة والعملات مش هنقرب منها خالص
    gold_table = _parse_table(soup, "أسعار الذهب في مصر")
    currency_table = _parse_table(soup, "أسعار العملات")

    gold_rows = _rows_to_dicts(
        gold_table, ["sell", "sell_gap", "buy", "buy_gap", "change", "change_pct"]
    )
    currency_rows = _rows_to_dicts(
        currency_table, ["sell", "buy", "change", "change_pct"]
    )

    karat_24 = _find_by_label(gold_rows, "24")
    karat_21 = _find_by_label(gold_rows, "21")
    karat_18 = _find_by_label(gold_rows, "18")
    gold_pound = _find_by_label(gold_rows, "جنيه")
    gold_ounce = _find_by_label(gold_rows, "أوقية")
    usd = _find_by_label(currency_rows, "دولار")

    # الأرقام دي بالظبط بترتيب الكروت في تصميم التطبيق
    result = {
        "source": URL,
        "karat_18": {"buy": karat_18["buy"] if karat_18 else None,
                     "sell": karat_18["sell"] if karat_18 else None},
        "karat_21": {"buy": karat_21["buy"] if karat_21 else None,
                     "sell": karat_21["sell"] if karat_21 else None},
        "karat_24": {"buy": karat_24["buy"] if karat_24 else None,
                     "sell": karat_24["sell"] if karat_24 else None},
        "gold_pound": {"buy": gold_pound["buy"] if gold_pound else None,
                        "sell": gold_pound["sell"] if gold_pound else None},
        "gold_ounce_usd": {"buy": gold_ounce["buy"] if gold_ounce else None,
                            "sell": gold_ounce["sell"] if gold_ounce else None},
        "usd_official": {"buy": usd["buy"] if usd else None,
                          "sell": usd["sell"] if usd else None},
    }
    return result


if __name__ == "__main__":
    data = get_prices()
    print(json.dumps(data, ensure_ascii=False, indent=2))
