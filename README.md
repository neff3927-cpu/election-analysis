# 국회의원 지역구 인구와 표의 등가성 분석

## 실행
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud 배포
1. 이 폴더의 파일을 GitHub 저장소 루트에 업로드합니다.
2. Streamlit Community Cloud에서 해당 저장소와 `app.py`를 선택해 배포합니다.
3. 이 앱은 NEC API 키를 사용하지 않습니다. 비밀키를 Secrets에 넣을 필요가 없습니다.

## 포함 데이터
- `data/election_history_summary.csv`: 제20·21·22대 총선 요약
- `data/election_voters_national.csv`: 전국 주민등록인구 및 선거인수 요약
- `data/admin_dong_population_reference.csv`: KOSIS에서 추출한 2015.10, 2019.01, 2023.01 읍면동별 총인구

## 중요
선거구별 공식 인구 원자료와 선거구 경계의 완전한 결합표는 아직 확보되지 않았습니다. 따라서 지도·Top 10·인접 비교·분포는 **시각화용 모형 추정치**이며 실제 관측값이나 공식 순위로 인용하면 안 됩니다. 전국 총계와 최대·최소·평균 요약은 별도 표기된 자료 기준입니다.
