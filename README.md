# 국회의원 지역구 인구와 표의 등가성 분석

## API 수집 수정
- 선거구별 선거인수 API: `getElpcElcntInfoInqire`
- 국회의원선거 코드: `sgTypecode=2`
- 시도별 조회: `sdName` 사용
- `wiwName`은 지방의회의원 선거 조건이므로 국회의원선거 요청에서 제외
- 서울특별시 테스트와 전국 수집 버튼 제공
- API 응답 오류 원문 일부를 화면에 표시

## Streamlit Secrets
```toml
SERVICE_KEY = "공공데이터포털 일반 인증키"
```
키를 GitHub에 올리지 마세요.

앱에서 서울특별시 테스트 버튼을 먼저 실행한 뒤 전국 수집 버튼을 사용하세요.
