from __future__ import annotations
from pathlib import Path
import io, json, re
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st

BASE = Path(__file__).parent
DATA = BASE / 'data'
GEOJSON_URL = 'https://raw.githubusercontent.com/OhmyNews/2024_22_elec_map/main/2024_22_Elec_simplify.json'

st.set_page_config(page_title='국회의원 지역구 인구와 표의 등가성 분석', page_icon='🗳️', layout='wide')
st.markdown('''
<style>
.block-container{max-width:1800px;padding-top:1.3rem;padding-bottom:2.4rem}
h1{font-weight:800!important;letter-spacing:-.04em}
h2{font-weight:750!important;letter-spacing:-.025em}
h3{font-weight:700!important}
[data-testid="stMetric"]{background:#f5f8fc;border:1px solid #e7edf4;padding:13px 16px;border-radius:12px}
[data-testid="stVerticalBlockBorderWrapper"]{border-radius:13px}
[data-testid="stAlert"]{border-radius:11px}
div[data-testid="stSelectbox"] label{font-weight:650}
</style>
''', unsafe_allow_html=True)

OPTIONS = [
    '1. 역대 총선별 선거구 최대·최소·평균 인구 변화',
    '2. 선거구별 인구수 및 표의 등가성 지수',
    '3. 인접 선거구와의 인구 차이',
    '4. 총선별 표의 등가성 지수 분포',
    '5. 총선 시기별 표의 등가성 변화 분석',
    '6. 주민등록인구와 유권자수(선거인수)의 관계 분석',
]

# ---------- data utilities ----------
def read_csv_safe(source):
    if isinstance(source, bytes):
        raw = source
    else:
        raw = Path(source).read_bytes()
    for enc in ('utf-8-sig','cp949','utf-8'):
        try:
            return pd.read_csv(io.BytesIO(raw), encoding=enc)
        except Exception:
            continue
    raise ValueError('CSV 인코딩을 읽을 수 없습니다. UTF-8 또는 CP949로 저장해 주세요.')

def normalize_columns(df):
    if df is None or df.empty:
        return pd.DataFrame() if df is None else df.copy()
    x=df.copy()
    x.columns=[str(c).replace('\ufeff','').strip() for c in x.columns]
    aliases={
        '시도명':'시도','지역구':'선거구','선거구명':'선거구','선거구명칭':'선거구',
        '주민등록인구수':'주민등록인구','인구수':'주민등록인구','인구':'주민등록인구',
        '선거인 수':'선거인수','유권자수':'선거인수','선거인수(명)':'선거인수',
        '총선명':'총선','회차':'총선','선거연도':'연도','평균':'평균인구',
        '최대':'최대인구','최소':'최소인구','선거구 수':'선거구수',
        'SIDO_SGG명':'SIDO_SGG','선거구키':'SIDO_SGG'
    }
    ren={k:v for k,v in aliases.items() if k in x.columns and v not in x.columns}
    x=x.rename(columns=ren)
    for c in ['연도','최대인구','최소인구','평균인구','선거구수','주민등록인구','선거인수','투표자수','위도','경도']:
        if c in x.columns:
            x[c]=pd.to_numeric(x[c].astype(str).str.replace(',','',regex=False).str.replace('명','',regex=False).str.strip(),errors='coerce')
    return x

def get_csv(filename, uploaded_key=None):
    uploads=st.session_state.get('uploads',{})
    key=uploaded_key or filename
    if key in uploads:
        return normalize_columns(read_csv_safe(uploads[key]))
    p=DATA/filename
    if p.exists():
        try: return normalize_columns(read_csv_safe(p))
        except Exception: return pd.DataFrame()
    return pd.DataFrame()

def has(df, cols):
    return isinstance(df,pd.DataFrame) and not df.empty and all(c in df.columns for c in cols)

def notice(text):
    st.info(text, icon='ℹ️')

def won(v):
    try: return f'{float(v):,.0f}'
    except Exception: return '자료 없음'

