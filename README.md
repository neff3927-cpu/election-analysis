# 국회의원 지역구 인구와 표의 등가성 분석

## API 응답 처리 수정
- 중앙선관위 선거구별 선거인수 API `getElpcElcntInfoInqire`
- 국회의원선거 `sgTypecode=2`, `sdName` 기반 조회
- `INFO-000 / NORMAL SERVICE` 정상 응답을 오류로 처리하지 않도록 수정
- API의 `response.body.items.item` 구조 파싱
- 응답 행과 `totalCount`를 화면에 표시
- 합계 행(`sggName=합계`)과 개별 행을 구분할 수 있도록 안내

## 배포
GitHub 저장소 최상위에 `app.py`, `requirements.txt`, `data/`를 업로드합니다.
Streamlit Cloud → App settings → Secrets:
```toml
SERVICE_KEY = "공공데이터포털 일반 인증키"
```
인증키를 GitHub에 올리지 마세요.

서울 테스트에서 실제 응답 행이 표시되는지 확인한 뒤 전국 수집을 실행하세요.
