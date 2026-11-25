# 국회의원 지역구 인구와 표의 등가성 분석

## Streamlit Cloud 배포 시 필수
이 프로젝트는 지도 표시를 위해 `folium`과 `streamlit-folium`을 사용합니다.
따라서 `app.py`만 업로드하면 `ModuleNotFoundError: No module named 'folium'` 오류가 발생합니다.

GitHub 저장소 최상위(루트)에 아래 항목을 함께 업로드하세요.
- `app.py`
- `requirements.txt`
- `data/` 폴더 전체

`requirements.txt`가 루트에 있어야 Streamlit Cloud가 필요한 패키지를 설치합니다.

## 배포 후
Streamlit Cloud에서 앱을 재부팅하거나 Reboot app을 실행하세요.