def norm_key(s):
    return re.sub(r'\s+','',str(s)).replace('특별자치시','').replace('특별자치도','')

@st.cache_data(show_spinner='제22대 선거구 경계 불러오는 중…', ttl=86400)
def load_remote_geojson():
    r=requests.get(GEOJSON_URL,timeout=25,headers={'User-Agent':'ElectionDashboard/1.0'})
    r.raise_for_status()
    obj=r.json()
    if not obj.get('features'):
        raise ValueError('GeoJSON에 선거구 경계가 없습니다.')
    return obj

def load_geojson():
    local=DATA/'constituencies_22.geojson'
    if local.exists():
        return json.loads(local.read_text(encoding='utf-8'))
    raw=st.session_state.get('uploads',{}).get('constituencies_22.geojson')
    if raw:
        return json.loads(raw.decode('utf-8'))
    return load_remote_geojson()

@st.cache_data(show_spinner=False)
def make_adjacency(geojson_text):
    # Shapely is used only for spatial adjacency; shared-boundary neighbors are preferred to point-only touches.
    from shapely.geometry import shape
    gj=json.loads(geojson_text)
    feats=gj.get('features',[])
    items=[]
    for f in feats:
        p=f.get('properties',{})
        key=p.get('SIDO_SGG') or p.get('SIDO_SGG_NM') or p.get('SGG')
        if key:
            items.append((str(key),shape(f['geometry'])))
    neighbors={k:[] for k,_ in items}
    for i,(ka,ga) in enumerate(items):
        for kb,gb in items[i+1:]:
            try:
                if ga.boundary.intersection(gb.boundary).length > 1e-7:
                    neighbors[ka].append(kb); neighbors[kb].append(ka)
            except Exception:
                continue
    return neighbors

def choropleth(geo, table, value_col, title, color_scale='Blues', categorical=False, selected_region='전체'):
    feats=geo.get('features',[])
    keyset=[]; region_by_key={}
    for f in feats:
        p=f.get('properties',{})
        k=p.get('SIDO_SGG') or p.get('SIDO_SGG_NM') or p.get('SGG')
        if k:
            keyset.append(str(k)); region_by_key[str(k)]=str(p.get('SIDO',''))
    if selected_region!='전체':
        keyset=[k for k in keyset if region_by_key.get(k)==selected_region]
    if categorical:
        # -1 = lower than neighbors (blue), 0 = equal (gray), +1 = higher (red)
        cmap=[[0,'#3478c8'],[0.499,'#3478c8'],[0.5,'#a3a3a3'],[0.501,'#c94b4b'],[1,'#c94b4b']]
        vals=table.set_index('SIDO_SGG')[value_col].to_dict() if has(table,['SIDO_SGG',value_col]) else {}
        z=[vals.get(k,np.nan) for k in keyset]
        colorscale=cmap; zmin=-1; zmax=1; cbar=dict(title='인접 평균 대비',tickvals=[-1,0,1],ticktext=['낮음','같음','높음'])
    else:
        vals=table.set_index('SIDO_SGG')[value_col].to_dict() if has(table,['SIDO_SGG',value_col]) else {}
        z=[vals.get(k,np.nan) for k in keyset]
        colorscale=color_scale; zmin=None; zmax=None; cbar=dict(title=title)
    fig=go.Figure(go.Choropleth(
        geojson=geo, featureidkey='properties.SIDO_SGG', locations=keyset, z=z,
        colorscale=colorscale, zmin=zmin, zmax=zmax, marker_line_color='#8295a8', marker_line_width=.45,
        colorbar=cbar, hovertemplate='%{location}<br>'+title+': %{z:,.0f}<extra></extra>'
    ))
    fig.update_geos(fitbounds='locations',visible=False,projection_type='mercator',center=dict(lat=36.2,lon=127.8))
    fig.update_layout(height=690,margin=dict(l=0,r=0,t=8,b=0),paper_bgcolor='white',geo_bgcolor='white')
    return fig

