from pathlib import Path
import io
import json
import math
import textwrap

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import folium
from streamlit_folium import st_folium
import geopandas as gpd
import requests
import streamlit as st

HERE = Path(__file__).parent
DATA = HERE / "data"

st.set_page_config(page_title="국회의원 지역구 인구와 표의 등가성 분석", layout="wide")

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 1.4rem;}
    h1 {margin-bottom: 0.2rem;}
    .section-title {font-size: 1.35rem; font-weight: 700; margin: 0.4rem 0 0.5rem 0;}
    .muted {color: #666; font-size: 0.95rem;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("국회의원 지역구 인구와 표의 등가성 분석")
st.caption("첫 화면에서 모든 분석이 한 번에 보이는 버전입니다.")

st.info(
    "선택칸은 없애고 1~5번 분석을 모두 한 화면에 배치했습니다. "
    "2·3번은 선거구별 인구 CSV와 GeoJSON 경계가 있으면 실제 색상 분석이 동작합니다."
)

GEOJSON_URL = "https://raw.githubusercontent.com/OhmyNews/2024_22_elec_map/main/2024_22_Elec_simplify.json"

@st.cache_data(show_spinner=False)
def load_history() -> pd.DataFrame:
    path = DATA / "election_history_summary.csv"
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame([
            [20, 2016, 51465228, 246, 278945, 139473, 209209.0],
            [21, 2020, 51826287, 253, 273129, 136565, 204847.0],
            [22, 2024, 51558034, 254, 271716, 135858, 203787.0],
        ], columns=["총선", "연도", "총인구", "지역구수", "최대인구", "최소인구", "평균인구"])
    return df.sort_values("연도").reset_index(drop=True)

@st.cache_data(show_spinner=False)
def load_voters() -> pd.DataFrame:
    path = DATA / "election_voter_summary.csv"
    if path.exists():
        df = pd.read_csv(path)
    else:
        df = pd.DataFrame([
            [20, 2016, 51465228, 42100398],
            [21, 2020, 51826287, 43994247],
            [22, 2024, 51558034, 44251919],
        ], columns=["총선", "연도", "주민등록인구", "선거인수"])
    return df.sort_values("연도").reset_index(drop=True)

def _norm(s: str) -> str:
    return "".join(ch for ch in str(s).lower().strip() if ch.isalnum() or ch in ["가", "나", "다", "라", "마", "바", "사", "아", "자", "차", "카", "타", "파", "하"])

def pick_col(df: pd.DataFrame, candidates) -> str | None:
    norm_map = {_norm(c): c for c in df.columns}
    for cand in candidates:
        key = _norm(cand)
        if key in norm_map:
            return norm_map[key]
    # partial match fallback
    for cand in candidates:
        key = _norm(cand)
        for n, orig in norm_map.items():
            if key in n or n in key:
                return orig
    return None

@st.cache_data(show_spinner=False)
def load_geojson() -> dict | None:
    try:
        r = requests.get(GEOJSON_URL, timeout=20)
        r.raise_for_status()
        data = r.json()
        if data.get("type") == "FeatureCollection":
            return data
    except Exception:
        return None
    return None

def geojson_to_gdf(geojson: dict) -> gpd.GeoDataFrame:
    features = geojson.get("features", [])
    if not features:
        return gpd.GeoDataFrame()
    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    # try to infer a readable label column
    label_cols = ["SIDO_SGG", "sgg_nm", "sgg_name", "name", "NAME", "title", "district", "구역명"]
    found = None
    for c in label_cols:
        if c in gdf.columns:
            found = c
            break
    if found is None:
        # pick first non-geometry object column
        for c in gdf.columns:
            if c != "geometry" and gdf[c].dtype == "object":
                found = c
                break
    if found is None:
        gdf["__label__"] = [f"구역 {i+1}" for i in range(len(gdf))]
    else:
        gdf["__label__"] = gdf[found].astype(str)
    gdf["__key__"] = gdf["__label__"].map(_norm)
    return gdf

def load_constituency_data(uploaded_file=None) -> pd.DataFrame | None:
    candidates = []
    if uploaded_file is not None:
        try:
            candidates.append(pd.read_csv(uploaded_file))
        except Exception:
            pass
    local = DATA / "constituency_population.csv"
    if local.exists():
        try:
            candidates.append(pd.read_csv(local))
        except Exception:
            pass
    template = DATA / "constituency_population_template.csv"
    if template.exists() and not candidates:
        try:
            candidates.append(pd.read_csv(template))
        except Exception:
            pass
    if not candidates:
        return None
    df = candidates[0].copy()
    # normalize columns for easier downstream use
    rename = {}
    for col in df.columns:
        n = _norm(col)
        if n in ["총선", "electionyear", "year", "회차"]:
            rename[col] = "총선"
        elif n in ["선거구명", "선거구", "district", "sgg", "sggname", "name"]:
            rename[col] = "선거구명"
        elif n in ["시도", "지역", "sido", "region", "광역시도"]:
            rename[col] = "시도"
        elif n in ["주민등록인구", "인구", "population", "pop"]:
            rename[col] = "주민등록인구"
        elif n in ["선거인수", "유권자수", "voters", "electors", "electorcount"]:
            rename[col] = "선거인수"
        elif n in ["표의등가성지수", "등가성지수", "eqindex", "equalvoteindex"]:
            rename[col] = "표의등가성지수"
        elif n in ["위도", "lat", "latitude"]:
            rename[col] = "위도"
        elif n in ["경도", "lon", "lng", "longitude"]:
            rename[col] = "경도"
    df = df.rename(columns=rename)
    return df

def compute_equal_vote_index(df: pd.DataFrame) -> pd.Series:
    if "주민등록인구" not in df.columns:
        return pd.Series(dtype=float)
    base = pd.to_numeric(df["주민등록인구"], errors="coerce").mean()
    return base / pd.to_numeric(df["주민등록인구"], errors="coerce")

def compute_neighbors(gdf: gpd.GeoDataFrame) -> dict[int, set[int]]:
    neighbors = {i: set() for i in gdf.index}
    if gdf.empty:
        return neighbors
    sindex = gdf.sindex
    for i, geom in gdf.geometry.items():
        try:
            candidates = list(sindex.intersection(geom.bounds))
        except Exception:
            candidates = list(gdf.index)
        for j in candidates:
            if j <= i:
                continue
            try:
                g2 = gdf.at[j, "geometry"]
                if geom.touches(g2):
                    inter = geom.intersection(g2)
                    if not inter.is_empty and inter.length > 0:
                        neighbors[i].add(j)
                        neighbors[j].add(i)
            except Exception:
                continue
    return neighbors

def fallback_map(title: str, message: str, height: int = 600):
    m = folium.Map(location=[36.2, 127.8], zoom_start=6, tiles="CartoDB positron", control_scale=False)
    st.caption(message)
    st_folium(m, height=height, use_container_width=True)

def section_header(num: str, title: str):
    st.markdown(f'<div class="section-title">{num}. {title}</div>', unsafe_allow_html=True)

history = load_history()
voters = load_voters()
geojson = load_geojson()
gdf = geojson_to_gdf(geojson) if geojson else None

# ---------- 1 ----------
with st.container(border=True):
    section_header("1", "역대 총선별 선거구 최대·최소·평균 인구 변화")
    st.caption("차트만 표시됩니다.")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=history["연도"], y=history["최대인구"], mode="lines+markers", name="최대",
        hovertemplate="%{x}년<br>%{y:,.0f}명<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=history["연도"], y=history["평균인구"], mode="lines+markers", name="평균",
        hovertemplate="%{x}년<br>%{y:,.0f}명<extra></extra>"
    ))
    fig.add_trace(go.Scatter(
        x=history["연도"], y=history["최소인구"], mode="lines+markers", name="최소",
        hovertemplate="%{x}년<br>%{y:,.0f}명<extra></extra>"
    ))
    fig.update_layout(height=360, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="")
    fig.update_yaxes(title="인구(명)", tickformat=",")
    fig.update_xaxes(title="총선 연도")
    st.plotly_chart(fig, use_container_width=True)

