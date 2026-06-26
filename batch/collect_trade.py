import requests
import xml.etree.ElementTree as ET
from db_config import get_conn
import os
from dotenv import load_dotenv
load_dotenv()
SERVICE_KEY = os.getenv("MOLIT_SERVICE_KEY")

DAEGU_LAWD_CODES = [
    "27200",  
    "27230", 
    "27260",  
    "27140",  
    "27170",  
    "27110",  
    "27290", 
]

DEAL_MONTHS = ["202501", "202502", "202503", "202504", "202505", "202506"]

URLS = {
    "단독다가구": "https://apis.data.go.kr/1613000/RTMSDataSvcSHRent/getRTMSDataSvcSHRent",
    "오피스텔": "https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent",
}

def fetch_rent_data(url, lawd_cd, deal_ymd):
    params = {
        "serviceKey": SERVICE_KEY,
        "LAWD_CD": lawd_cd,
        "DEAL_YMD": deal_ymd,
        "numOfRows": 1000,
        "pageNo": 1,
    }
    res = requests.get(url, params=params, timeout=10)
    return ET.fromstring(res.content)

def parse_and_insert(root, trade_type, conn):
    cur = conn.cursor()
    items = root.findall(".//item")
    inserted = 0

    for item in items:
        deposit = item.findtext("보증금액", "0").replace(",", "").strip()
        monthly = item.findtext("월세금액", "0").replace(",", "").strip()
        year = item.findtext("년", "")
        month = item.findtext("월", "").zfill(2)
        jibun = item.findtext("지번", "").strip()
        dong = item.findtext("법정동", "").strip()

        if not deposit or not year or not month:
            continue

        contract_ym = f"{year}{month}"

        # building_master에서 지번 주소로 매칭 시도
        cur.execute("""
            SELECT building_id FROM building_master
            WHERE jibun_address LIKE %s
            LIMIT 1
        """, (f"%{dong}%{jibun}%",))
        row = cur.fetchone()
        if not row:
            continue

        building_id = row[0]
        cur.execute("""
            INSERT INTO trade_price (building_id, trade_type, price, monthly_rent_amount, contract_year_month, created_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING
        """, (building_id, trade_type, int(deposit), int(monthly), contract_ym))
        inserted += 1

    conn.commit()
    cur.close()
    print(f"  [{trade_type}] {inserted}건 삽입")

def main():
    conn = get_conn()
    for trade_type, url in URLS.items():
        for lawd_cd in DAEGU_LAWD_CODES:
            for deal_ymd in DEAL_MONTHS:
                print(f"수집 중: {trade_type} / {lawd_cd} / {deal_ymd}")
                try:
                    root = fetch_rent_data(url, lawd_cd, deal_ymd)
                    parse_and_insert(root, "RENT_DEPOSIT", conn)
                except Exception as e:
                    print(f"  오류: {e}")
    conn.close()

if __name__ == "__main__":
    main()