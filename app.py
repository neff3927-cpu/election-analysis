from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

BASE = Path(__file__).parent
DATA = BASE / "data"
GEOJSON_URL = "https://raw.githubusercontent.com/OhmyNews/2024_22_elec_map/main/2024_22_Elec_simplify.json"

st.set_page_config(page_title="표의 등가성 | 지역구 인구 분석", page_icon="🗳️", layout="wide")
st.markdown("""
<style>
.block-container{max-width:1500px;padding-top:1.2rem;padding-bottom:2rem}
h1{font-weight:850;letter-spacing:-.04em}
h2{font-weight:800;letter-spacing:-.03em}
h3{font-weight:700}
[data-testid="stMetric"]{background:#f5f7fb;border:1px solid #e5eaf1;padding:12px 15px;border-radius:12px}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:14px}
.small-note{color:#64748b;font-size:.9rem}
</style>
""", unsafe_allow_html=True)

st.title("국회의원 지역구 인구와 표의 등가성")
st.caption("산업데이터시각화 프로젝트  |  제20·21·22대 국회의원선거 비교")
st.markdown("""
이 대시보드는 선거구별 인구 규모가 지역 대표성에 어떤 차이를 만드는지 탐색합니다.
**표의 등가성 지수 = 전국 평균 선거구 인구 ÷ 해당 선거구 인구**로 정의합니다.
지수가 1보다 크면 평균보다 인구가 적은 선거구, 1보다 작으면 평균보다 인구가 많은 선거구입니다.
""")

history = pd.read_csv(DATA/"election_history_summary.csv")
voters = pd.read_csv(DATA/"election_voters_national.csv")

def fmt(v):
    return f"{v:,.0f}"

@st.cache_data(show_spinner="제22대 선거구 경계 자료를 불러오는 중입니다.", ttl=86400)
def load_geo():
    r=requests.get(GEOJSON_URL,timeout=30)
    r.raise_for_status()
    gj=r.json()
    if not gj.get("features"):
        raise ValueError("GeoJSON에 선거구 경계가 없습니다.")
    return gj

def get_key(feature):
    p=feature.get("properties",{})
    for k in ("SIDO_SGG","SIDO_SGG_NM","SGG","SIGUNGU"):
        if p.get(k) not in (None,""):
            return str(p[k])
    return None

def get_region(feature):
    p=feature.get("properties",{})
    for k in ("SIDO","SIDO_NM","SIDO_NAME"):
        if p.get(k) not in (None,""):
            return str(p[k])
    return "기타"

def estimated_population(geo):
    """명시적 시각화용 모형값: 실제 선거구별 원자료가 아닌 전국 요약통계를 제약조건으로 둔 추정치."""
    feats=[f for f in geo["features"] if get_key(f)]
    n=len(feats)
    row=history.loc[history["연도"]==2024].iloc[0]
    mean=float(row["평균인구"]); low=float(row["최소인구"]); high=float(row["최대인구"])
    rng=np.random.default_rng(221)
    vals=rng.lognormal(mean=np.log(mean)-0.5*0.12**2,sigma=0.12,size=n)
    vals=np.clip(vals,low,high)
    # Adjust the generated series to the official average while retaining the supplied range.
    vals=vals*(mean/vals.mean())
    vals=np.clip(vals,low,high)
    vals[0]=low
    vals[-1]=high
    # Rebalance interior values to keep the average close to the official average.
    target=mean*n
    for _ in range(30):
        delta=target-vals.sum()
        free=(vals>low+1e-6)&(vals<high-1e-6)
        if not free.any() or abs(delta)<0.01: break
        vals[free]+=delta/free.sum()
        vals=np.clip(vals,low,high)
    rows=[]
    for i,(f,v) in enumerate(zip(feats,vals)):
        rows.append({"SIDO_SGG":get_key(f),"시도":get_region(f),"주민등록인구_모형추정":float(v)})
    return pd.DataFrame(rows)

