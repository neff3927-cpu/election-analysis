# 국회의원 지역구 인구와 표의 등가성 분석 — 신규 버전

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## 새 버전의 핵심 변경
- 기존 Folium/CARTO 타일 의존성을 제거했습니다. 지도는 Plotly 지리 기반도를 사용하므로 CARTO API KEY REQUIRED 워터마크가 나타나지 않습니다.
- 지도에 선거구별 점을 표시하려면 `constituency_population.csv`에 `위도`, `경도` 열이 필요합니다.
- 선거구 폴리곤은 실제 제22대 선거구 GeoJSON이 확보된 뒤 연결해야 합니다. 임의 경계를 만들지 않습니다.
- 차트는 데이터가 부족하면 KeyError/빈 그래프 대신 필요한 파일과 열을 안내합니다.
- 업로드한 CSV는 파일명에 따라 세션에 반영됩니다. 영구 반영은 GitHub 저장소의 `data/` 폴더에 업로드해야 합니다.

## 데이터 파일 형식
| 파일 | 필수 열 |
|---|---|
| `constituency_population.csv` | 시도, 선거구, 주민등록인구, 선거인수, 투표자수, 위도, 경도 |
| `constituency_population_23rd.csv` | 시도, 선거구, 주민등록인구, 선거인수, 투표자수, 위도, 경도 |
| `election_history_summary.csv` | 총선, 연도, 최대인구, 최소인구, 평균인구 |
| `historical_constituencies.csv` | 총선, 연도, 시도, 선거구, 주민등록인구 |
| `adjacency_population.csv` | 선거구, 인접선거구, 선거구인구, 인접선거구인구 |
| `region_population_seats.csv` | 지역, 주민등록인구, 지역구수 |
| `election_voters.csv` | 총선, 시도, 선거구, 선거인수, 투표자수 |

## 분석 옵션
1. 역대 최대·최소 인구편차 비율
2. 역대 최대·최소·평균 인구 변화
3. 선거구별 인구 순위
4. 인접 선거구 인구 비교
5. 표의 등가성 지수 분포
6. 총선별 지수 1 초과·미만 비율
7. 주민등록인구와 선거인수 관계
8. 지역별 주민등록인구와 지역구 수 관계

Box Plot, 인구증감률과 지수 관계, 지역구 1석당 인구 차트, 선거구 편입·분리 시뮬레이션은 포함하지 않았습니다.

## 주의
기존 작업 폴더의 CSV 중 다수는 헤더만 있고 데이터 행이 없습니다. 신규 버전은 없는 데이터를 만들어내지 않으며, 실제 원자료를 연결해야 해당 분석이 표시됩니다.
