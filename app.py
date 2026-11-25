from __future__ import annotations
from pathlib import Path
import json
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import folium
import branca.colormap as bcm
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
    # GeoJSON의 공식 선거구 고유코드로 결합해 한글 명칭/띄어쓰기 불일치를 방지
    for k in ("SGG_Code","SIDO_SGG","SIDO_SGG_NM","SGG","SIGUNGU"):
        if p.get(k) not in (None,""):
            return str(p[k]).strip()
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
        rows.append({"SGG_Code":get_key(f),"선거구":str(f.get("properties",{}).get("SIDO_SGG",get_key(f))),
                     "시도":get_region(f),"주민등록인구_모형추정":float(v)})
    return pd.DataFrame(rows)

def map_figure(geo, table, value_col, title, colors="Blues", categorical=False):
    """
    Folium/Leaflet polygon map.
    Values are attached directly to each GeoJSON feature before rendering,
    avoiding Plotly Choropleth's strict featureidkey join.
    """
    if table.empty:
        raise ValueError("지도에 표시할 선거구 데이터가 없습니다.")

    values = {
        str(row["SGG_Code"]).strip(): float(row[value_col])
        for _, row in table.iterrows()
        if pd.notna(row[value_col])
    }
    labels = {
        str(row["SGG_Code"]).strip(): str(row.get("선거구", row["SGG_Code"]))
        for _, row in table.iterrows()
    }
    regions = {
        str(row["SGG_Code"]).strip(): str(row.get("시도", ""))
        for _, row in table.iterrows()
    }

    features = []
    for original in geo.get("features", []):
        feature = json.loads(json.dumps(original))
        props = feature.setdefault("properties", {})
        code = str(props.get("SGG_Code", "")).strip()
        if code not in values:
            continue

        value = values[code]
        props["_map_code"] = code
        props["_map_name"] = labels.get(code, str(props.get("SIDO_SGG", code)))
        props["_map_region"] = regions.get(code, str(props.get("SIDO", "")))
        props["_map_value"] = value

        if categorical:
            if value > 0:
                fill = "#c94b4b"   # 인접 평균보다 인구가 많음
            elif value < 0:
                fill = "#3478c8"   # 인접 평균보다 인구가 적음
            else:
                fill = "#a3a3a3"   # 같음
        else:
            lo = min(values.values())
            hi = max(values.values())
            if hi == lo:
                t = 0.5
            else:
                t = (value - lo) / (hi - lo)
            # Fixed blue ramp, interpolated without relying on any map join.
            stops = ["#deebf7", "#9ecae1", "#4292c6", "#08519c"]
            pos = t * (len(stops) - 1)
            j = min(int(pos), len(stops) - 2)
            frac = pos - j
            def hex_rgb(h):
                h = h.lstrip("#")
                return np.array([int(h[k:k+2], 16) for k in (0, 2, 4)], dtype=float)
            c1 = hex_rgb(stops[j])
            c2 = hex_rgb(stops[j + 1])
            rgb = np.round(c1 * (1 - frac) + c2 * frac).astype(int)
            fill = "#{:02x}{:02x}{:02x}".format(*rgb)

        props["_map_fill"] = fill
        features.append(feature)

    if not features:
        raise ValueError(
            "선택한 선거구와 경계 데이터가 하나도 연결되지 않았습니다. "
            "선거구 코드(SGG_Code)를 확인해야 합니다."
        )

    geo_subset = {"type": "FeatureCollection", "features": features}
    m = folium.Map(
        location=[36.35, 127.85],
        zoom_start=7,
        tiles="CartoDB positron",
        control_scale=True,
        prefer_canvas=True,
    )

    tooltip = folium.GeoJsonTooltip(
        fields=["_map_region", "_map_name", "_map_value"],
        aliases=["시도", "선거구", title],
        localize=True,
        sticky=False,
        labels=True,
        style="background-color: white; color: #222; font-size: 13px; padding: 8px;",
    )

    layer = folium.GeoJson(
        data=geo_subset,
        name=title,
        style_function=lambda feature: {
            "fillColor": feature["properties"]["_map_fill"],
            "color": "#ffffff",
            "weight": 1.0,
            "fillOpacity": 0.82,
            "opacity": 1.0,
        },
        highlight_function=lambda feature: {
            "color": "#222222",
            "weight": 2.5,
            "fillOpacity": 0.95,
        },
        tooltip=tooltip,
        smooth_factor=0.5,
    )
    layer.add_to(m)

    bounds = layer.get_bounds()
    if bounds and len(bounds) == 2:
        m.fit_bounds(bounds, padding=(18, 18), max_zoom=9)

    if categorical:
        legend = bcm.StepColormap(
            colors=["#3478c8", "#a3a3a3", "#c94b4b"],
            index=[-1, -0.5, 0.5, 1],
            vmin=-1,
            vmax=1,
            caption="인접 평균 대비 인구 차이",
        )
    else:
        vals = list(values.values())
        vmin, vmax = min(vals), max(vals)
        if vmin == vmax:
            vmax = vmin + 1
        legend = bcm.LinearColormap(
            ["#deebf7", "#9ecae1", "#4292c6", "#08519c"],
            vmin=vmin,
            vmax=vmax,
            caption=title,
        )
    legend.add_to(m)
    folium.LayerControl(collapsed=True).add_to(m)
    return m