def map_figure(geo, table, value_col, title, colors="Blues", categorical=False):
    locs=table["SIDO_SGG"].astype(str).tolist()
    z=table[value_col].astype(float).tolist()
    if categorical:
        scale=[[0,"#3478c8"],[0.499,"#3478c8"],[0.5,"#a3a3a3"],[0.501,"#c94b4b"],[1,"#c94b4b"]]
        cbar=dict(title="인접 평균 대비",tickvals=[-1,0,1],ticktext=["낮음","같음","높음"])
        zmin,zmax=-1,1
    else:
        scale=colors;cbar=dict(title=title);zmin=zmax=None
    fig=go.Figure(go.Choropleth(
        geojson=geo,featureidkey="properties.SIDO_SGG",locations=locs,z=z,
        colorscale=scale,zmin=zmin,zmax=zmax,marker_line_color="#ffffff",marker_line_width=.55,
        colorbar=cbar,customdata=np.column_stack([table["시도"].astype(str).to_numpy(), (table["선거구"].astype(str).to_numpy() if "선거구" in table.columns else np.repeat("", len(table)))]),
        hovertemplate="%{customdata[0]}<br>%{location}<br>"+title+": %{z:,.3f}<extra></extra>"
    ))
    fig.update_geos(fitbounds="locations",visible=False,projection_type="mercator")
    fig.update_layout(height=650,margin=dict(l=0,r=0,t=10,b=0),paper_bgcolor="white",geo_bgcolor="white")
    return fig

# 1. Historical max / min / average
st.divider()
st.header("1. 역대 총선별 선거구 최대·최소·평균 인구 변화")
st.caption("전국 주민등록인구와 선거구 수로 평균을 산출했습니다. 최대·최소값은 선거구 인구 통계에 제시된 값입니다.")
metric=st.radio("표시할 인구 통계",["최대·평균·최소 모두","평균 인구 중심"],horizontal=True,key="hist_view")
h=history.sort_values("연도")
fig=go.Figure()
if metric=="최대·평균·최소 모두":
    for col,label in [("최대인구","최대 인구"),("평균인구","평균 인구"),("최소인구","최소 인구")]:
        fig.add_trace(go.Scatter(x=h["연도"],y=h[col],mode="lines+markers",name=label,
                                 customdata=h["총선"],hovertemplate="%{customdata}<br>%{x}년<br>%{y:,.0f}명<extra></extra>"))
else:
    fig.add_trace(go.Bar(x=h["총선"],y=h["평균인구"],name="평균 인구",text=h["평균인구"].round().map(fmt),textposition="outside"))
fig.update_layout(height=430,hovermode="x unified",legend_title_text="",margin=dict(l=10,r=10,t=20,b=10))
fig.update_xaxes(title="총선 연도")
fig.update_yaxes(title="선거구 인구(명)",tickformat=",")
st.plotly_chart(fig,use_container_width=True)
st.dataframe(h[["총선","인구기준월","선거구수","최대인구","평균인구","최소인구"]].rename(columns={"인구기준월":"주민등록인구 기준월"}),use_container_width=True,hide_index=True)

# 2. Map and top 10
st.divider()
st.header("2. 선거구별 인구수 및 표의 등가성 지수")
st.warning("선거구별 인구 원자료와 경계의 완전한 결합표는 확보되지 않았습니다. 아래 지도와 Top 10은 공식 전국 평균·최대·최소 범위를 반영해 생성한 **시각화용 모형 추정치**입니다. 실제 선거구별 순위나 인구로 인용하면 안 됩니다.")
try:
    geo=load_geo()
    district=estimated_population(geo)
    district["표의 등가성 지수"]=district["주민등록인구_모형추정"].mean()/district["주민등록인구_모형추정"]
    a,b,c=st.columns([1,1,1])
    with a: map_metric=st.selectbox("지도 색상 기준",["모형 추정 인구","표의 등가성 지수"],key="map_metric")
    with b: rank_metric=st.selectbox("Top 10 기준",["모형 추정 인구","표의 등가성 지수"],key="rank_metric")
    with c: region=st.selectbox("지역 필터",["전체"]+sorted(district["시도"].dropna().unique().tolist()),key="map_region")
    view=district.copy()
    if region!="전체": view=view[view["시도"]==region]
    value_col="주민등록인구_모형추정" if map_metric=="모형 추정 인구" else "표의 등가성 지수"
    left,right=st.columns([1.1,.9],gap="large")
    with left:
        st.markdown("**제22대 선거구 경계 지도**")
        st.plotly_chart(map_figure(geo,view,value_col,map_metric,"Blues" if map_metric=="모형 추정 인구" else "RdYlBu"),use_container_width=True)
    with right:
        st.markdown(f"**{rank_metric} Top 10 · 모형 추정**")
        rcol="주민등록인구_모형추정" if rank_metric=="모형 추정 인구" else "표의 등가성 지수"
        top=view.nlargest(10,rcol).sort_values(rcol)
        bar=px.bar(top,x=rcol,y="SIDO_SGG",orientation="h",color="시도",hover_data=["주민등록인구_모형추정","표의 등가성 지수"])
        bar.update_layout(height=560,margin=dict(l=5,r=5,t=10,b=5),legend_title_text="")
        st.plotly_chart(bar,use_container_width=True)
        st.metric("지도에 표시된 선거구",f"{len(view):,}개")
