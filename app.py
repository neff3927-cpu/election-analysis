from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import folium
from streamlit_folium import st_folium
import requests

ROOT = Path(__file__).parent
DATA = ROOT / "data"
GEOJSON_URL = "https://raw.githubusercontent.com/OhmyNews/2024_22_elec_map/main/2024_22_Elec_simplify.json"

st.set_page_config(page_title="국회의원 지역구 인구와 표의 등가성 분석", layout="wide")
st.markdown("""
<style>
.block-container{padding-top:1.2rem;padding-bottom:2rem;max-width:1500px}
.section{font-size:1.35rem;font-weight:750;margin:.25rem 0 .15rem}
.sub{color:#68717d;font-size:.92rem;margin-bottom:.7rem}
.smallnote{font-size:.86rem;color:#68717d}
</style>
""", unsafe_allow_html=True)
st.title("국회의원 지역구 인구와 표의 등가성 분석")
st.caption("제20~22대 국회의원 총선거 자료를 활용한 인구 대표성 분석")
st.info("모든 분석은 이 페이지에 순서대로 표시됩니다. 별도 CSV 업로드나 분석 옵션 선택은 필요하지 않습니다.")


# 중앙선관위 선거구별 선거인수 API 연결 및 원자료 수집
# 국회의원선거(sgTypecode=2)는 시도명(sdName)으로 조회한다.
# wiwName은 지방의회의원 선거 조회용이므로 국회의원선거 요청에는 전달하지 않는다.
from urllib.parse import unquote

API_URL = "https://apis.data.go.kr/9760000/ElcntInfoInqireService/getElpcElcntInfoInqire"
ELECTIONS = {"제20대": "20160413", "제21대": "20200415", "제22대": "20240410"}
SIDO_NAMES_OLD = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원도",
    "충청북도", "충청남도", "전라북도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도"
]
# 제22대 당시 강원특별자치도·전북특별자치도 명칭 사용
SIDO_NAMES_2024 = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도"
]

def get_service_key():
    try:
        return unquote(str(st.secrets["SERVICE_KEY"]).strip())
    except Exception:
        return None

def parse_nec_response(response):
    text_body = response.text
    try:
        payload = response.json()
    except Exception:
        import xml.etree.ElementTree as ET
        try:
            root_xml = ET.fromstring(text_body)
            payload = {child.tag: child.text for child in root_xml}
        except Exception:
            raise RuntimeError(f"응답 해석 실패. HTTP {response.status_code}, 본문={text_body[:700]}")
    # NEC API JSON 실제 응답은 {"response":{"header":...,"body":...}} wrapper 구조임.
    # wrapper를 먼저 해제해야 body.items.item 배열을 읽을 수 있음.
    root = payload.get("response", payload) if isinstance(payload, dict) else {}
    if isinstance(root, dict) and "getElpcElcntInfoInqire" in root:
        root = root["getElpcElcntInfoInqire"]
    header = root.get("header", {}) if isinstance(root, dict) else {}
    body = root.get("body", {}) if isinstance(root, dict) else {}
    code = str(header.get("resultCode", "")) if isinstance(header, dict) else ""
    msg = str(header.get("resultMsg", "")) if isinstance(header, dict) else ""
    # 공공데이터포털의 정상 응답은 INFO-000 / NORMAL SERVICE.
    # 일부 응답에서는 코드 표기가 INFO-00 등으로 축약되어 올 수 있으므로
    # resultMsg가 NORMAL SERVICE이면 정상으로 처리한다.
    is_normal = (msg.strip().upper() == "NORMAL SERVICE") or code in ("00", "0", "INFO-000") or code.startswith("INFO-0")
    if code and not is_normal:
        raise RuntimeError(f"API 오류 {code}: {msg}; 응답={text_body[:700]}")
    items = []
    if isinstance(body, dict):
        wrapped = body.get("items", {})
        if isinstance(wrapped, dict): items = wrapped.get("item", [])
        elif isinstance(wrapped, list): items = wrapped
        elif isinstance(wrapped, str): items = []
    if isinstance(items, dict): items = [items]
    if not items and isinstance(root, dict):
        items = root.get("item", [])
        if isinstance(items, dict): items = [items]
    total = None
    if isinstance(body, dict):
        try: total = int(body.get("totalCount"))
        except (TypeError, ValueError): pass
    return items or [], total, payload