# 1. Historical max / min / average
st.divider()
st.header("1. 역대 총선별 선거구 최대·최소·평균 인구 변화")
st.caption("총선별 인구 기준월의 전국 주민등록인구와 선거구 수로 평균을 산출했습니다. 최대·최소값은 해당 총선의 선거구 인구 통계에 제시된 값입니다.")
metric=st.radio("표시할 인구 통계",["최대·평균·최소 모두","평균 인구 중심"],horizontal=True,key="hist_view")
h=history.sort_values("연도").copy()
h["총선표시"]=h["총선"]+" ("+h["연도"].astype(str)+")"
fig=go.Figure()
if metric=="최대·평균·최소 모두":
    for col,label in [("최대인구","최대 인구"),("평균인구","평균 인구"),("최소인구","최소 인구")]:
        fig.add_trace(go.Scatter(
            x=h["총선표시"],y=h[col],mode="lines+markers",name=label,
            customdata=np.column_stack([h["인구기준월"],h["연도"]]),
            hovertemplate="%{x}<br>인구 기준월: %{customdata[0]}<br>%{y:,.0f}명<extra></extra>"
        ))
else:
    fig.add_trace(go.Bar(
        x=h["총선표시"],y=h["평균인구"],name="평균 인구",
        text=h["평균인구"].round().map(fmt),textposition="outside"
    ))
fig.update_layout(height=430,hovermode="x unified",legend_title_text="",margin=dict(l=10,r=10,t=20,b=10))
fig.update_xaxes(title="총선 시기",type="category")
fig.update_yaxes(title="선거구 인구(명)",tickformat=",")
st.plotly_chart(fig,use_container_width=True)
st.caption("각 점은 실제 자료가 확인되는 세 차례 총선만 나타냅니다. 점 사이의 선은 관측되지 않은 연도별 변화를 의미하지 않습니다.")
st.dataframe(h[["총선","인구기준월","선거구수","최대인구","평균인구","최소인구"]].rename(columns={"인구기준월":"주민등록인구 기준월"}),use_container_width=True,hide_index=True)