# ---------- 2 ----------
with st.container(border=True):
    section_header("2", "선거구별 인구수 및 표의 등가성 지수")
    st.caption("지도 + 차트")
    uploaded_const = st.file_uploader("선거구 인구 CSV 업로드", type=["csv"], key="u_const")
    const_df = load_constituency_data(uploaded_const)
    left, right = st.columns([1.05, 0.95], gap="large")

    with left:
        st.markdown("**지도**")
        if const_df is None or const_df.empty:
            fallback_map(
                "선거구별 인구 지도",
                "현재는 선거구별 인구 CSV가 없어 색칠 지도를 표시할 수 없습니다. "
                "data/constituency_population.csv 또는 업로드 파일이 있으면 실제 색상이 들어갑니다.",
                height=540,
            )
        else:
            if geojson is None or gdf is None or gdf.empty:
                st.warning("GeoJSON을 불러오지 못했습니다. 지도 색상은 계산할 수 있지만 폴리곤 경계가 필요합니다.")
            else:
                pop_col = pick_col(const_df, ["주민등록인구", "population"])
                name_col = pick_col(const_df, ["선거구명", "선거구", "district", "name"])
                idx_col = pick_col(const_df, ["표의등가성지수", "등가성지수", "eqindex"])
                if idx_col is None and pop_col is not None:
                    const_df["표의등가성지수"] = compute_equal_vote_index(const_df)
                    idx_col = "표의등가성지수"
                if name_col is None or pop_col is None:
                    st.error("선거구명/주민등록인구 열이 필요합니다.")
                else:
                    merged = const_df.copy()
                    merged["__key__"] = merged[name_col].astype(str).map(_norm)
                    gdf2 = gdf.copy()
                    gdf2 = gdf2.merge(merged, left_on="__key__", right_on="__key__", how="left")

                    vcol = pop_col
                    values = pd.to_numeric(gdf2[vcol], errors="coerce")
                    if values.notna().sum() == 0:
                        vcol = idx_col if idx_col else pop_col
                        values = pd.to_numeric(gdf2[vcol], errors="coerce")
                    m = folium.Map(location=[36.2, 127.8], zoom_start=6, tiles="CartoDB positron", control_scale=False)
                    folium.Choropleth(
                        geo_data=json.loads(gdf2.to_json()),
                        data=gdf2,
                        columns=["__key__", vcol],
                        key_on="feature.properties.__key__",
                        fill_color="Blues",
                        fill_opacity=0.75,
                        line_opacity=0.7,
                        nan_fill_color="#efefef",
                        highlight=True,
                        legend_name="주민등록인구" if vcol == pop_col else "표의 등가성 지수",
                    ).add_to(m)
                    folium.GeoJson(
                        json.loads(gdf2.to_json()),
                        style_function=lambda x: {"fillOpacity": 0, "color": "#557799", "weight": 0.7},
                        tooltip=folium.GeoJsonTooltip(fields=["__label__"], aliases=["선거구:"]),
                    ).add_to(m)
                    st_folium(m, height=540, use_container_width=True)

    with right:
        st.markdown("**차트**")
        if const_df is None or const_df.empty:
            st.info("선거구별 인구 CSV가 필요합니다. 위 업로드 또는 data/constituency_population.csv를 넣어 주세요.")
        else:
            pop_col = pick_col(const_df, ["주민등록인구", "population"])
            name_col = pick_col(const_df, ["선거구명", "선거구", "district", "name"])
            idx_col = pick_col(const_df, ["표의등가성지수", "등가성지수", "eqindex"])
            if pop_col is None or name_col is None:
                st.error("선거구명/주민등록인구 열이 필요합니다.")
            else:
                if idx_col is None:
                    const_df["표의등가성지수"] = compute_equal_vote_index(const_df)
                    idx_col = "표의등가성지수"
                top_n = st.slider("Top N", 5, 20, 10, key="topn2")
                dff = const_df.copy()
                dff[pop_col] = pd.to_numeric(dff[pop_col], errors="coerce")
                dff[idx_col] = pd.to_numeric(dff[idx_col], errors="coerce")
                dff = dff.dropna(subset=[pop_col, idx_col, name_col])
                top_pop = dff.nlargest(top_n, pop_col)[[name_col, pop_col]].sort_values(pop_col)
                top_idx = dff.nlargest(top_n, idx_col)[[name_col, idx_col]].sort_values(idx_col)

                fig2 = make_subplots(rows=1, cols=2, subplot_titles=(f"인구수 Top {top_n}", f"등가성 지수 Top {top_n}"))
                fig2.add_trace(go.Bar(x=top_pop[pop_col], y=top_pop[name_col], orientation="h", name="인구수"), row=1, col=1)
                fig2.add_trace(go.Bar(x=top_idx[idx_col], y=top_idx[name_col], orientation="h", name="등가성 지수"), row=1, col=2)
                fig2.update_layout(height=540, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
                st.plotly_chart(fig2, use_container_width=True)

# ---------- 3 ----------
with st.container(border=True):
    section_header("3", "인접 선거구와의 인구 차이")
    st.caption("지도만 표시됩니다.")
    uploaded_const3 = st.file_uploader("인접 비교용 선거구 인구 CSV 업로드", type=["csv"], key="u_const3")
    const_df3 = load_constituency_data(uploaded_const3)
    if const_df3 is None or const_df3.empty or geojson is None or gdf is None or gdf.empty:
        fallback_map(
            "인접 선거구 인구 차이 지도",
            "선거구별 인구 CSV와 GeoJSON이 모두 있어야 인접 평균 대비 빨강/파랑/회색 색칠이 가능합니다.",
            height=620,
        )
    else:
        pop_col = pick_col(const_df3, ["주민등록인구", "population"])
        name_col = pick_col(const_df3, ["선거구명", "선거구", "district", "name"])
        if pop_col is None or name_col is None:
            st.error("선거구명/주민등록인구 열이 필요합니다.")
        else:
            d = const_df3.copy()
            d[name_col] = d[name_col].astype(str)
            d["__key__"] = d[name_col].map(_norm)
            d[pop_col] = pd.to_numeric(d[pop_col], errors="coerce")
            gdf3 = gdf.copy().merge(d, on="__key__", how="left")
            neighbors = compute_neighbors(gdf3)
            mean_neighbor = {}
            for i in gdf3.index:
                nbrs = list(neighbors.get(i, []))
                vals = gdf3.loc[nbrs, pop_col].dropna().astype(float) if nbrs else pd.Series(dtype=float)
                mean_neighbor[i] = float(vals.mean()) if len(vals) else np.nan

            def color_row(i):
                p = gdf3.at[i, pop_col]
                n = mean_neighbor.get(i)
                if pd.isna(p) or pd.isna(n):
                    return "#d9d9d9"
                if abs(p - n) < 1e-9:
                    return "#8c8c8c"
                return "#d73027" if p > n else "#4575b4"

            m3 = folium.Map(location=[36.2, 127.8], zoom_start=6, tiles="CartoDB positron", control_scale=False)
            for i, row in gdf3.iterrows():
                col = color_row(i)
                pop = row.get(pop_col, np.nan)
                nbr = mean_neighbor.get(i, np.nan)
                tooltip = f"{row['__label__']}" if row['__label__'] else ""
                popup = folium.Popup(
                    f"<b>{row['__label__']}</b><br>인구: {'' if pd.isna(pop) else f'{int(pop):,}'}<br>"
                    f"인접 평균: {'' if pd.isna(nbr) else f'{int(nbr):,}'}",
                    max_width=250,
                )
                folium.GeoJson(
                    row["geometry"],
                    style_function=lambda feat, c=col: {"fillColor": c, "color": c, "weight": 0.8, "fillOpacity": 0.65},
                    tooltip=tooltip,
                    popup=popup,
                ).add_to(m3)
            st_folium(m3, height=620, use_container_width=True)

# ---------- 4 ----------
with st.container(border=True):
    section_header("4", "총선별 표의 등가성 지수 분포")
    st.caption("차트만 표시됩니다.")
    # Prefer constituency-level file if available, otherwise fallback to election summary band.
    const_path = DATA / "constituency_population.csv"
    if const_path.exists():
        const_hist = pd.read_csv(const_path)
    else:
        const_hist = None

    if const_hist is not None and not const_hist.empty and "총선" in const_hist.columns and "주민등록인구" in const_hist.columns:
        const_hist["총선"] = pd.to_numeric(const_hist["총선"], errors="coerce")
        const_hist["주민등록인구"] = pd.to_numeric(const_hist["주민등록인구"], errors="coerce")
        const_hist["표의등가성지수"] = const_hist.groupby("총선")["주민등록인구"].transform(lambda s: s.mean() / s)
        fig4 = go.Figure()
        for election, grp in const_hist.dropna(subset=["총선","표의등가성지수"]).groupby("총선"):
            fig4.add_trace(go.Box(y=grp["표의등가성지수"], name=f"{int(election)}대", boxmean=True))
        fig4.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="표의 등가성 지수")
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.caption("현재는 총선별 요약값으로 분포 범위를 표시합니다. 선거구별 CSV가 있으면 실제 분포(Box Plot)로 바뀝니다.")
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(
            x=history["연도"], y=history["최대인구"], mode="lines", line=dict(color="#1f77b4"),
            name="최대"
        ))
        fig4.add_trace(go.Scatter(
            x=history["연도"], y=history["최소인구"], mode="lines", line=dict(color="#9ecae1"),
            name="최소", fill="tonexty", fillcolor="rgba(158,202,225,0.25)"
        ))
        fig4.add_trace(go.Scatter(
            x=history["연도"], y=history["평균인구"], mode="lines+markers", line=dict(color="#d62728"),
            name="평균"
        ))
        fig4.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10), yaxis_title="인구(명)", xaxis_title="총선 연도")
        fig4.update_yaxes(tickformat=",")
        st.plotly_chart(fig4, use_container_width=True)