def call_district_electors(election_id, service_key, sido_name, page=1, rows=1000):
    params = {
        "serviceKey": service_key, "pageNo": page, "numOfRows": rows,
        "resultType": "json", "sgId": election_id, "sgTypecode": "2",
        "sdName": sido_name
        # wiwName deliberately omitted for National Assembly elections.
    }
    response = requests.get(API_URL, params=params, timeout=40)
    items, total, payload = parse_nec_response(response)
    return items, total, payload, response

def fetch_sido_for_election(election_id, service_key, sido_name):
    collected=[]
    for page in range(1, 31):
        items, total, payload, response = call_district_electors(election_id, service_key, sido_name, page, 1000)
        if not items:
            if page == 1:
                raise RuntimeError(f"{sido_name}: 0건. HTTP={response.status_code}, 응답={response.text[:700]}")
            break
        collected.extend(items)
        if (total is not None and len(collected) >= total) or len(items) < 1000: break
    return collected

with st.expander("중앙선관위 API 연결 및 선거구별 유권자 원자료 수집", expanded=False):
    st.markdown("Streamlit Secrets의 `SERVICE_KEY`를 사용합니다. 국회의원선거는 `sgTypecode=2`, `sdName`으로 조회하며 `wiwName`은 전달하지 않습니다.")
    key = get_service_key()
    c1, c2 = st.columns(2)
    with c1: test_clicked = st.button("서울특별시 테스트 (제20~22대)", key="test_nec_seoul")
    with c2: collect_clicked = st.button("전국 20~22대 전체 수집", key="fetch_official_electors")
    if not key:
        st.error('SERVICE_KEY를 찾지 못했습니다. Streamlit Cloud → App settings → Secrets에 SERVICE_KEY = "발급키" 형식으로 저장해 주세요.')
    if test_clicked and key:
        for label, eid in ELECTIONS.items():
            try:
                items, total, payload, response = call_district_electors(eid, key, "서울특별시")
                st.success(f"{label}: 서울특별시 응답 {len(items)}행 수신 (HTTP {response.status_code}, API totalCount={total})")
                if items:
                    st.dataframe(pd.DataFrame(items), use_container_width=True)
                    st.caption("API 응답 원자료입니다. 합계 행과 실제 지역구 행을 구분해 CSV로 정리합니다.")
                else:
                    st.warning(f"{label}: 0건. API 응답: {json.dumps(payload, ensure_ascii=False)[:1200]}")
            except Exception as exc: st.error(f"{label} 테스트 실패: {exc}")
    if collect_clicked and key:
        collected = []
        errors = []
        tasks = []
        for label, eid in ELECTIONS.items():
            sido_list = SIDO_NAMES_2024 if label == "제22대" else SIDO_NAMES_OLD
            tasks.extend((label, eid, sido) for sido in sido_list)

        progress = st.progress(0)
        status = st.empty()
        for i, (label, eid, sido) in enumerate(tasks, start=1):
            status.caption(f"수집 중: {label} / {sido} ({i}/{len(tasks)})")
            try:
                rows = fetch_sido_for_election(eid, key, sido)
                for row in rows:
                    row["총선"] = label
                    row["선거ID"] = eid
                    row["조회시도"] = sido
                collected.extend(rows)
            except Exception as exc:
                errors.append(f"{label} / {sido}: {exc}")
            progress.progress(i / len(tasks))

        status.empty()
        if collected:
            raw = pd.DataFrame(collected)
            st.success(f"전체 수집 결과: {len(raw):,}행")
            st.dataframe(raw.head(50), use_container_width=True)
            st.download_button(
                "제20~22대 선거구별 선거인수 CSV 다운로드",
                raw.to_csv(index=False, encoding="utf-8-sig"),
                file_name="district_electors_20_22.csv",
                mime="text/csv",
            )
        if errors:
            with st.expander(f"조회 오류 상세 ({len(errors)}건)"):
                for error in errors:
                    st.error(error)
        if not collected:
            st.error("수집된 자료가 없습니다. 오류 상세의 API 응답코드와 메시지를 확인해 주세요.")

# All figures below are national totals / officially reported summary figures.
# District-level raw population and district-level elector counts are not bundled unless verified.
history = pd.DataFrame([
    {"총선":"제20대", "연도":2016, "기준인구일":"2015-10-31", "지역구수":253,
     "최대인구":278982, "최소인구":140126, "평균인구":51465228/253, "전국인구":51465228},
    {"총선":"제21대", "연도":2020, "기준인구일":"2019-01-31", "지역구수":253,
     "최대인구":277912, "최소인구":139027, "평균인구":51826287/253, "전국인구":51826287},
    {"총선":"제22대", "연도":2024, "기준인구일":"2023-01-31", "지역구수":254,
     "최대인구":273177, "최소인구":136629, "평균인구":51297846/254, "전국인구":51297846},
])
# Population and electors are election-year national totals, not constituency-level pairs.
voters = pd.DataFrame([
    {"총선":"제20대", "연도":2016, "주민등록인구":51623293, "선거인수":42100398},
    {"총선":"제21대", "연도":2020, "주민등록인구":51843268, "선거인수":43994247},
    {"총선":"제22대", "연도":2024, "주민등록인구":51297846, "선거인수":44280011},
])

