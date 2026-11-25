# 데이터 파일 안내

## 1. election_history_summary.csv
역대 총선별 인구 요약값(최대·최소·평균)을 담습니다.

## 2. election_voter_summary.csv
총선별 주민등록인구와 선거인수(유권자 수) 요약값을 담습니다.

## 3. constituency_population_template.csv
선거구별 인구 데이터 입력용 템플릿입니다. 실제 분석을 하려면 아래 열이 채워진 CSV를 준비해 `data/constituency_population.csv`로 저장하면 됩니다.

필수 열 예시:
- 총선
- 선거구명
- 시도
- 주민등록인구
- 선거인수
- 표의등가성지수
- 위도
- 경도

위도·경도는 지도 마커가 필요할 때 사용합니다. GeoJSON 경계 파일과 함께 쓰면 2번·3번 분석이 작동합니다.
