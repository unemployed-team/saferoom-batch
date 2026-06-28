# SafeRoom Batch — 공공데이터 수집 파이프라인

> SafeRoom 서비스의 HRI Score 산출에 필요한 공공 API 데이터를 수집하여 PostgreSQL에 적재하는 **Python 배치 스크립트 모음**입니다.

---

##  팀원

### 프론트엔드 개발자

<table>
<tr>
<td align="center">
<img src="https://github.com/seonghyeon-digipen.png" width="100" height="100" alt="이성현">
<br>
<a href="https://github.com/seonghyeon-digipen"><strong>이성현</strong></a>
<br>
<small>프론트엔드 개발자</small>
</td>

<td align="center">
<img src="https://github.com/taejuKwon-digipen.png" width="100" height="100" alt="권태주">
<br>
<a href="https://github.com/taejuKwon-digipen"><strong>권태주</strong></a>
<br>
<small>프론트엔드 개발자</small>
</td>
</tr>
</table>

### 백엔드 개발자

<table>
<tr>
<td align="center">
<img src="https://github.com/Hyun-jun-Lee0811.png" width="100" height="100" alt="이현준">
<br>
<a href="https://github.com/Hyun-jun-Lee0811"><strong>이현준</strong></a>
<br>
<small>백엔드 개발자</small>
</td>
</tr>
</table>

---

##  폴더 구조

```
saferoom-batch/
└── batch/
    ├── collect_building.py   # 건축물대장 정보 수집 (국토교통부)
    ├── collect_trade.py      # 전월세 실거래가 수집 (국토교통부)
    ├── official_price.py     # 공시가격 추정값 적재
    ├── db_config.py          # PostgreSQL 연결 설정 (공통 모듈)
    └── requirements.txt      # Python 의존성 목록
```

---

##  전체 데이터 흐름

이 배치는 Spring Boot 서버가 HRI Score를 산출하기 전에 반드시 먼저 실행되어야 합니다.  
아래 흐름대로 데이터가 PostgreSQL에 적재된 이후에야 정확한 점수 계산이 가능합니다.

```
[국토교통부 건축물대장 API]          [국토교통부 전월세 실거래 API]          [유형·연도 기반 추정]
        ↓                                      ↓                                    ↓
 collect_building.py                   collect_trade.py                    official_price.py
        ↓                                      ↓                                    ↓
 building_detail 테이블                 trade_price 테이블                  official_price 테이블
 (위반건축물 / 층수 / 가구수)          (보증금 / 월세 / 계약연월)           (공시가격 추정값)
        ↓                                      ↓                                    ↓
└──────────────────────────────────────────────────────────────────────────────────┘
                                       PostgreSQL
                                           ↓
                              Spring Boot HriCalculator
                                           ↓
                    ┌──────────────────────────────────────────┐
                    │         HRI Score 0~100점 산출           │
                    │                                          │
                    │  건축 위험 (25점) ← building_detail      │
                    │  시세 이상 (25점) ← trade_price          │
                    │  임대인 위험 (30점) ← auction_history    │
                    │  생활 안전 (20점) ← field_report         │
                    └──────────────────────────────────────────┘
                                           ↓
                              SAFE / CAUTION / DANGER 등급
```

---

##  스크립트별 상세 설명

### 1. `collect_building.py` — 건축물대장 정보 수집

**사용 API**: [국토교통부] 건축물대장정보 서비스 (`getBrTitleInfo`)

```
https://apis.data.go.kr/1613000/BldRgstHubService/getBrTitleInfo
```

**동작 방식**

1. `building_master` 테이블에서 전체 건물 목록(`building_id`, `road_address`)을 조회합니다.
2. 각 건물의 도로명 주소를 API 파라미터(`platPlcNm`)로 요청합니다.
3. 응답에서 3가지 데이터를 추출해 `building_detail` 테이블에 UPSERT합니다.

| API 응답 필드 | 의미 | 저장 컬럼 |
|--------------|------|-----------|
| `vltnBldYn` | 위반건축물 여부 (Y/N) | `is_illegal_building` |
| `grndFlrCnt` | 지상 층수 | `floor_count` |
| `hhldCnt` | 가구수 | `household_count` |

4. API 응답이 없는 건물은 **기본값**(층수 4, 가구수 10, 위반 없음)으로 처리합니다.

**HRI Score 연관** — `건축 위험` 카테고리 (최대 25점)

| 조건 | 가산 점수 |
|------|-----------|
| 위반건축물(`is_illegal_building = true`) | +20점 |
| 건물 노후 30년 이상 | +5점 |
| 건물 노후 20년 이상 | +3점 |
| 건물 노후 15년 이상 | +1점 |
| 가구수 ÷ 층수 > 10 (방 쪼개기 의심) | +5점 |

**실행 예시**
```
건물 150개 처리 시작
  건물 1 업데이트 완료
  건물 2: API 결과 없음, 기본값 사용
  건물 3 업데이트 완료
```

---

### 2. `collect_trade.py` — 전월세 실거래가 수집

**사용 API**: [국토교통부] 부동산 실거래 데이터

| 유형 | API Endpoint |
|------|-------------|
| 단독/다가구 전월세 | `RTMSDataSvcSHRent/getRTMSDataSvcSHRent` |
| 오피스텔 전월세 | `RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent` |