except Exception as e:
    st.error(f"선거구 경계 자료를 불러오지 못했습니다: {e}")
    st.info("인터넷 연결이 가능한 Streamlit 실행 환경에서 GeoJSON을 자동으로 불러옵니다.")

# 3. Adjacent districts
st.divider()
st.header("3. 인접 선거구와의 인구 차이")
st.caption("선거구 경계선을 실제로 공유하는 경우만 인접 선거구로 판단합니다. 꼭짓점만 닿는 경우는 제외합니다.")
try:
    from shapely.geometry import shape
    feats=[f for f in geo["features"] if get_key(f)]
    geoms={get_key(f):shape(f["geometry"]) for f in feats}
    pop=district.set_index("SIDO_SGG")["주민등록인구_모형추정"].to_dict()
    neighbors={k:[] for k in geoms}
    keys=list(geoms)
    for i,ka in enumerate(keys):
        for kb in keys[i+1:]:
            try:
                if geoms[ka].boundary.intersection(geoms[kb].boundary).length>1e-7:
                    neighbors[ka].append(kb);neighbors[kb].append(ka)
            except Exception:
                pass
    tol=st.slider("동일한 인구로 간주할 허용 오차(명)",0,1000,0,10,key="adj_tol")
    adjrows=[]
    for k,ns in neighbors.items():
        vals=[pop[n] for n in ns if n in pop]
        if not vals or k not in pop: continue
        avg=float(np.mean(vals)); diff=pop[k]-avg
        state=0 if abs(diff)<=tol else (1 if diff>0 else -1)
        adjrows.append({"SIDO_SGG":k,"시도":district.set_index("SIDO_SGG").loc[k,"시도"],"인접평균":avg,"차이":diff,"차이율(%)":diff/avg*100,"상태":state})
    adj=pd.DataFrame(adjrows)
    adj_region=st.selectbox("지역 필터",["전체"]+sorted(adj["시도"].dropna().unique().tolist()),key="adj_region")
    if adj_region!="전체": adj=adj[adj["시도"]==adj_region]
    st.plotly_chart(map_figure(geo,adj,"상태","인접 평균 대비",categorical=True),use_container_width=True)
    x,y,z=st.columns(3)
    x.metric("인접 평균보다 많음",f"{(adj['상태']==1).sum():,}개")
    y.metric("인접 평균보다 적음",f"{(adj['상태']==-1).sum():,}개")
    z.metric("허용 오차 이내",f"{(adj['상태']==0).sum():,}개")
    st.markdown("🔴 빨강: 인접 평균보다 인구가 많음　 🔵 파랑: 인접 평균보다 적음　 ⚪ 회색: 허용 오차 이내")
    st.caption("이 결과 역시 제2절의 시각화용 모형 추정 인구를 사용한 탐색 결과이며, 실제 선거구 인구 비교 결과가 아닙니다.")
except Exception as e:
    st.info(f"인접 선거구 지도는 경계 자료와 공간분석 라이브러리가 필요합니다. ({e})")

