# 국회의원 지역구 인구와 표의 등가성 분석

실행:
```bash
pip install -r requirements.txt
streamlit run app.py
```

이 버전은 첫 화면에서 옵션 선택 없이 1~5번 분석이 모두 보이도록 구성했습니다.

- 1: 역대 총선별 선거구 최대·최소·평균 인구 변화
- 2: 선거구별 인구수 및 표의 등가성 지수
- 3: 인접 선거구와의 인구 차이
- 4: 총선별 표의 등가성 지수 분포
- 5: 주민등록인구와 유권자수(선거인수)의 관계 분석

## 입력 파일 안내
- `data/election_history_summary.csv` : 역대 총선 요약
- `data/election_voter_summary.csv` : 주민등록인구/선거인수 요약
- `data/constituency_population_template.csv` : 선거구별 인구 데이터 템플릿

2번과 3번을 실제 색상 지도와 top 10 차트로 보려면,
`data/constituency_population.csv`를 추가하세요. 필요한 열은 아래와 같습니다.

- 총선
- 선거구명
- 시도
- 주민등록인구
- 선거인수
- 표의등가성지수
- 위도
- 경도

GeoJSON 경계는 실행 시 공개 저장소에서 불러옵니다.
