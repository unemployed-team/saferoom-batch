import requests
from db_config import get_conn
import os
from dotenv import load_dotenv
load_dotenv()
SERVICE_KEY = os.getenv("MOLIT_SERVICE_KEY")
BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

def fetch_building(sigungu_cd, bjdong_cd, bun, ji):
    params = {
        "serviceKey": SERVICE_KEY,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "bun": bun.zfill(4),
        "ji": ji.zfill(4),
        "numOfRows": 10,
        "pageNo": 1,
        "_type": "json",
    }
    res = requests.get(BASE_URL, params=params, timeout=10)
    return res.json()

def update_building_detail(building_id, is_illegal, floor_count, household_count, conn):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO building_detail (building_id, is_illegal_building, floor_count, household_count, created_at)
        VALUES (%s, %s, %s, %s, NOW())
        ON CONFLICT (building_id) DO UPDATE
        SET is_illegal_building = EXCLUDED.is_illegal_building,
            floor_count = EXCLUDED.floor_count,
            household_count = EXCLUDED.household_count
    """, (building_id, is_illegal, floor_count, household_count))
    conn.commit()
    cur.close()

def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT building_id, pnu_code, jibun_address FROM building_master LIMIT 500")
    buildings = cur.fetchall()
    cur.close()

    for building_id, pnu_code, jibun_address in buildings:
        if not pnu_code or len(pnu_code) < 19:
            continue
        sigungu_cd = pnu_code[0:5]
        bjdong_cd = pnu_code[5:10]
        bun = pnu_code[11:15]
        ji = pnu_code[15:19]

        try:
            data = fetch_building(sigungu_cd, bjdong_cd, bun, ji)
            items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
            if not items:
                continue
            if isinstance(items, dict):
                items = [items]

            item = items[0]
            is_illegal = item.get("vltnBldYn", "N") == "Y"
            floor_count = int(item.get("grndFlrCnt", 0) or 0)
            household_count = int(item.get("hhldCnt", 0) or 0)

            update_building_detail(building_id, is_illegal, floor_count, household_count, conn)
            print(f"건물 {building_id} 업데이트 완료")
        except Exception as e:
            print(f"건물 {building_id} 오류: {e}")

    conn.close()

if __name__ == "__main__":
    main()