# ---------- title and first screen ----------
st.title('국회의원 지역구 인구와 표의 등가성 분석')
st.caption('산업데이터시각화 프로젝트 · 인구 대표성의 지역 간 차이를 데이터로 탐색')

with st.container(border=True):
    st.subheader('분석 옵션 선택')
    selected=st.selectbox('분석할 항목을 선택하세요',OPTIONS,index=0,label_visibility='collapsed')

# load all available files after option selection
history=get_csv('election_history_summary.csv')
const=get_csv('constituency_population.csv')
historical=get_csv('historical_constituencies.csv')
voters_nat=get_csv('election_voters_national.csv')
voters_dist=get_csv('election_voters_district.csv')

# Optional in-session data loading; first page remains uncluttered.
with st.expander('데이터 파일 추가·교체 (CSV / GeoJSON)',expanded=False):
    st.write('공식 원자료를 올리면 해당 분석에 즉시 반영됩니다. 영구 반영하려면 같은 파일을 GitHub 저장소의 `data/` 폴더에도 업로드하세요.')
    files=st.file_uploader('자료 여러 개 선택',type=['csv','json','geojson'],accept_multiple_files=True,key='all_data_upload')
    if files:
        st.session_state.setdefault('uploads',{})
        for f in files:
            st.session_state.uploads[f.name]=f.getvalue()
        st.success('업로드 자료를 현재 세션에서 사용할 수 있습니다. 파일명은 아래 안내와 일치해야 합니다.')
    st.markdown('**지원 파일명**')
    st.code('''constituency_population.csv
historical_constituencies.csv
election_history_summary.csv
election_voters_national.csv
election_voters_district.csv
constituencies_22.geojson''',language='text')

# reload uploaded files after upload widget
history=get_csv('election_history_summary.csv')
const=get_csv('constituency_population.csv')
historical=get_csv('historical_constituencies.csv')
voters_nat=get_csv('election_voters_national.csv')
voters_dist=get_csv('election_voters_district.csv')

# ---------- 1. historical maximum/minimum/average ----------
if selected.startswith('1.'):
    st.header('역대 총선별 선거구 최대·최소·평균 인구 변화')
    if has(history,['연도','총선','최대인구','최소인구','평균인구']):
        t=history.dropna(subset=['연도','최대인구','최소인구','평균인구']).sort_values('연도')
        fig=go.Figure()
        for col,label in [('최대인구','최대 인구'),('평균인구','평균 인구'),('최소인구','최소 인구')]:
            fig.add_trace(go.Scatter(x=t['연도'].astype(int),y=t[col],mode='lines+markers',name=label,
                customdata=t['총선'],hovertemplate='%{customdata}<br>%{x}년<br>%{y:,.0f}명<extra></extra>'))
        fig.update_layout(height=540,hovermode='x unified',legend_title_text='',margin=dict(l=10,r=15,t=25,b=10))
        fig.update_xaxes(title='총선 연도',dtick=4,tickformat='d')
        fig.update_yaxes(title='선거구 인구(명)',tickformat=',')
        st.plotly_chart(fig,use_container_width=True)
        st.dataframe(t[['총선','연도','선거구수','최대인구','평균인구','최소인구','인구기준일']].sort_values('연도',ascending=False),use_container_width=True,hide_index=True)
        st.caption('인구기준일은 각 총선의 선거구 획정에 사용된 기준일입니다. 총선마다 법적 기준과 기준일이 달라질 수 있으므로 수치의 직접 비교에는 기준 차이를 함께 고려해야 합니다.')
    else:
        notice('election_history_summary.csv에 총선, 연도, 최대인구, 최소인구, 평균인구 열이 필요합니다.')

