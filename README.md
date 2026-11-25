# 중앙선관위 선거인수 수집 수정본

- 정상 응답 `INFO-000 / NORMAL SERVICE` 처리
- 실제 JSON wrapper `response.body.items.item` 파싱
- 제20·21대 시도명: 강원도, 전라북도
- 제22대 시도명: 강원특별자치도, 전북특별자치도
- 제22대 누락된 2개 시도를 현행 명칭으로 재조회하도록 수정

배포: GitHub의 `app.py`와 `requirements.txt`를 교체하고 Commit.
Streamlit Secrets에 SERVICE_KEY는 기존 값 그대로 유지.
전국 수집 후 CSV의 제22대 시도수가 17개인지 확인.
