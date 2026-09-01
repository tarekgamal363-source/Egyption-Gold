"""
oil_scraper.py
---------------
يجيب سعر برميل النفط العالمي (WTI) بالدولار من API Ninjas (مجاني).

محتاج مفتاح API مجاني:
1. اعمل حساب على https://api-ninjas.com (مجاني، من غير كارت)
2. من الداشبورد بتاعك هتلاقي API Key، انسخه
3. حطه في متغير بيئة (Environment Variable) اسمه OIL_API_KEY في Render:
   Render Dashboard → مشروعك → Environment → Add Environment Variable
   Key: OIL_API_KEY   Value: (المفتاح بتاعك)

المتطلبات:
    pip install requests

الاستخدام:
    from oil_scraper import get_oil_price
    data = get_oil_price()
"""

import os
import requests

API_URL = "https://api.api-ninjas.com/v1/oilprice"


def get_oil_price():
    api_key = os.environ.get("OIL_API_KEY")
    if not api_key:
        return {"error": "OIL_API_KEY غير موجود - أضفه في إعدادات Environment على Render"}

    headers = {"X-Api-Key": api_key}
    resp = requests.get(API_URL, headers=headers, params={"type": "wti"}, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    return {
        "name": data.get("name", "WTI Crude Oil"),
        "price_usd": data.get("price"),
        "previous_close": data.get("previous_close"),
        "change_24h": data.get("change_24h"),
        "change_24h_percent": data.get("change_24h_percent"),
        "updated_unix": data.get("updated"),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(get_oil_price(), ensure_ascii=False, indent=2))
