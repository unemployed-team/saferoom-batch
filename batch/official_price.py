import requests
import xml.etree.ElementTree as ET
from db_config import get_conn
import os
from dotenv import load_dotenv
load_dotenv()

SERVICE_KEY = os.getenv("MOLIT_SERVICE_KEY")
LAND_PRICE_URL = "https://apis.data.go.kr/1611000/nsdi/IndvdLandPriceService/wgs84/getIndvdLandPriceWgs84"

def fetch_land_price_by_coord(lat, lng):
    params = {
        "serviceKey": SERVICE_KEY,
        "pageNo": 1,
        "numOfRows": 1,
        "stdrYear": "2024",
        "ldCode": "",
        "_type": "xml",
    }
    try:
        res = requests.get(LAND_PRICE_URL, params=params, timeout=10)
        root = ET.fromstring(res.content)
        item = root.find(".//item")
        if item is None:
            return None
        val = item.findtext("pblntfPclnd")
        return int(val.replace(",", "").strip()) if val else None
    except Exception as e:
        print(f"  공시지가 오류: {e}")
        return None

def upsert_official_price(building_id, official_price, price_type, conn):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO official_price (building_id, official_price, price_type, base_year, created_at)
        VALUES (%s, %s, %s, '2024', NOW())
        ON CONFLICT (building_id) DO UPDATE
        SET official_price = EXCLUDED.official_price,
            price_type = EXCLUDED.price_type,
            base_year = EXCLUDED.base_year,
            created_at = NOW()
    """, (building_id, official_price, price_type))
    conn.commit()
    cur.close()

DEFAULT_PRICES = {
    '다가구주택': 120000000,
    '연립주택': 130000000,
    '오피스텔': 180000000,
}

def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT b.building_id, b.building_type, b.build_year
        FROM building_master b
        LEFT JOIN official_price op ON b.building_id = op.building_id
        WHERE op.building_id IS NULL
    """)
    buildings = cur.fetchall()
    cur.close()

    print(f"공시가격 수집 대상: {len(buildings)}개")
    for building_id, building_type, build_year in buildings:
        default = DEFAULT_PRICES.get(building_type, 120000000)
        if build_year and build_year < 2000:
            default = int(default * 0.7)
        elif build_year and build_year >= 2015:
            default = int(default * 1.3)
        upsert_official_price(building_id, default, 'ESTIMATED', conn)
        print(f"  건물 {building_id} ({building_type}): {default:,}원 (추정값)")
    conn.close()
    print("완료")

if __name__ == "__main__":
    main()