# ---------- 2. constituency choropleth + top 10 ----------
elif selected.startswith('2.'):
    st.header('선거구별 인구수 및 표의 등가성 지수')
    a,b,c=st.columns([1,1,1])
    with a: metric=st.selectbox('지도 표시 기준',['주민등록인구','표의 등가성 지수'],key='map_metric')
    with b: rank_metric=st.selectbox('Top 10 기준',['주민등록인구','표의 등가성 지수'],key='rank_metric')
    with c: region='전체'
    if has(const,['SIDO_SGG','시도','선거구','주민등록인구']):
        data=const.copy().dropna(subset=['주민등록인구'])
        data['주민등록인구']=pd.to_numeric(data['주민등록인구'],errors='coerce')
        data=data.dropna(subset=['주민등록인구'])
        data['표의 등가성 지수']=data['주민등록인구'].mean()/data['주민등록인구'].replace(0,np.nan)
        regions=['전체']+sorted(data['시도'].dropna().astype(str).unique().tolist())
        region=st.selectbox('지역 필터',regions,key='map_region')
        if region!='전체': data=data[data['시도'].astype(str)==region]
        map_value='주민등록인구' if metric=='주민등록인구' else '표의 등가성 지수'
        try:
            geo=load_geojson()
            left,right=st.columns([1.05,.95],gap='large')
            with left:
                st.markdown('**제22대 국회의원 지역구 경계 지도**')
                st.plotly_chart(choropleth(geo,data,map_value,map_value,'Blues' if metric=='주민등록인구' else 'RdYlBu'),use_container_width=True,config={'displayModeBar':True})
                st.caption('경계: OhmyNews 2024_22_elec_map (MIT). 데이터 연결이 안 된 선거구는 회색/결측으로 표시됩니다.')
            with right:
                st.markdown(f'**{rank_metric} Top 10**')
                if rank_metric=='표의 등가성 지수': data['표의 등가성 지수']=data['주민등록인구'].mean()/data['주민등록인구'].replace(0,np.nan)
                top=data.nlargest(10,rank_metric)
                if not top.empty:
                    fig=px.bar(top.sort_values(rank_metric),x=rank_metric,y='선거구',orientation='h',color='시도',hover_data=['주민등록인구','표의 등가성 지수'])
                    fig.update_layout(height=560,legend_title_text='',margin=dict(l=5,r=5,t=15,b=5))
                    fig.update_xaxes(title='명' if rank_metric=='주민등록인구' else '지수')
                    st.plotly_chart(fig,use_container_width=True)
                    st.metric('분석에 포함된 선거구',f'{len(data):,}개')
                else: notice('표시할 인구 자료가 없습니다.')
        except Exception as e:
            notice(f'선거구 경계 GeoJSON을 불러오지 못했습니다: {e}. 인터넷 연결을 확인하거나 `constituencies_22.geojson`을 업로드해 주세요.')
    else:
        notice('선거구별 실제 인구 자료가 아직 연결되지 않았습니다. data/constituency_population.csv에 254개 선거구의 공식 주민등록인구를 넣으면 지도 색상과 Top 10이 함께 작동합니다.')
        try:
            geo=load_geojson()
            keys=[f.get('properties',{}).get('SIDO_SGG') for f in geo.get('features',[]) if f.get('properties',{}).get('SIDO_SGG')]
            empty=pd.DataFrame({'SIDO_SGG':keys,'주민등록인구':np.nan})
            st.plotly_chart(choropleth(geo,empty,'주민등록인구','주민등록인구'),use_container_width=True)
        except Exception:
            st.caption('지도 경계 파일은 앱 실행 시 GitHub 공개 저장소에서 자동으로 불러옵니다.')