**수집 범위 — 대구광역시 7개 구·군**

| 법정동 코드 | 지역 |
|-------------|------|
| 27110 | 중구 |
| 27140 | 동구 |
| 27170 | 서구 |
| 27200 | 남구 |
| 27230 | 북구 |
| 27260 | 수성구 |
| 27290 | 달서구 |

수집 기간: `2025년 1월 ~ 2025년 6월` (6개월)  
총 API 호출 횟수: 7개 구·군 × 6개월 × 2개 유형 = **최대 84회**

**동작 방식**

1. 위 범위로 API를 호출해 XML 응답을 파싱합니다.
2. 거래 건별로 읍면동명(`umdNm`)을 추출합니다.
3. `building_master` 테이블에서 `jibun_address LIKE '%읍면동명%'`으로 건물을 매핑합니다.
4. 매핑된 건물에 `trade_price` 테이블로 INSERT합니다.

| XML 필드 | 의미 | 변환 방식 |
|----------|------|-----------|
| `deposit` | 보증금 (만원) | × 10,000 → 원 단위 저장 |
| `monthlyRent` | 월세 (만원) | × 10,000 → 원 단위 저장 |
| `dealYear` + `dealMonth` | 계약 연월 | `"YYYYMM"` 형식으로 저장 |
| `umdNm` | 읍면동명 | 건물 매핑 키 |

**HRI Score 연관** — `시세 이상` 카테고리 (최대 25점)

전세가율 = 최근 6개월 평균 보증금 ÷ 평균 매매가

| 전세가율 | 가산 점수 |
|----------|-----------|
| 90% 이상 | +25점 (최고 위험) |
| 80% 이상 | +20점 |
| 70% 이상 | +15점 |
| 60% 이상 | +8점 |
| 60% 미만 | +0점 |

**실행 예시**
```
수집 중: 단독다가구 / 27230 / 202501
  [RENT_DEPOSIT] 47건 삽입
수집 중: 단독다가구 / 27230 / 202502
  [RENT_DEPOSIT] 39건 삽입
수집 중: 오피스텔 / 27200 / 202501
  오류: connection timeout
```

---

### 3. `official_price.py` — 공시가격 추정값 적재

>  **참고**: 공공 API의 좌표 기반 공시가격 조회 응답이 불안정하여, 현재는 **건물 유형 + 건축년도 기반 추정값**을 사용합니다.  
> `fetch_land_price_by_coord()` 함수는 구현되어 있으나 `main()`에서는 호출하지 않으며, 향후 실제 API 연동으로 대체할 예정입니다.

**동작 방식**

1. `official_price` 테이블에 공시가격이 없는 건물만 조회합니다.
2. 건물 유형과 건축년도를 기반으로 추정 공시가격을 계산합니다.

**유형별 기본 추정가**

| 건물 유형 | 기본 추정 공시가격 |
|-----------|-------------------|
| 다가구주택 | 1억 2,000만 원 |
| 연립주택 | 1억 3,000만 원 |
| 오피스텔 | 1억 8,000만 원 |
| 그 외 | 1억 2,000만 원 |

**건축년도 보정**

| 건축년도 | 보정 계수 |
|----------|-----------|
| 2000년 이전 | × 0.7 (30% 감가) |
| 2000년 ~ 2015년 | × 1.0 (변동 없음) |
| 2015년 이후 | × 1.3 (30% 가산) |

3. `official_price` 테이블에 UPSERT하며 `price_type = 'ESTIMATED'`로 추정값임을 표기합니다.

**경매 배당 시뮬레이터 연관**

```
낙찰가 = 공시가격(official_price) × 0.72 (대구 평균 낙찰가율)

소액임차인 최우선변제 (보증금 5,500만 원 이하 → 1,650만 원 보호)
    ↓
선순위 근저당 배당
    ↓
내 보증금 회수액 계산 → 회수율 (%)
```

**실행 예시**
```
공시가격 수집 대상: 120개
  건물 1 (다가구주택, 1998년): 84,000,000원 (추정값)
  건물 2 (오피스텔, 2020년): 234,000,000원 (추정값)
  건물 3 (다가구주택, 2010년): 120,000,000원 (추정값)
완료
```

---

### 4. `db_config.py` — DB 연결 설정

`.env` 파일에서 설정을 읽어 PostgreSQL 연결 객체를 반환하는 공통 모듈입니다.

```python
def get_conn():
    return psycopg2.connect(
        host=config.get("DB_HOST", "saferoom"),
        port=config.get("DB_PORT", 5433),
        dbname="saferoom",
        user=config["DB_USERNAME"],
        password=config["DB_PASSWORD"]
    )
```

> `DB_HOST` 기본값이 `"saferoom"`인 이유: Docker Compose 환경에서 서비스명으로 컨테이너 간 통신하기 위함입니다. 로컬에서 직접 실행할 경우 `.env`에 `DB_HOST=localhost`를 명시하세요.

---

`MOLIT_SERVICE_KEY`는 [공공데이터포털](https://www.data.go.kr)에서 아래 API를 신청하면 발급됩니다.

- 건축물대장정보 서비스
- 국토교통부 실거래가 정보 (단독/다가구, 오피스텔)

---

##  의존성

```
requests          # HTTP API 호출
psycopg2-binary   # PostgreSQL 드라이버
python-dotenv     # .env 환경변수 로딩
```
