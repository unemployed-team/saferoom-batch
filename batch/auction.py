import requests
import xml.etree.ElementTree as ET
from db_config import get_conn
import os
from dotenv import load_dotenv
load_dotenv()

SERVICE_KEY = os.getenv("MOLIT_SERVICE_KEY")
AUCTION_URL = "https://apis.data.go.kr/B550093/RetrieveAuctionResult/retrieveAuctionResultList"

def fetch_auction(sido_cd="27"):
    params = {
        "serviceKey": SERVICE_KEY,
        "sidoCd": sido_cd,
        "pgNum": 1,
        "pgSz": 1000,
        "_type": "xml",
    }
    try:
        res = requests.get(AUCTION_URL, params=params, timeout=15)
        print(f"  응답코드: {res.status_code}")
        print(f"  응답앞부분: {res.text[:200]}")
        if res.status_code != 200:
            return []
        root = ET.fromstring(res.content)
        return root.findall(".//item")
    except ET.ParseError as e:
        print(f"  XML 파싱 오류 (API 미지원 또는 키 오류): {e}")
        return []
    except Exception as e:
        print(f"  경매 API 오류: {e}")
        return []

def match_building(road_addr, conn):
    if not road_addr:
        return None
    cur = conn.cursor()
    cur.execute("""
        SELECT building_id FROM building_master
        WHERE road_address LIKE %s OR jibun_address LIKE %s
        LIMIT 1
    """, (f"%{road_addr.strip()}%", f"%{road_addr.strip()}%"))
    row = cur.fetchone()
    cur.close()
    return row[0] if row else None

def upsert_auction(building_id, court_name, case_number, status, start_date, conn):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO auction_history
            (building_id, court_name, case_number, auction_status, auction_start_date, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
        ON CONFLICT DO NOTHING
    """, (building_id, court_name, case_number, status, start_date))
    conn.commit()
    cur.close()

def main():
    conn = get_conn()
    items = fetch_auction()
    print(f"경매 건수: {len(items)}")

    status_map = {"1": "PROCEEDING", "2": "COMPLETED", "3": "CANCELLED"}
    matched = 0

    for item in items:
        road_addr = item.findtext("rdnm", "")
        court_name = item.findtext("crtNm", "")
        case_number = item.findtext("caseNo", "")
        status = status_map.get(item.findtext("prgScd", ""), "PROCEEDING")
        start_date = item.findtext("auctDt", None)

        building_id = match_building(road_addr, conn)
        if building_id:
            upsert_auction(building_id, court_name, case_number, status, start_date, conn)
            matched += 1
            print(f"  매칭: building {building_id} / {case_number} / {status}")

    print(f"완료 — {matched}/{len(items)} 건 매칭")
    conn.close()

if __name__ == "__main__":
    main()