# ---------- 3. adjacency comparison map only ----------
elif selected.startswith('3.'):
    st.header('인접 선거구와의 인구 차이')
    st.caption('각 선거구의 주민등록인구를 인접 선거구들의 평균과 비교합니다.')
    if has(const,['SIDO_SGG','시도','선거구','주민등록인구']):
        try:
            geo=load_geojson()
            neighbors=make_adjacency(json.dumps(geo,ensure_ascii=False))
            data=const.copy().dropna(subset=['주민등록인구'])
            data['주민등록인구']=pd.to_numeric(data['주민등록인구'],errors='coerce')
            pop=data.set_index('SIDO_SGG')['주민등록인구'].to_dict()
            rows=[]
            tol=st.number_input('같음으로 처리할 허용 오차(명)',min_value=0,max_value=1000,value=0,step=10)
            for key,ns in neighbors.items():
                if key not in pop: continue
                vals=[pop[n] for n in ns if n in pop and pd.notna(pop[n])]
                if not vals: continue
                avg=float(np.mean(vals)); diff=float(pop[key])-avg
                state=0 if abs(diff)<=tol else (1 if diff>0 else -1)
                rows.append({'SIDO_SGG':key,'인접선거구평균':avg,'인접평균대비차이':diff,'상태':state,'인접선거구수':len(vals)})
            result=pd.DataFrame(rows)
            regions=['전체']+sorted(data['시도'].dropna().astype(str).unique().tolist())
            region=st.selectbox('지역 필터',regions,key='adj_region')
            if region!='전체':
                valid=set(data.loc[data['시도'].astype(str)==region,'SIDO_SGG'].astype(str))
                result=result[result['SIDO_SGG'].isin(valid)]
            if not result.empty:
                fig=choropleth(geo,result,'상태','인접 평균 대비',categorical=True,selected_region=region)
                st.plotly_chart(fig,use_container_width=True)
                x,y,z=st.columns(3)
                x.metric('인접 평균보다 인구가 많음',f'{int((result.상태==1).sum()):,}개')
                y.metric('인접 평균보다 인구가 적음',f'{int((result.상태==-1).sum()):,}개')
                z.metric('인접 평균과 같음',f'{int((result.상태==0).sum()):,}개')
                st.markdown('🔴 빨간색: 인접 평균보다 많음　 🔵 파란색: 인접 평균보다 적음　 ⚪ 회색: 허용 오차 이내')
                st.caption('인접성은 선거구 경계의 공유 경계 길이가 있는 경우로 계산했습니다. 꼭짓점만 접하는 선거구는 이웃으로 보지 않습니다.')
            else:
                notice('인접 선거구의 인구 자료를 연결할 수 없습니다. SIDO_SGG 값이 GeoJSON의 선거구 키와 정확히 일치하는지 확인해 주세요.')
        except Exception as e:
            notice(f'인접 선거구 계산에 실패했습니다: {e}. shapely 및 제22대 GeoJSON을 확인해 주세요.')
    else:
        notice('인접 선거구 비교를 위해 254개 선거구의 주민등록인구 CSV가 필요합니다. 경계 간 인접 관계는 GeoJSON으로 자동 계산하도록 구현했습니다.')
        try:
            geo=load_geojson(); empty=pd.DataFrame({'SIDO_SGG':[f.get('properties',{}).get('SIDO_SGG') for f in geo.get('features',[]) if f.get('properties',{}).get('SIDO_SGG')],'상태':np.nan})
            st.plotly_chart(choropleth(geo,empty,'상태','인접 평균 대비',categorical=True),use_container_width=True)
        except Exception: pass

