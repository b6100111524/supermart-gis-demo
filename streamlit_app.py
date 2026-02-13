import streamlit as st
import pandas as pd
import pydeck as pdk
import shapely.wkt as wkt
from shapely.geometry import mapping
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import os
import altair as alt

# --- 品牌點位顏色定義 ---
brand_colors = {
    "統一超商股份有限公司": [235, 120, 35, 200],
    "全家便利商店股份有限公司": [0, 100, 180, 200],
    "萊爾富國際股份有限公司": [0, 229, 230, 200],
    "來來超商股份有限公司": [200, 0, 0, 200],
    "全聯實業股份有限公司": [0, 50, 150, 200]
}

# --- 初始化 Session State ---
if 'map_view' not in st.session_state:
    st.session_state.map_view = {
        "latitude": 25.04,
        "longitude": 121.55,
        "zoom": 11,
        "pitch": 0,
        "bearing": 0
    }

# --- 資料讀取函數 (使用 Cache 優化效能) ---
@st.cache_data
def load_data():
    base_path = os.path.dirname(__file__)
    # 建議讀取時加上 encoding 以防中文亂碼
    p_path = os.path.join(base_path, "data", "aoc_major_supermart_202512.csv")
    g_path = os.path.join(base_path, "data", "gs_grid1000_taiwan_supermart_2025.csv")
    
    df_p = pd.read_csv(p_path, encoding='utf-8-sig')
    df_g = pd.read_csv(g_path, encoding='utf-8-sig')
    return df_p, df_g

df_points, df_polygon = load_data()

# --- 輔助函數 ---
def create_point_tooltip(row):
    return f"""<div style="padding: 5px;"><b style="color: #FFA500;">📍 {row['store_name']}</b><br/>
               <b>品牌:</b> {row['company_name']}<br/><b>地址:</b> {row['store_address']}</div>"""

def create_grid_tooltip(row):
    return f"""<div style="padding: 5px;"><b style="color: #00BFFF;">▣ 1km 統計網格</b><br/>
               <b>區域總店數:</b> {row['convenience_store_count']} 筆</div>"""

def assign_color(company):
    company_str = str(company)
    for brand, color in brand_colors.items():
        if brand in company_str: return color
    return [150, 150, 150, 150]

# --- 資料預處理 ---
df_points['tooltip_html'] = df_points.apply(create_point_tooltip, axis=1)
df_points['color'] = df_points['company_name'].apply(assign_color)

df_polygon['tooltip_html'] = df_polygon.apply(create_grid_tooltip, axis=1)
df_polygon = df_polygon.rename(columns={'geometry': 'geometry_wkt'})

# 設定色階
cmap = plt.get_cmap('YlOrRd')
norm = mcolors.Normalize(vmin=df_polygon['convenience_store_count'].min(), vmax=df_polygon['convenience_store_count'].max())

def get_fill_color(val):
    rgba = cmap(norm(val))
    return [int(c * 255) for c in rgba[:3]] + [160]

df_polygon['geometry'] = df_polygon['geometry_wkt'].apply(lambda x: mapping(wkt.loads(x)))
df_polygon['fill_color'] = df_polygon['convenience_store_count'].apply(get_fill_color)
geojson_dict = df_polygon.to_dict(orient='records')
display_columns = ['company_name', 'store_name', 'store_address', 'longitude', 'latitude']

# --- UI 介面 ---
st.set_page_config(layout="wide", page_title="Web GIS POC")
st.title("Web GIS POC")

st.sidebar.header("地圖圖層控制")
show_grid = st.sidebar.checkbox("網格統計", value=True)
show_points = st.sidebar.checkbox("超商點位", value=True)

if 'selected_brand' not in st.session_state:
    st.session_state.selected_brand = "全部"

st.subheader("品牌快速篩選")
brands = ["全部"] + list(brand_colors.keys())
cols = st.columns(len(brands))
for i, brand in enumerate(brands):
    display_name = brand.replace("股份有限公司", "").replace("便利商店", "").replace("實業", "")
    if cols[i].button(display_name, width='stretch'):
        st.session_state.selected_brand = brand

filtered_df = df_points if st.session_state.selected_brand == "全部" else df_points[df_points['company_name'] == st.session_state.selected_brand]
st.info(f"目前顯示：{st.session_state.selected_brand} (共 {len(filtered_df)} 筆)")

# --- 圖層物件 ---
grid_layer = pdk.Layer('GeoJsonLayer', data=geojson_dict, pickable=True, filled=True, get_fill_color='fill_color', stroked=True, get_line_color=[255, 255, 255, 80], line_width_min_pixels=0.5)
point_layer = pdk.Layer("ScatterplotLayer", data=filtered_df, get_position='[longitude, latitude]', get_color='color', get_radius=50, pickable=True)

active_layers = []
if show_grid: active_layers.append(grid_layer)
if show_points: active_layers.append(point_layer)

# --- 分頁顯示 ---
tab1, tab2, tab3 = st.tabs(["單一地圖", "雙圖對比", "數據統計"])

with tab1:
    st.pydeck_chart(pdk.Deck(
        initial_view_state=pdk.ViewState(**st.session_state.map_view),
        layers=active_layers,
        map_style='light',
        tooltip={"html": "{tooltip_html}", "style": {"backgroundColor": "rgba(30,30,30,0.9)", "color": "white"}}
    ))

with tab2:
    st.subheader("同步對比模式")
    col1, col2 = st.columns(2)
    current_view = pdk.ViewState(**st.session_state.map_view, controller=True)
    with col1:
        st.caption("圖層 A (超商點位)")
        st.pydeck_chart(pdk.Deck(initial_view_state=current_view, layers=[point_layer], map_style='light', tooltip={"html": "{tooltip_html}"}), key="map_a")
    with col2:
        st.caption("圖層 B (網格統計)")
        st.pydeck_chart(pdk.Deck(initial_view_state=current_view, layers=[grid_layer], map_style='light', tooltip={"html": "{tooltip_html}"}), key="map_b")

with tab3:
    st.subheader("各縣市超商分佈統計")
    if 'county_name' in df_polygon.columns:
        df_stats = df_polygon.groupby('county_name')['convenience_store_count'].sum().reset_index().sort_values(by='convenience_store_count', ascending=False)
        chart = alt.Chart(df_stats).mark_bar(color='steelblue').encode(
            x=alt.X('county_name:N', sort='-y', title='縣市'),
            y=alt.Y('convenience_store_count:Q', title='超商總數'),
            tooltip=['county_name', 'convenience_store_count']
        ).properties(height=400)
        st.altair_chart(chart, width='stretch')
        st.dataframe(df_stats, width='stretch', hide_index=True)

st.subheader("連動資料表預覽")
st.dataframe(filtered_df[display_columns], width='stretch', hide_index=True)