# ---------- 5 ----------
with st.container(border=True):
    section_header("5", "주민등록인구와 유권자수(선거인수)의 관계 분석")
    st.caption("차트만 표시됩니다.")
    vv = voters.copy()
    vv["선거인수비율"] = vv["선거인수"] / vv["주민등록인구"] * 100
    fig5 = go.Figure()
    fig5.add_trace(go.Scatter(
        x=vv["주민등록인구"], y=vv["선거인수"], mode="markers+lines+text",
        text=vv["총선"].astype(str) + "대", textposition="top center",
        name="관측값"
    ))
    if len(vv) >= 2:
        m, b = np.polyfit(vv["주민등록인구"], vv["선거인수"], 1)
        xline = np.linspace(vv["주민등록인구"].min(), vv["주민등록인구"].max(), 100)
        fig5.add_trace(go.Scatter(
            x=xline, y=m * xline + b, mode="lines", name="추세선", line=dict(dash="dash")
        ))
    fig5.update_layout(height=420, margin=dict(l=10, r=10, t=40, b=10), xaxis_title="주민등록인구", yaxis_title="선거인수")
    fig5.update_xaxes(tickformat=",")
    fig5.update_yaxes(tickformat=",")
    st.plotly_chart(fig5, use_container_width=True)
    st.caption("아래 표는 발표용 해석을 돕는 요약값입니다.")
    st.dataframe(vv[["총선","연도","주민등록인구","선거인수","선거인수비율"]], use_container_width=True, hide_index=True)