# 2. Constituency map and official summary
st.divider()
st.header("2. 선거구별 인구수 및 표의 등가성 지수")
st.warning("선거구별 인구 원자료와 경계의 완전한 결합표는 확보되지 않았습니다. 지도는 공식 전국 평균·최대·최소 범위를 반영해 생성한 **시각화용 모형 추정치**입니다. 실제 선거구별 인구로 인용하면 안 됩니다. 오른쪽 그래프는 공식 전국 요약 통계입니다.")
try:
    geo=load_geo()
    district=estimated_population(geo)
    geo_codes={str(f.get("properties",{}).get("SGG_Code"," ")).strip() for f in geo["features"]}
    matched=len(set(district["SGG_Code"].astype(str)) & geo_codes)
    if matched < 200:
        raise ValueError(f"선거구 코드 결합이 충분하지 않습니다. 일치 {matched}개")
    district["표의 등가성 지수"]=district["주민등록인구_모형추정"].mean()/district["주민등록인구_모형추정"]
    a,b,c=st.columns([1,1,1])
    with a: map_metric=st.selectbox("지도 색상 기준",["모형 추정 인구","표의 등가성 지수"],key="map_metric")
    with b: st.markdown("**오른쪽 그래프: 공식 전국 요약 통계**")
    with c: region=st.selectbox("지역 필터",["전체"]+sorted(district["시도"].dropna().unique().tolist()),key="map_region")
    view=district.copy()
    if region!="전체": view=view[view["시도"]==region]
    value_col="주민등록인구_모형추정" if map_metric=="모형 추정 인구" else "표의 등가성 지수"
    left,right=st.columns([1.1,.9],gap="large")
    with left:
        st.markdown("**제22대 선거구 경계 지도**")
        folium_map = map_figure(geo,view,value_col,map_metric)
        st.components.v1.html(folium_map.get_root().render(),height=680,scrolling=False)
    with right:
        st.markdown("**제22대 공식 전국 요약 통계**")
        summary_row=history.loc[history["연도"]==2024].iloc[0]
        summary=pd.DataFrame({
            "통계":["최대 인구","전국 평균 인구","최소 인구"],
            "인구수":[summary_row["최대인구"],summary_row["평균인구"],summary_row["최소인구"]]
        })
        summary_fig=px.bar(
            summary.sort_values("인구수"),
            x="인구수",y="통계",orientation="h",
            text=summary.sort_values("인구수")["인구수"].round().map(fmt),
            color="통계",
            color_discrete_map={"최대 인구":"#2463a6","전국 평균 인구":"#79b9e8","최소 인구":"#d97970"}
        )
        summary_fig.update_traces(textposition="outside",cliponaxis=False)
        summary_fig.update_layout(height=430,margin=dict(l=5,r=35,t=15,b=10),showlegend=False,xaxis_title="인구(명)",yaxis_title="")
        summary_fig.update_xaxes(tickformat=",")
        st.plotly_chart(summary_fig,use_container_width=True)
        st.metric("지도에 표시된 선거구",f"{len(view):,}개")
        st.caption(f"공식 요약 통계의 인구 기준월: {summary_row['인구기준월']}. 지도는 모형 추정값이며 오른쪽 그래프는 공식 최대·평균·최소값입니다.")
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
    pop=district.set_index("SGG_Code")["주민등록인구_모형추정"].to_dict()
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
        adjrows.append({"SGG_Code":k,"시도":district.set_index("SGG_Code").loc[k,"시도"],"인접평균":avg,"차이":diff,"차이율(%)":diff/avg*100,"상태":state})
    adj=pd.DataFrame(adjrows)
    adj_region=st.selectbox("지역 필터",["전체"]+sorted(adj["시도"].dropna().unique().tolist()),key="adj_region")
    if adj_region!="전체": adj=adj[adj["시도"]==adj_region]
    folium_adj_map = map_figure(geo,adj,"상태","인접 평균 대비",categorical=True)
    st.components.v1.html(folium_adj_map.get_root().render(),height=680,scrolling=False)
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

# Proportion of constituencies above/below the equal-representation index (=1)
above=int((idx>1).sum())
below=int((idx<1).sum())
equal=int((np.isclose(idx,1,atol=1e-9)).sum())
ratio_table=pd.DataFrame({
    "구분":["지수 1 초과","지수 1 미만","지수 1"],
    "선거구 수":[above,below,equal],
})
ratio_table["비율(%)"]=ratio_table["선거구 수"]/len(idx)*100
st.markdown("**모형 추정 기준 표의 등가성 지수 1 초과·미만 선거구 비율**")
ratio_fig=px.bar(
    ratio_table[ratio_table["선거구 수"]>0],
    x="구분",y="비율(%)",text=ratio_table.loc[ratio_table["선거구 수"]>0,"비율(%)"].map(lambda v:f"{v:.1f}%"),
    color="구분",
    color_discrete_map={"지수 1 초과":"#2878b5","지수 1 미만":"#e07a5f","지수 1":"#9ca3af"}
)
ratio_fig.update_traces(textposition="outside",cliponaxis=False)
ratio_fig.update_layout(height=350,showlegend=False,margin=dict(l=10,r=10,t=15,b=10),yaxis_title="선거구 비율(%)",xaxis_title="")
ratio_fig.update_yaxes(range=[0,max(100,float(ratio_table["비율(%)"].max())*1.18)])
st.plotly_chart(ratio_fig,use_container_width=True)
st.caption(f"지수 1 초과 {above}개({above/len(idx)*100:.1f}%), 지수 1 미만 {below}개({below/len(idx)*100:.1f}%). 현재 선거구별 공식 인구 원자료가 완전하지 않아, 이 비율은 선택한 총선의 공식 평균·최대·최소를 반영한 모형 추정 분포에서 산출한 값입니다.")