# ---------- 4. index distribution ----------
elif selected.startswith('4.'):
    st.header('총선별 표의 등가성 지수 분포')
    if has(historical,['총선','연도','SIDO_SGG','주민등록인구']):
        t=historical.dropna(subset=['총선','연도','SIDO_SGG','주민등록인구']).copy()
        choices=sorted(t['총선'].astype(str).unique().tolist())
        election=st.selectbox('총선 시기 선택',choices,key='dist_election')
        sub=t[t['총선'].astype(str)==election].copy()
        sub['표의 등가성 지수']=sub['주민등록인구'].mean()/sub['주민등록인구'].replace(0,np.nan)
        fig=px.histogram(sub,x='표의 등가성 지수',nbins=24,opacity=.85)
        fig.add_vline(x=1,line_dash='dash',line_color='#d9534f',annotation_text='전국 평균 = 1')
        fig.update_layout(height=510,margin=dict(l=10,r=10,t=25,b=10))
        fig.update_xaxes(title='표의 등가성 지수(주민등록인구 기준)')
        fig.update_yaxes(title='선거구 수')
        st.plotly_chart(fig,use_container_width=True)
        a,b,c=st.columns(3)
        a.metric('선거구 수',f'{len(sub):,}개')
        b.metric('지수 중앙값',f'{sub["표의 등가성 지수"].median():.3f}')
        c.metric('지수 표준편차',f'{sub["표의 등가성 지수"].std():.3f}')
        st.caption('지수 1 초과는 전국 평균보다 인구가 적은 선거구, 1 미만은 평균보다 인구가 많은 선거구를 뜻합니다.')
    else:
        notice('실제 분포를 그리려면 `historical_constituencies.csv`에 총선, 연도, SIDO_SGG, 주민등록인구 열과 각 총선의 선거구별 원자료가 필요합니다. 최대·최소·평균만으로는 분포를 복원할 수 없어 임의의 분포값은 만들지 않았습니다.')

# ---------- 5. period change analysis ----------
elif selected.startswith('5.'):
    st.header('총선 시기별 표의 등가성 변화 분석')
    if has(history,['총선','연도','최대인구','최소인구','평균인구']):
        t=history.dropna(subset=['연도','최대인구','최소인구','평균인구']).sort_values('연도').copy()
        t['최대·최소 인구편차 비율']=t['최대인구']/t['최소인구'].replace(0,np.nan)
        base_ratio=t.iloc[0]['최대·최소 인구편차 비율']
        t['표의 등가성 상대지수(첫 총선=100)']=base_ratio/t['최대·최소 인구편차 비율']*100
        t['최대·최소 범위/평균(%)']=(t['최대인구']-t['최소인구'])/t['평균인구']*100
        fig=go.Figure()
        fig.add_trace(go.Scatter(x=t['연도'],y=t['표의 등가성 상대지수(첫 총선=100)'],mode='lines+markers',name='표의 등가성 상대지수',
            customdata=t['총선'],hovertemplate='%{customdata}<br>%{x}년<br>상대지수 %{y:.2f}<extra></extra>'))
        fig.add_hline(y=100,line_dash='dot',line_color='#999',annotation_text='첫 번째 관측 총선 = 100')
        fig.update_layout(height=470,margin=dict(l=10,r=10,t=25,b=10),showlegend=False)
        fig.update_xaxes(title='총선 연도',dtick=4,tickformat='d')
        fig.update_yaxes(title='상대지수(높을수록 최대·최소 격차가 작음)')
        st.plotly_chart(fig,use_container_width=True)
        fig2=px.bar(t,x='총선',y='최대·최소 범위/평균(%)',text_auto='.1f')
        fig2.update_layout(height=350,margin=dict(l=10,r=10,t=15,b=10),showlegend=False)
        fig2.update_yaxes(title='(최대 인구 - 최소 인구) ÷ 평균 인구(%)')
        st.plotly_chart(fig2,use_container_width=True)
        st.dataframe(t[['총선','연도','최대·최소 인구편차 비율','표의 등가성 상대지수(첫 총선=100)','최대·최소 범위/평균(%)']],use_container_width=True,hide_index=True)
        st.warning('이 상대지수는 프로젝트에서 정의한 탐색용 지표입니다. 선거구별 전체 인구분포가 아닌 최대·최소·평균 요약값으로 계산하며, 공식 민주주의 지수나 법적 위법 판정 지표가 아닙니다. 첫 관측 총선을 100으로 놓고 최대·최소 인구비율의 상대 변화를 나타냅니다.')
    else:
        notice('election_history_summary.csv에 총선별 최대·최소·평균 인구 자료가 필요합니다.')

