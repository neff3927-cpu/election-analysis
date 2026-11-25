from pathlib import Path
import io
import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

BASE = Path(__file__).parent
DATA = BASE / "data"

st.set_page_config(page_title="국회의원 지역구 인구와 표의 등가성 분석", page_icon="🗳️", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1800px;padding-top:1.2rem;padding-bottom:2.5rem}
h1{font-size:2.15rem!important;font-weight:800!important;letter-spacing:-.04em}
h2{font-size:1.45rem!important;font-weight:750!important}
h3{font-size:1.08rem!important}
[data-testid="stMetric"]{background:#f5f8fc;border:1px solid #e7edf4;padding:14px 16px;border-radius:12px}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px}
div[data-testid="stAlert"]{border-radius:12px}
small,.muted{color:#6b7280}
</style>
""", unsafe_allow_html=True)

FILES = {
    "constituency_population.csv": "제22대 선거구별 주민등록인구·선거인수·좌표",
    "constituency_population_23rd.csv": "제23대 가정용 인구(제22대 선거구 경계 고정)",
    "election_history_summary.csv": "역대 총선별 최대·최소·평균 인구",
    "historical_constituencies.csv": "역대 총선 선거구별 인구 원자료",
    "adjacency_population.csv": "선거구와 인접 선거구 인구",
    "region_population_seats.csv": "시도별 주민등록인구와 지역구 의석수",
    "election_voters.csv": "역대 총선별 선거인수·투표자수",
}
ALIASES = {
    "시도명":"시도", "지역명":"지역", "인구수":"주민등록인구", "주민등록인구(명)":"주민등록인구",
    "선거인 수":"선거인수", "투표자 수":"투표자수", "지역구 수":"지역구수",
    "인접 선거구":"인접선거구", "선거구 인구":"선거구인구", "인접 선거구 인구":"인접선거구인구",
    "위도":"위도", "경도":"경도"
}
NUMERIC = ["주민등록인구","선거인수","투표자수","위도","경도","이전인구","연도","최대인구","최소인구","평균인구","선거구수","지역구수","선거구인구","인접선거구인구"]

@st.cache_data(show_spinner=False)
def read_csv_bytes(raw: bytes):
    for enc in ("utf-8-sig", "cp949", "utf-8"):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception:
            pass
    raise ValueError("CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장해 주세요.")

def clean(df):
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()
    x=df.copy()
    x.columns=[str(c).replace("\ufeff","").strip() for c in x.columns]
    x=x.rename(columns={k:v for k,v in ALIASES.items() if k in x.columns and v not in x.columns})
    for c in NUMERIC:
        if c in x.columns:
            x[c]=pd.to_numeric(x[c].astype(str).str.replace(",","",regex=False).str.replace("명","",regex=False).str.strip(),errors="coerce")
    return x

def local_data(filename):
    p=DATA/filename
    if not p.exists(): return pd.DataFrame()
    try: return clean(read_csv_bytes(p.read_bytes()))
    except Exception: return pd.DataFrame()

def get_data(filename):
    if filename in st.session_state.get("uploaded",{}):
        return st.session_state.uploaded[filename].copy()
    return local_data(filename)

def has(df, cols):
    return isinstance(df,pd.DataFrame) and not df.empty and all(c in df.columns for c in cols)

def msg(text):
    st.info(text, icon="ℹ️")

def fmt(v):
    return "자료 없음" if pd.isna(v) else f"{v:,.0f}"

st.title("국회의원 지역구 인구와 표의 등가성 분석")
st.caption("산업데이터시각화 프로젝트 · 국회의원 지역구 인구 배분과 표의 등가성 탐색")
st.warning("자료 안내: 공식 원자료가 연결된 분석만 수치 결과로 표시합니다. 예시값이나 임의의 선거구 인구는 사용하지 않습니다.")

# Upload panel: filename maps directly to the expected data slot.
with st.expander("데이터 파일 연결 / 업로드", expanded=False):
    st.write("CSV를 여러 개 선택하면 파일명에 맞춰 해당 분석에 즉시 반영됩니다. 영구 반영하려면 GitHub 저장소의 `data/` 폴더에도 같은 파일을 올려주세요.")
    uploaded=st.file_uploader("CSV 여러 개 업로드", type=["csv"], accept_multiple_files=True, key="new_site_upload")
    if uploaded:
        st.session_state.setdefault("uploaded",{})
        for f in uploaded:
            try:
                st.session_state.uploaded[f.name]=clean(read_csv_bytes(f.getvalue()))
            except Exception as e:
                st.error(f"{f.name}: {e}")
        st.success("업로드한 CSV를 현재 세션에 반영했습니다.")
    st.caption("지원 파일명: " + " · ".join(FILES.keys()))
    with st.expander("CSV 필수 열 확인"):
        for fn,desc in FILES.items():
            st.markdown(f"**{fn}** — {desc}")
            st.code({
                "constituency_population.csv":"시도,선거구,주민등록인구,선거인수,투표자수,위도,경도",
                "constituency_population_23rd.csv":"시도,선거구,주민등록인구,선거인수,투표자수,위도,경도",
                "election_history_summary.csv":"총선,연도,최대인구,최소인구,평균인구,선거구수,인구기준일,출처",
                "historical_constituencies.csv":"총선,연도,시도,선거구,주민등록인구",
                "adjacency_population.csv":"선거구,인접선거구,선거구인구,인접선거구인구",
                "region_population_seats.csv":"지역,주민등록인구,지역구수",
                "election_voters.csv":"총선,시도,선거구,선거인수,투표자수",
            }[fn], language="text")

D={f:get_data(f) for f in FILES}
current=D["constituency_population.csv"]
scenario=D["constituency_population_23rd.csv"]
history=D["election_history_summary.csv"]
historical=D["historical_constituencies.csv"]
adj=D["adjacency_population.csv"]
regions=D["region_population_seats.csv"]
voters=D["election_voters.csv"]

# Global filters
with st.container(border=True):
    st.subheader("공통 입력 위젯")
    a,b,c=st.columns([1,1,1.4])
    with a: election=st.selectbox("총선 시기 선택",["제22대 총선","제23대 총선 가정","역대 총선 비교"])
    src=scenario if election=="제23대 총선 가정" else current
    reglist=sorted(src["시도"].dropna().astype(str).unique().tolist()) if has(src,["시도"]) else []
    with b: region=st.selectbox("지역 선택",["전체"]+reglist)
    distlist=sorted(src["선거구"].dropna().astype(str).unique().tolist()) if has(src,["선거구"]) else []
    with c: district=st.selectbox("선거구 검색",["전체 선거구"]+distlist)

if election=="제23대 총선 가정":
    st.info("제23대 총선 가정은 제22대 선거구 경계를 유지하고 인구 자료만 바꿔 보는 시나리오입니다. 실제 획정 결과가 아닙니다.")
elif election=="역대 총선 비교":
    st.caption("역대 총선 비교에서는 선거구별 현재 상세정보 대신 총선별 집계 자료를 사용합니다.")

# 표의 등가성 지수의 기준 평균은 지역/선거구 필터를 적용하기 전 전국 평균으로 고정
national_source=src.copy()
if has(national_source,["주민등록인구"]):
    national_source["주민등록인구"]=pd.to_numeric(national_source["주민등록인구"],errors="coerce")
    mean_pop=national_source["주민등록인구"].mean()
else:
    mean_pop=np.nan

view=src.copy()
if not view.empty:
    if region!="전체" and "시도" in view: view=view[view["시도"].astype(str)==region]
    if district!="전체 선거구" and "선거구" in view: view=view[view["선거구"].astype(str)==district]
if has(view,["주민등록인구"]):
    view=view.copy()
    view["주민등록인구"]=pd.to_numeric(view["주민등록인구"],errors="coerce")
    view["표의 등가성 지수"]=mean_pop/view["주민등록인구"].replace(0,np.nan)

map_options=["선거구별 주민등록인구","표의 등가성 지수","인접 선거구 인구편차"]
chart_options=[
    "역대 최대·최소 인구편차 비율", "역대 최대·최소·평균 인구 변화", "선거구별 인구 순위",
    "인접 선거구 인구 비교", "표의 등가성 지수 분포", "총선별 지수 1 초과·미만 비율",
    "주민등록인구와 선거인수 관계", "지역별 주민등록인구와 지역구 수 관계"
]

left,right=st.columns([1,1],gap="large")
with left:
    with st.container(border=True):
        st.header("지도 영역")
        map_metric=st.selectbox("지도 표시 기준 선택",map_options)
        st.caption("외부 타일 API 키 없이 대한민국 영역을 표시합니다. 선거구별 점 위치는 CSV의 위도·경도 자료가 있을 때만 나타납니다.")
        # 외부 타일/키 없이 표시. 좌표가 없으면 빈 Plotly 축 대신 명확한 안내를 표시
        if has(view,["위도","경도"]):
            m=view.dropna(subset=["위도","경도"]).copy()
            if not m.empty:
                if map_metric=="표의 등가성 지수" and "표의 등가성 지수" in m:
                    color=m["표의 등가성 지수"]; colorscale="RdYlBu"; cbar="표의 등가성 지수"
                elif map_metric=="선거구별 주민등록인구" and "주민등록인구" in m:
                    color=m["주민등록인구"]; colorscale="Blues"; cbar="주민등록인구(명)"
                else:
                    color=None; colorscale=None; cbar=None
                hover=[c for c in ["시도","선거구","주민등록인구","선거인수","표의 등가성 지수"] if c in m.columns]
                figmap=go.Figure(go.Scattergeo(
                    lon=m["경도"],lat=m["위도"],mode="markers",
                    text=m["선거구"] if "선거구" in m else None,
                    customdata=m[hover].to_numpy() if hover else None,
                    marker=dict(size=9,color=color if color is not None else "#2563eb",
                                colorscale=colorscale if colorscale else None,showscale=color is not None,
                                colorbar=dict(title=cbar) if cbar else None,
                                line=dict(width=0.7,color="white")),
                    hovertemplate="%{text}<br>위도 %{lat:.3f}, 경도 %{lon:.3f}<extra></extra>"
                ))
                figmap.update_geos(
                    scope="asia",projection_type="mercator",showland=True,landcolor="#edf2f7",
                    showocean=True,oceancolor="#dcecf4",showlakes=True,lakecolor="#dcecf4",
                    showcountries=True,countrycolor="#9aa9b8",showcoastlines=True,coastlinecolor="#8ba0b2",
                    lonaxis_range=[123.5,132.5],lataxis_range=[32.5,39.9],showframe=False,resolution=50
                )
                figmap.update_layout(height=610,margin=dict(l=0,r=0,t=5,b=0),paper_bgcolor="white",geo_bgcolor="#dcecf4")
                st.plotly_chart(figmap,use_container_width=True,config={"displayModeBar":False})
            else:
                msg("선택한 조건에 해당하는 선거구 좌표가 없습니다. 좌표가 포함된 constituency_population.csv를 연결하면 지도에 표시됩니다.")
        else:
            st.markdown("""
            <div style='height:610px;border:1px dashed #cbd5e1;border-radius:12px;background:linear-gradient(180deg,#f8fafc,#eef4f8);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;padding:28px;'>
              <div style='font-size:42px'>🗺️</div>
              <div style='font-size:20px;font-weight:700;margin:10px 0'>선거구 위치 데이터 연결 대기</div>
              <div style='color:#64748b;max-width:440px;line-height:1.7'>현재 CSV에 선거구별 위도·경도 또는 GeoJSON 경계가 없어 지도 마커를 표시하지 않습니다.<br>공식 좌표·경계 자료를 연결하면 이 영역에 표시됩니다.</div>
            </div>
            """,unsafe_allow_html=True)
        st.caption("지도는 좌표·경계 원자료가 연결된 경우에만 실제 위치를 표시합니다. 자료가 없을 때 임의 위치나 선거구 경계를 만들어 표시하지 않습니다.")

with right:
    with st.container(border=True):
        st.header("차트 영역")
        x,y=st.columns(2)
        with x: chart1=st.selectbox("차트 1 선택",chart_options,index=0)
        with y: chart2=st.selectbox("차트 2 선택",chart_options,index=1)

        def render_chart(choice,key):
            st.markdown(f"**{choice}**")
            fig=None
            if choice=="역대 최대·최소 인구편차 비율":
                if not has(history,["연도","최대인구","최소인구"]): return msg("election_history_summary.csv에 연도·최대인구·최소인구가 필요합니다.")
                t=history.dropna(subset=["연도","최대인구","최소인구"]).copy().sort_values("연도")
                t["인구편차 비율"]=t["최대인구"]/t["최소인구"].replace(0,np.nan)
                t["연도"]=pd.to_numeric(t["연도"],errors="coerce")
                t=t.dropna(subset=["연도"]).sort_values("연도")
                fig=px.line(t,x="연도",y="인구편차 비율",markers=True,
                            hover_data=[c for c in ["총선","최대인구","최소인구","선거구수","인구기준일","출처"] if c in t])
                # 2:1은 현행 참고선일 뿐, 과거 총선에 소급해 위법 여부를 판정하지 않음
                fig.add_hline(y=2,line_dash="dash",line_color="#dc6b6b",annotation_text="2:1 현행 기준 참고선")
                lo=float(t["인구편차 비율"].min()); hi=float(t["인구편차 비율"].max())
                pad=max((hi-lo)*0.25,0.006)
                fig.update_yaxes(title="최대 인구 ÷ 최소 인구(배)",tickformat=".3f",
                                 range=[min(lo- pad,1.90),max(hi+pad,2.06)],dtick=0.02)
                st.caption("주의: 2:1 선은 현행 기준을 이해하기 위한 참고선이며, 과거 총선 당시의 법적 기준과 다를 수 있어 소급 판정에 사용하지 않습니다.")
            elif choice=="역대 최대·최소·평균 인구 변화":
                if not has(history,["연도","최대인구","최소인구","평균인구"]): return msg("election_history_summary.csv에 총선별 최대·최소·평균 인구가 필요합니다.")
                t=history.dropna(subset=["연도","최대인구","최소인구","평균인구"]).sort_values("연도")
                fig=go.Figure()
                for col,label in [("최대인구","최대"),("최소인구","최소"),("평균인구","평균")]:
                    fig.add_trace(go.Scatter(x=t["연도"].astype(int),y=t[col],mode="lines+markers",name=label,customdata=t["총선"] if "총선" in t else None,hovertemplate="%{x}년<br>%{y:,.0f}명<extra></extra>"))
                fig.update_yaxes(title="인구(명)",tickformat=",")
            elif choice=="선거구별 인구 순위":
                if not has(view,["선거구","주민등록인구"]): return msg("constituency_population.csv에 선거구별 주민등록인구가 필요합니다.")
                t=view.dropna(subset=["주민등록인구"]).sort_values("주민등록인구",ascending=False)
                if t.empty:return msg("유효한 선거구 인구 자료가 없습니다.")
                n=st.selectbox("표시 선거구 수",[10,20,50,100,254],index=0,key=f"n_{key}")
                t=t.head(n)
                fig=px.bar(t,x="주민등록인구",y="선거구",orientation="h",color="시도" if "시도" in t else None,hover_data=[c for c in ["시도","선거인수"] if c in t])
                fig.update_yaxes(categoryorder="total ascending"); fig.update_xaxes(title="주민등록인구(명)",tickformat=",")
            elif choice=="인접 선거구 인구 비교":
                if not has(adj,["선거구","인접선거구","선거구인구","인접선거구인구"]): return msg("adjacency_population.csv에 선거구·인접선거구·양쪽 인구가 필요합니다.")
                chosen=district if district!="전체 선거구" else (str(view.iloc[0]["선거구"]) if has(view,["선거구"]) and len(view) else None)
                if not chosen:return msg("공통 입력 위젯에서 선거구를 선택해 주세요.")
                t=adj[adj["선거구"].astype(str)==str(chosen)]
                if t.empty:return msg(f"{chosen}의 인접 선거구 자료가 없습니다.")
                long=pd.concat([pd.DataFrame({"선거구":t["선거구"],"인구":t["선거구인구"]}),pd.DataFrame({"선거구":t["인접선거구"],"인구":t["인접선거구인구"]})]).dropna()
                fig=px.bar(long,x="인구",y="선거구",orientation="h",color="선거구")
            elif choice=="표의 등가성 지수 분포":
                if not has(view,["선거구","주민등록인구"]):return msg("선거구별 주민등록인구 자료가 있어야 지수를 계산할 수 있습니다.")
                t=view.dropna(subset=["주민등록인구"]).copy()
                if t.empty:return msg("유효한 인구 자료가 없습니다.")
                t["지수"]=mean_pop/t["주민등록인구"].replace(0,np.nan)
                fig=px.histogram(t,x="지수",nbins=20)
                fig.add_vline(x=1,line_dash="dash",line_color="#dc6b6b",annotation_text="전국 평균=1")
                fig.update_xaxes(title="표의 등가성 지수(주민등록인구 기준)")
            elif choice=="총선별 지수 1 초과·미만 비율":
                if not has(historical,["총선","주민등록인구"]):return msg("historical_constituencies.csv에 역대 총선별 선거구 인구 원자료가 필요합니다.")
                t=historical.dropna(subset=["총선","주민등록인구"]).copy()
                t["평균인구"]=t.groupby("총선")["주민등록인구"].transform("mean")
                t["지수"]=t["평균인구"]/t["주민등록인구"].replace(0,np.nan)
                t["분류"]=np.select([t["지수"]>1,t["지수"]<1],["1 초과(평균보다 인구 적음)","1 미만(평균보다 인구 많음)"],default="1")
                p=pd.crosstab(t["총선"],t["분류"],normalize="index").mul(100).reset_index().melt(id_vars="총선",var_name="분류",value_name="비율")
                fig=px.bar(p,x="총선",y="비율",color="분류",barmode="stack"); fig.update_yaxes(title="선거구 비율(%)",range=[0,100])
            elif choice=="주민등록인구와 선거인수 관계":
                if not has(view,["주민등록인구","선거인수"]):return msg("선거구별 주민등록인구와 선거인수 열이 모두 필요합니다.")
                t=view.dropna(subset=["주민등록인구","선거인수"])
                if t.empty:return msg("유효한 선거인수 자료가 없습니다.")
                fig=px.scatter(t,x="주민등록인구",y="선거인수",color="시도" if "시도" in t else None,hover_name="선거구" if "선거구" in t else None,trendline="ols" if len(t)>=3 else None)
                fig.update_xaxes(title="주민등록인구(명)",tickformat=","); fig.update_yaxes(title="선거인수(명)",tickformat=",")
            elif choice=="지역별 주민등록인구와 지역구 수 관계":
                if not has(regions,["지역","주민등록인구","지역구수"]):return msg("region_population_seats.csv에 지역별 주민등록인구와 지역구수가 필요합니다.")
                t=regions.dropna(subset=["주민등록인구","지역구수"])
                if len(t)<3:return msg("시도별 주민등록인구 자료가 부족합니다. 같은 기준일의 공식 인구를 입력해 주세요.")
                fig=px.scatter(t,x="주민등록인구",y="지역구수",text="지역",trendline="ols")
                fig.update_traces(textposition="top center"); fig.update_xaxes(title="주민등록인구(명)",tickformat=","); fig.update_yaxes(title="지역구 의석수(석)")
            if fig is not None:
                fig.update_layout(height=390,margin=dict(l=10,r=10,t=35,b=10),legend_title_text="",font=dict(family="Arial, sans-serif"))
                st.plotly_chart(fig,use_container_width=True,key=f"plot_{key}")
        render_chart(chart1,"one")
        st.divider()
        render_chart(chart2,"two")

st.divider()
st.header("선거구 상세정보")
if has(view,["선거구","주민등록인구"]) and not view.dropna(subset=["주민등록인구"]).empty:
    chosen=district if district!="전체 선거구" else str(view.dropna(subset=["주민등록인구"]).iloc[0]["선거구"])
    row=view[view["선거구"].astype(str)==str(chosen)].iloc[0]
    c1,c2,c3,c4=st.columns(4)
    c1.metric("선거구",chosen)
    c2.metric("주민등록인구",f"{fmt(row['주민등록인구'])}명")
    c3.metric("선거인수",f"{fmt(row['선거인수'])}명" if "선거인수" in row and pd.notna(row["선거인수"]) else "자료 없음")
    c4.metric("표의 등가성 지수",f"{row['표의 등가성 지수']:.3f}" if "표의 등가성 지수" in row and pd.notna(row["표의 등가성 지수"]) else "자료 없음")
    if "시도" in row: st.caption(f"지역: {row['시도']}")
else:
    msg("실제 선거구별 인구 CSV를 연결하면 선택한 선거구의 주민등록인구·선거인수·표의 등가성 지수가 표시됩니다.")

with st.expander("데이터 출처 및 해석상 유의점"):
    st.markdown("""
- 주민등록인구 및 행정구역 자료: 행정안전부 주민등록 인구통계(https://jumin.mois.go.kr/)
- 선거구·선거인수·투표자수 자료: 중앙선거관리위원회 선거통계시스템(https://info.nec.go.kr/)
- 법령상 선거구 획정 기준: 공직선거법 제25조(국가법령정보센터 https://www.law.go.kr/)
- 표의 등가성 지수는 이 프로젝트에서 **전국 평균 선거구 인구 ÷ 해당 선거구 인구**로 정의한 탐색 지표이며 실제 투표 영향력을 직접 측정하지 않습니다.
- 주민등록인구, 선거인수, 투표자수는 서로 다른 개념이며 기준일을 구분해 해석해야 합니다.
- 제23대 총선 가정은 제22대 경계를 고정한 시나리오일 뿐 실제 선거구 획정안이 아닙니다.
- 지도는 외부 타일 API에 의존하지 않습니다. 선거구별 실제 경계 표시를 위해서는 제22대 선거구 GeoJSON 파일이 별도로 필요합니다.
""")

st.caption("이 대시보드는 공개자료를 바탕으로 한 수업 프로젝트용 분석 도구입니다. 데이터 기준일·출처·경계 일치 여부를 확인한 뒤 결과를 해석하세요.")