# 5. Population vs registered voters (22nd election, constituency level)
st.divider()
st.header("5. 제22대 총선 선거구 인구수와 선거인수 비율의 관계")
st.caption("각 점은 하나의 국회의원 지역구입니다. x축은 선거구 인구수, y축은 선거구 인구수 대비 확정 선거인수 비율입니다.")
scatter_path=DATA/"election22_district_population_voters.csv"
if scatter_path.exists():
    s22=pd.read_csv(scatter_path)
    fig=px.scatter(
        s22, x="선거구인구수", y="선거인수비율(%)", hover_name="선거구명",
        hover_data={"선거구인구수":":,","확정선거인수":":,","선거인수비율(%)":":.2f"},
        color="sdName",
        labels={"선거구인구수":"선거구 인구수(명)","선거인수비율(%)":"선거인수 비율(%)","sdName":"시도"},
        opacity=.78
    )
    from scipy import stats
    x=s22["선거구인구수"].astype(float).to_numpy()
    y=s22["선거인수비율(%)"].astype(float).to_numpy()
    reg=stats.linregress(x,y)
    xline=np.linspace(x.min(),x.max(),100)
    fig.add_trace(go.Scatter(
        x=xline, y=reg.intercept+reg.slope*xline, mode="lines",
        name="선형 회귀선", line=dict(color="#222222",width=2,dash="dash"),
        hoverinfo="skip"
    ))
    fig.update_traces(marker=dict(size=9,line=dict(width=.5,color="white")),selector=dict(mode="markers"))
    fig.update_layout(height=540,margin=dict(l=10,r=10,t=20,b=10),legend_title_text="시도 / 추세선",hovermode="closest")
    fig.update_xaxes(title="선거구 인구수(명)",tickformat=",")
    fig.update_yaxes(title="선거구 인구수 대비 선거인수 비율(%)",ticksuffix="%")
    st.plotly_chart(fig,use_container_width=True)
    c1,c2,c3=st.columns(3)
    c1.metric("분석 선거구",f"{len(s22):,}개")
    c2.metric("상관계수 r",f"{reg.rvalue:.3f}")
    c3.metric("설명력 R²",f"{reg.rvalue**2:.3f}")
    slope_10k=reg.slope*10000
    direction="음(-)의 관계" if reg.slope<0 else "양(+)의 관계"
    st.markdown("**회귀분석 결과 해석**")
    st.info(
        f"현재 확보된 {len(s22)}개 선거구 자료의 단순선형회귀 결과, 인구수와 선거인수 비율은 {direction}를 보입니다. "
        f"선거구 인구가 1만 명 증가할 때 선거인수 비율은 평균적으로 약 {abs(slope_10k):.2f}%p "
        f"{'낮아지는' if reg.slope<0 else '높아지는'} 경향이 관찰됩니다(r={reg.rvalue:.3f}, R²={reg.rvalue**2:.3f}, p={reg.pvalue:.3g}). "
        "즉, 이 표본에서는 인구가 큰 선거구일수록 전체 인구 중 선거인명부에 포함된 사람의 비율이 낮은 경향이 있습니다. "
        "다만 이는 상관관계이며, 연령구조·외국인 인구·인구 기준일 차이 등 다른 요인을 통제하지 않은 결과이므로 인과관계로 해석해서는 안 됩니다."
    )
    st.caption("비율 = 확정 선거인수 ÷ 선거구 인구수 × 100. 선거인수는 투표에 참여한 사람이 아니라 선거인명부에 등재된 유권자 수입니다.")
    st.warning(
        f"전체 254개 선거구 중 자료가 확인된 {len(s22)}개만 분석했으며, 29개 선거구는 누락되어 있습니다. "
        "또한 선거구 인구 기준월과 선거인명부 작성 기준일은 동일한 개념이 아닐 수 있으므로, "
        "비율 차이를 연령구조만의 영향으로 단정할 수 없습니다."
    )
else:
    st.error("제22대 선거구별 인구·선거인수 자료 파일을 찾을 수 없습니다.")

st.divider()
st.subheader("자료 및 해석상 유의사항")
st.markdown("""
- **실제 통계:** 제20·21·22대 총선별 전국 인구, 선거구 수, 최대·최소 인구 및 전국 선거인수 요약
- **제22대 산점도:** 중앙선거관리위원회 API에서 확인된 225개 선거구의 선거구 인구(ppltCnt)와 확정 선거인수(cfmtnElcnt)를 사용
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