@st.cache_data(show_spinner=False, ttl=86400)
def get_geojson():
    local = DATA / "constituencies_22.geojson"
    if local.exists():
        try: return json.loads(local.read_text(encoding="utf-8"))
        except Exception: pass
    try:
        r=requests.get(GEOJSON_URL, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
        r.raise_for_status()
        obj=r.json()
        if obj.get("type")=="FeatureCollection": return obj
    except Exception:
        return None
    return None

def base_map(key, height=520, fill="#d9dfe7"):
    geo=get_geojson()
    if not geo:
        st.warning("선거구 경계 파일을 불러오지 못했습니다. 인터넷 연결 후 다시 열어 주세요.")
        return
    m=folium.Map(location=[36.35,127.8], zoom_start=6, tiles="OpenStreetMap", control_scale=True)
    folium.GeoJson(geo, name="제22대 선거구 경계",
        style_function=lambda f:{"fillColor":fill,"color":"#667085","weight":0.65,"fillOpacity":0.55},
        tooltip=folium.GeoJsonTooltip(fields=["SIDO_SGG"], aliases=["선거구:"])).add_to(m)
    st_folium(m, height=height, use_container_width=True, key=key, returned_objects=[])

# 1
with st.container(border=True):
    st.markdown('<div class="section">1. 역대 총선별 선거구 최대·최소·평균 인구 변화</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">각 총선의 선거구 획정 기준일 인구를 기준으로 비교</div>', unsafe_allow_html=True)
    fig=go.Figure()
    for col,label in [("최대인구","최대 인구"),("평균인구","평균 인구"),("최소인구","최소 인구")]:
        fig.add_trace(go.Scatter(x=history["총선"],y=history[col],mode="lines+markers+text",name=label,
            text=[f"{v:,.0f}" for v in history[col]],textposition="top center",hovertemplate="%{x}<br>%{y:,.0f}명<extra></extra>"))
    fig.update_layout(height=370,margin=dict(l=15,r=15,t=30,b=10),legend=dict(orientation="h",y=1.12),yaxis_title="인구(명)")
    fig.update_yaxes(tickformat=",")
    st.plotly_chart(fig,use_container_width=True,key="chart_1")
    st.caption("※ 총선별 인구 기준일과 지역구 수가 다르므로 기준일·의석수를 함께 확인해야 합니다.")

# 2
with st.container(border=True):
    st.markdown('<div class="section">2. 선거구별 인구수 및 표의 등가성 지수</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">지도 + 선거구별 인구수 및 지수 Top 10 차트</div>', unsafe_allow_html=True)
    a,b=st.columns([1.05,.95],gap="large")
    with a:
        st.markdown("**선거구 인구 지도**")
        base_map("district_population_map",540)
        st.caption("현재 포함된 지도는 제22대 선거구 경계 참고용입니다. 선거구별 인구 원자료가 확인되지 않아 인구 단계별 색상은 적용하지 않았습니다.")
    with b:
        st.markdown("**선거구별 인구수 및 표의 등가성 지수 Top 10**")
        st.warning("제20~22대 전체 선거구별 인구 원자료가 아직 프로젝트에 포함되지 않았습니다. 실제 Top 10을 계산할 수 없어 임의의 순위나 수치를 표시하지 않습니다.")
        st.markdown("표의 등가성 지수 = 해당 총선 전국 평균 선거구 인구 ÷ 해당 선거구 인구")
        st.markdown("지수 1 초과: 전국 평균보다 인구가 적음 / 1 미만: 전국 평균보다 인구가 많음")

# 3
with st.container(border=True):
    st.markdown('<div class="section">3. 인접 선거구와의 인구 차이</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">인접 선거구 평균 인구보다 많으면 빨강, 적으면 파랑, 같으면 회색</div>', unsafe_allow_html=True)
    base_map("neighbor_population_map",600)
    st.caption("※ 인접 관계는 실제 경계를 공유하는 선거구 기준으로 계산해야 합니다. 현재는 선거구별 인구 원자료가 없어 비교 색상을 적용하지 않은 경계 지도입니다.")

# 4
with st.container(border=True):
    st.markdown('<div class="section">4. 총선별 표의 등가성 지수 분포</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">선거구별 원자료가 확보되면 분포(Box Plot)를 산출할 수 있습니다.</div>', unsafe_allow_html=True)
    # Derived extrema of index from verified min/max/mean; not a distribution plot.
    dist=[]
    for _,r in history.iterrows():
        dist.append({"총선":r["총선"],"최대인구 선거구의 지수":r["평균인구"]/r["최대인구"],"최소인구 선거구의 지수":r["평균인구"]/r["최소인구"]})
    d=pd.DataFrame(dist)
    fig4=go.Figure()
    for _,r in d.iterrows():
        fig4.add_trace(go.Scatter(x=[r["최대인구 선거구의 지수"],r["최소인구 선거구의 지수"]],y=[r["총선"],r["총선"]],
            mode="lines+markers",name=r["총선"],showlegend=False,hovertemplate="%{y}<br>지수 %{x:.3f}<extra></extra>"))
    fig4.add_vline(x=1,line_dash="dash",line_color="#555")
    fig4.update_layout(height=330,margin=dict(l=15,r=15,t=25,b=15),xaxis_title="표의 등가성 지수",yaxis_title="총선",showlegend=False)
    st.plotly_chart(fig4,use_container_width=True,key="chart_4")
    st.caption("※ 전체 선거구 분포가 아니라, 공개된 최대·최소 인구와 평균으로 계산한 지수의 양 끝 범위입니다. 실제 분포(Box Plot)로 오인하지 않도록 범위로 표시했습니다.")

# 5
with st.container(border=True):
    st.markdown('<div class="section">5. 주민등록인구와 유권자수(선거인수)의 관계 분석</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub">총선별 전국 주민등록인구와 선거인수의 관계 · 산점도 및 추세선</div>', unsafe_allow_html=True)
    fig5=go.Figure()
    fig5.add_trace(go.Scatter(x=voters["주민등록인구"],y=voters["선거인수"],mode="markers+text",text=voters["총선"],
        textposition="top center",marker=dict(size=13),name="총선별 전국값",hovertemplate="%{text}<br>주민등록인구 %{x:,.0f}명<br>선거인수 %{y:,.0f}명<extra></extra>"))
    if len(voters)>=2:
        slope,intercept=np.polyfit(voters["주민등록인구"],voters["선거인수"],1)
        xs=np.linspace(voters["주민등록인구"].min(),voters["주민등록인구"].max(),100)
        fig5.add_trace(go.Scatter(x=xs,y=slope*xs+intercept,mode="lines",name="선형 추세선",line=dict(dash="dash")))
    fig5.update_layout(height=390,margin=dict(l=15,r=15,t=25,b=15),xaxis_title="주민등록인구(명)",yaxis_title="선거인수(명)",legend=dict(orientation="h",y=1.12))
    fig5.update_xaxes(tickformat=","); fig5.update_yaxes(tickformat=",")
    st.plotly_chart(fig5,use_container_width=True,key="chart_5")
    show=voters.copy(); show["선거인수 비율(%)"]=show["선거인수"]/show["주민등록인구"]*100
    st.dataframe(show.style.format({"주민등록인구":"{:,.0f}","선거인수":"{:,.0f}","선거인수 비율(%)":"{:.2f}%"}),use_container_width=True,hide_index=True)
    st.caption("※ 5번은 전국 단위 3개 관측값의 관계입니다. 선거구별 대응 자료가 아니므로 지역구별 상관관계로 해석하면 안 됩니다. 주민등록인구와 선거인수의 기준일도 서로 다를 수 있습니다.")

with st.expander("자료 기준 및 한계"):
    st.markdown("""
    - 1번: 선거구 획정 기준일의 전국 주민등록인구 및 지역구 수를 이용한 평균과, 총람·획정 자료에 보고된 최대·최소 인구를 표시합니다.
    - 2·3·4번: 선거구별 전체 원자료가 아직 확보되지 않아 색상 지도, Top 10, 실제 분포를 산출하지 않았습니다.
    - 5번: 중앙선관위·행정안전부 공개 전국 합계 기반의 참고 분석이며 선거구 단위 분석이 아닙니다.
    - 인구 기준일과 선거인명부 확정일은 다르므로 두 값의 차이를 해석할 때 기준일을 확인해야 합니다.
    """)
    st.markdown("출처: 중앙선거관리위원회 제20~22대 국회의원선거 총람 및 선거구획정 자료, 행정안전부 선거인수 보도자료.")
