import requests
import xml.etree.ElementTree as ET
from db_config import get_conn
import os
from dotenv import load_dotenv
load_dotenv()

SERVICE_KEY    = os.getenv("MOLIT_SERVICE_KEY")
LAND_PRICE_URL = "https://apis.data.go.kr/1611000/nsdi/IndvdLandPriceService/wgs84/getIndvdLandPriceWgs84"
APT_PRICE_URL  = "https://apis.data.go.kr/1611000/nsdi/ApartHousingPriceService/wgs84/getApartHousingPriceWgs84"

def fetch_land_price(pnu_code):
    params = {
        "serviceKey": SERVICE_KEY,
        "pnu":        pnu_code,
        "stdrYear":   "2024",
        "numOfRows":  1,
        "pageNo":     1,
        "_type":      "xml",
    }
    try:
        res  = requests.get(LAND_PRICE_URL, params=params, timeout=10)
        root = ET.fromstring(res.content)
        item = root.find(".//item")
        if item is None:
            return None
        val = item.findtext("pblntfPclnd")
        return int(val.replace(",", "").strip()) if val else None
    except Exception as e:
        print(f"  공시지가 오류 pnu={pnu_code}: {e}")
        return None

def fetch_apt_price(sigungu_cd, bjdong_cd, bun, ji):
    params = {
        "serviceKey": SERVICE_KEY,
        "sigunguCd":  sigungu_cd,
        "bjdongCd":   bjdong_cd,
        "bun":        bun.zfill(4),
        "ji":         ji.zfill(4),
        "stdrYear":   "2024",
        "numOfRows":  1,
        "pageNo":     1,
        "_type":      "xml",
    }
    try:
        res  = requests.get(APT_PRICE_URL, params=params, timeout=10)
        root = ET.fromstring(res.content)
        item = root.find(".//item")
        if item is None:
            return None
        val = item.findtext("pblntfPrc")
        return int(val.replace(",", "").strip()) * 1000 if val else None
    except Exception as e:
        print(f"  공동주택 공시가격 오류: {e}")
        return None

def upsert_official_price(building_id, official_price, price_type, conn):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO official_price (building_id, official_price, price_type, base_year, created_at)
        VALUES (%s, %s, %s, '2024', NOW())
        ON CONFLICT (building_id) DO UPDATE
        SET official_price = EXCLUDED.official_price,
            price_type     = EXCLUDED.price_type,
            base_year      = EXCLUDED.base_year,
            created_at     = NOW()
    """, (building_id, official_price, price_type))
    conn.commit()
    cur.close()

def main():
    conn = get_conn()
    cur  = conn.cursor()
    cur.execute("""
        SELECT b.building_id, b.pnu_code, b.building_type
        FROM building_master b
        LEFT JOIN official_price op ON b.building_id = op.building_id
        WHERE op.building_id IS NULL
        LIMIT 500
    """)
    buildings = cur.fetchall()
    cur.close()

    print(f"공시가격 수집 대상: {len(buildings)}개")

    for building_id, pnu_code, building_type in buildings:
        if not pnu_code or len(pnu_code) < 19:
            print(f"  건물 {building_id}: PNU 불완전, 건너뜀")
            continue

        sigungu_cd = pnu_code[0:5]
        bjdong_cd  = pnu_code[5:10]
        bun        = pnu_code[11:15]
        ji         = pnu_code[15:19]

        official_price = None
        price_type     = "LAND"

        if building_type and "오피스텔" in building_type:
            official_price = fetch_apt_price(sigungu_cd, bjdong_cd, bun, ji)
            if official_price:
                price_type = "APT"

        if not official_price:
            price_per_sqm = fetch_land_price(pnu_code)
            if price_per_sqm:
                official_price = price_per_sqm * 20  # 대구 원룸 평균 전용 20㎡
                price_type     = "LAND"

        if official_price:
            upsert_official_price(building_id, official_price, price_type, conn)
            print(f"  건물 {building_id} ({price_type}): {official_price:,}원")
        else:
            print(f"  건물 {building_id}: 공시가격 없음")

    conn.close()
    print("완료")

if __name__ == "__main__":
    main()