# ---------- 6. resident population and electorate ----------
elif selected.startswith('6.'):
    st.header('주민등록인구와 유권자수(선거인수)의 관계 분석')
    if has(voters_dist,['총선','선거구','주민등록인구','선거인수']):
        t=voters_dist.dropna(subset=['주민등록인구','선거인수']).copy()
        e=st.selectbox('총선 시기 선택',['전체']+sorted(t['총선'].astype(str).unique().tolist()),key='voters_election')
        if e!='전체': t=t[t['총선'].astype(str)==e]
        fig=px.scatter(t,x='주민등록인구',y='선거인수',color='시도' if '시도' in t else None,hover_name='선거구',trendline='ols' if len(t)>=3 else None)
        fig.update_layout(height=510,margin=dict(l=10,r=10,t=20,b=10))
        fig.update_xaxes(title='주민등록인구(명)',tickformat=',')
        fig.update_yaxes(title='선거인수(명)',tickformat=',')
        st.plotly_chart(fig,use_container_width=True)
        t['선거인수/주민등록인구(%)']=t['선거인수']/t['주민등록인구']*100
        st.metric('평균 선거인수 비율',f'{t["선거인수/주민등록인구(%)"].mean():.2f}%')
        st.caption('선거구별 원자료가 연결된 경우의 분석입니다. 주민등록인구와 선거인수의 기준일이 다를 수 있으므로 기준일을 확인해야 합니다.')
    elif has(voters_nat,['총선','연도','주민등록인구','선거인수']):
        t=voters_nat.dropna(subset=['주민등록인구','선거인수']).copy().sort_values('연도')
        t['선거인수 비율(%)']=t['선거인수']/t['주민등록인구']*100
        fig=px.scatter(t,x='주민등록인구',y='선거인수',text='총선',hover_data=['연도','선거인수 비율(%)'])
        fig.update_traces(textposition='top center',marker=dict(size=13,color='#2374c6'))
        fig.update_layout(height=490,margin=dict(l=10,r=10,t=25,b=10))
        fig.update_xaxes(title='전국 주민등록인구(명)',tickformat=',')
        fig.update_yaxes(title='전국 선거인수(명)',tickformat=',')
        st.plotly_chart(fig,use_container_width=True)
        fig2=px.line(t,x='연도',y='선거인수 비율(%)',markers=True,text='총선')
        fig2.update_layout(height=360,margin=dict(l=10,r=10,t=15,b=10))
        fig2.update_yaxes(title='선거인수 ÷ 주민등록인구(%)')
        st.plotly_chart(fig2,use_container_width=True)
        st.dataframe(t[['총선','연도','주민등록인구','선거인수','선거인수 비율(%)']],use_container_width=True,hide_index=True)
        st.warning('현재 기본 자료는 전국 합계 기준이며 선거구별 관계를 직접 보여주는 자료는 아닙니다. 선거구별 산점도를 보려면 election_voters_district.csv를 연결하세요. 전국 총계 3개 총선만으로 회귀관계를 일반화하지 않습니다.')
    else:
        notice('전국 단위 기본자료 또는 선거구별 자료가 없습니다. `election_voters_national.csv` 또는 `election_voters_district.csv`를 연결해 주세요.')

# Footer: data caveats and sources
st.divider()
st.caption('데이터 해석 원칙: 실제 원자료가 없는 수치는 생성하지 않습니다. 주민등록인구(미성년자 포함), 선거인수, 실제 투표자수는 서로 다른 개념입니다. 표의 등가성 지수는 주민등록인구 기준의 상대적 대표 규모를 나타내는 프로젝트 분석지표입니다.')
st.markdown('**주요 자료 출처**')
st.markdown('''
- 중앙선거관리위원회, 제22대 국회의원선거 총람: https://www.nec.go.kr
- 행정안전부 주민등록 인구통계: https://jumin.mois.go.kr/
- 중앙선거관리위원회 선거인수 정보(공공데이터포털): https://www.data.go.kr/data/15094967/openapi.do
- 제22대 국회의원 선거구 경계 GeoJSON: https://github.com/OhmyNews/2024_22_elec_map (MIT License)
''')