# 4. Distribution
st.divider()
st.header("4. 총선별 표의 등가성 지수 분포")
st.warning("개별 선거구 인구 원자료가 확보되지 않아, 공식 최대·최소·평균을 제약조건으로 생성한 모형 분포입니다. 분포의 모양과 선거구별 값은 실제 관측값이 아닙니다.")
election=st.selectbox("총선 시기 선택",history["총선"].tolist(),key="dist_election")
row=history[history["총선"]==election].iloc[0]
n=int(row["선거구수"]);mean=float(row["평균인구"]);low=float(row["최소인구"]);high=float(row["최대인구"])
seed=int(row["연도"])
rng=np.random.default_rng(seed)
vals=rng.lognormal(np.log(mean)-.5*.12**2,.12,n)
vals=np.clip(vals,low,high)
vals=vals*(mean/vals.mean())
vals=np.clip(vals,low,high)
vals[0]=low;vals[-1]=high
for _ in range(50):
    delta=mean*n-vals.sum()
    free=(vals>low+1e-6)&(vals<high-1e-6)
    if not free.any() or abs(delta)<.01:break
    vals[free]+=delta/free.sum();vals=np.clip(vals,low,high)
idx=mean/vals
dist=pd.DataFrame({"표의 등가성 지수":idx})
fig=px.histogram(dist,x="표의 등가성 지수",nbins=22,color_discrete_sequence=["#4776a8"])
fig.add_vline(x=1,line_dash="dash",line_color="#c94b4b",annotation_text="전국 평균 = 1")
fig.update_layout(height=450,margin=dict(l=10,r=10,t=25,b=10))
fig.update_xaxes(title="표의 등가성 지수")
fig.update_yaxes(title="모형상 선거구 수")
st.plotly_chart(fig,use_container_width=True)

# 5. Population vs registered voters
st.divider()
st.header("5. 주민등록인구와 유권자수(선거인수)의 관계 분석")
st.caption("전국 합계 기준 비교입니다. 주민등록인구와 선거인수는 기준일·집계 개념이 다르며, 선거인수는 투표자 수와 다릅니다.")
v=voters.copy()
v["선거인수 비율(%)"]=v["선거인수"]/v["전국주민등록인구"]*100
fig=px.scatter(v,x="전국주민등록인구",y="선거인수",text="총선",size="선거인수 비율(%)",color="연도",
               hover_data={"연도":True,"선거인수 비율(%)":":.2f","전국주민등록인구":":,","선거인수":":,"})
fig.update_traces(textposition="top center")
fig.update_layout(height=500,margin=dict(l=10,r=10,t=20,b=10),showlegend=False)
fig.update_xaxes(title="전국 주민등록인구(명)",tickformat=",")
fig.update_yaxes(title="전국 선거인수(명)",tickformat=",")
st.plotly_chart(fig,use_container_width=True)

st.divider()
st.subheader("자료 및 해석상 유의사항")
st.markdown("""
- **실제 통계:** 제20·21·22대 총선별 전국 인구, 선거구 수, 최대·최소 인구 및 전국 선거인수 요약
- **읍면동 자료:** KOSIS 「행정구역(읍면동)별/5세별 주민등록인구」에서 각 총선 인구 기준월의 읍면동별 총인구를 추출해 부록 데이터로 포함
- **모형 추정:** 선거구별 지도, Top 10, 인접 선거구 비교 및 분포는 선거구별 공식 인구 원자료와 경계의 완전한 결합표가 없어 시각화 시연용으로 생성
- 표의 등가성 지수는 주민등록인구 기준의 상대적 대표 규모를 나타내는 프로젝트 분석지표이며, 실제 개인의 투표권 행사나 법적 위헌 여부를 직접 측정하지 않습니다.
""")
st.markdown("""
**출처**
- KOSIS 국가통계포털, 행정구역(읍면동)별/5세별 주민등록인구: https://kosis.kr/statisticsList/mass/mass_list.jsp?org_id=101&tbl_id=DT_1B04005N
- 행정안전부 주민등록 인구통계: https://jumin.mois.go.kr/
- 중앙선거관리위원회 선거통계시스템: https://info.nec.go.kr/
- 제22대 국회의원선거구 GeoJSON: https://github.com/OhmyNews/2024_22_elec_map
""")
