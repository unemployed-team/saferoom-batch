import requests
from db_config import get_conn
import os
from dotenv import load_dotenv
load_dotenv()
SERVICE_KEY = os.getenv("MOLIT_SERVICE_KEY")
BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo"

def fetch_building_by_addr(road_addr):
    params = {
        "serviceKey": SERVICE_KEY,
        "platPlcNm": road_addr,
        "numOfRows": 1,
        "pageNo": 1,
        "_type": "json",
    }
    try:
        res = requests.get(BASE_URL, params=params, timeout=10)
        return res.json()
    except Exception as e:
        print(f"  API 오류: {e}")
        return {}

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
    cur.execute("SELECT building_id, road_address FROM building_master")
    buildings = cur.fetchall()
    cur.close()

    print(f"건물 {len(buildings)}개 처리 시작")
    for building_id, road_address in buildings:
        try:
            data = fetch_building_by_addr(road_address)
            items = data.get("response", {}).get("body", {}).get("items", {})
            if not items:
                print(f"  건물 {building_id}: API 결과 없음, 기본값 사용")
                update_building_detail(building_id, False, 4, 10, conn)
                continue
            item = items.get("item", [])
            if isinstance(item, list):
                item = item[0] if item else {}
            is_illegal = item.get("vltnBldYn", "N") == "Y"
            floor_count = int(item.get("grndFlrCnt", 4) or 4)
            household_count = int(item.get("hhldCnt", 10) or 10)
            update_building_detail(building_id, is_illegal, floor_count, household_count, conn)
            print(f"  건물 {building_id} 업데이트 완료")
        except Exception as e:
            print(f"  건물 {building_id} 오류: {e}")
            update_building_detail(building_id, False, 4, 10, conn)
    conn.close()

if __name__ == "__main__":
    main()