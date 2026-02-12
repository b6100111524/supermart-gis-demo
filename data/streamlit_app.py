import streamlit as st
import pandas as pd
import pydeck as pdk
import shapely.wkt as wkt
from shapely.geometry import mapping

import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

import os

import altair as alt

# --- 品牌點位顏色定義 (RGBA 格式) ---
brand_colors = {
    "統一超商股份有限公司": [235, 120, 35, 200],    # 7-11 橘色
    "全家便利商店股份有限公司": [0, 100, 180, 200],  # 全家 藍色
    "萊爾富國際股份有限公司": [0, 229, 230, 200],      # 萊爾富 紅色
    "來來超商股份有限公司": [200, 0, 0, 200],      # OK 超商 黃色
    "全聯實業股份有限公司": [0, 50, 150, 200]        # 全聯 深藍
}

# --- 初始化視角 Session State ---
if 'map_view' not in st.session_state:
    st.session_state.map_view = {
        "latitude": 25.04,
        "longitude": 121.55,
        "zoom": 11,
        "pitch": 0,
        "bearing": 0
    }


# @st.cache_resource # 快取連線，避免重複登入
@st.cache_data

# --- 連線 ---
def get_query_result(query):
    with sql.connect(server_hostname=HOST, http_path=HTTP_PATH, access_token=TOKEN) as conn:
        with conn.cursor() as cursor:
            cursor.execute(query)
            return pd.DataFrame(cursor.fetchall(), columns=[desc[0] for desc in cursor.description])

# --- 點資料處理 ---
def create_point_tooltip(row):
    return f"""
        <div style="padding: 5px;">
            <b style="color: #FFA500;">📍 {row['store_name']}</b><br/>
            <b>品牌:</b> {row['company_name']}<br/>
            <b>地址:</b> {row['store_address']}
        </div>
    """

# --- 面資料處理 ---
def create_grid_tooltip(row):
    return f"""
        <div style="padding: 5px;">
            <b style="color: #00BFFF;">▣ 1km 統計網格</b><br/>
            <b>區域總店數:</b> {row['convenience_store_count']} 筆
        </div>
    """


# --- 網格數值顏色定義 ---
def get_color(val):
    rgba = cmap(norm(val))
    return [int(c * 255) for c in rgba[:3]] + [160]

# --- 店面品牌顏色定義 ---
def assign_color(company):
    company_str = str(company)
    for brand, color in brand_colors.items():
        if brand in company_str:
            return color
    return [150, 150, 150, 150] # 若都沒對到，顯示灰色


# --- 讀取點資料 ---
# point_query = "" \
#               "select * " \
#               "from hims_catalog.raw_irent.aoc_major_supermart_202512 " \
#               "where store_status=1" \
#               ""

# # --- 讀取面資料 ---
# poly_query = "" \
#              "select * " \
#              "from dev_silver.enrich.gs_grid1000_taiwan_supermart_2025" \
#              ""


# --- 讀取本地資料替代連線 ---
# 取得目前程式碼所在的資料夾路徑
base_path = os.path.dirname(__file__)

# 讀取點資料
points_path = os.path.join(base_path, "data", "aoc_major_supermart_202512.csv")
df_points = pd.read_csv(points_path)

# 讀取面資料
poly_path = os.path.join(base_path, "data", "gs_grid1000_taiwan_supermart_2025.csv")
df_polygon = pd.read_csv(poly_path)


# --- 點資料處理 ---
# df_points = get_query_result(point_query)
df_points['tooltip_html'] = df_points.apply(create_point_tooltip, axis=1)
df_points['color'] = df_points['company_name'].apply(assign_color)

# --- 面資料處理 ---
# df_polygon = get_query_result(poly_query)
df_polygon['tooltip_html'] = df_polygon.apply(create_grid_tooltip, axis=1)
df_polygon = df_polygon.rename(columns={'geometry': 'geometry_wkt'})

cmap = plt.get_cmap('YlOrRd')
norm = mcolors.Normalize(vmin=df_polygon['convenience_store_count'].min(), vmax=df_polygon['convenience_store_count'].max())

df_polygon['geometry'] = df_polygon['geometry_wkt'].apply(lambda x: mapping(wkt.loads(x)))
df_polygon['fill_color'] = df_polygon['convenience_store_count'].apply(get_color)
geojson_dict = df_polygon.to_dict(orient='records')
display_columns = ['company_name', 'store_name', 'store_address', 'longitude', 'latitude']


# --- 設定頁面 ---
st.set_page_config(layout="wide")
st.title("Web GIS POC")


# --- 側邊欄：圖層顯示切換 ---
st.sidebar.header("地圖圖層控制")
# 使用 checkbox 讓使用者決定是否顯示
show_grid = st.sidebar.checkbox("網格統計", value=True)
show_points = st.sidebar.checkbox("超商點位", value=True)


# --- 初始化 Session State 儲存選中的品牌 ---
if 'selected_brand' not in st.session_state:
    st.session_state.selected_brand = "全部"

# --- 最上方的按鈕列 ---
st.subheader("品牌快速篩選")
brands = ["全部"] + list(brand_colors.keys())
cols = st.columns(len(brands))

for i, brand in enumerate(brands):
    # 簡化按鈕顯示名稱（例如把股份有限公司去掉）
    display_name = brand.replace("股份有限公司", "").replace("便利商店", "").replace("實業", "")
    
    if cols[i].button(display_name, width='stretch'):
        st.session_state.selected_brand = brand

# --- 根據按鈕狀態過濾資料 ---
if st.session_state.selected_brand == "全部":
    filtered_df = df_points
else:
    filtered_df = df_points[df_points['company_name'] == st.session_state.selected_brand]

st.info(f"目前顯示：{st.session_state.selected_brand} (共 {len(filtered_df)} 筆)")


# --- 面資料圖層 (GeoJsonLayer) ---
grid_layer = pdk.Layer(
    'GeoJsonLayer',
    data=geojson_dict,
    pickable=True,
    filled=True,
    get_fill_color='fill_color', # 使用色階庫算出的顏色
    stroked=True,
    get_line_color=[255, 255, 255, 80],
    line_width_min_pixels=0.5
)

# --- 點資料圖層 (Scatterplot) ---
point_layer = pdk.Layer(
    "ScatterplotLayer",
    data=filtered_df,
    get_position='[longitude, latitude]',
    get_color='color',
    get_radius=50,
    pickable=True,
    line_width_min_pixels=0.5
)

# --- 視角設定 ---
view_state = pdk.ViewState(
    latitude=25.04,
    longitude=121.55,
    zoom=11,
    pitch=0
)


# --- 動態圖層邏輯 ---
active_layers = []

# 根據開關狀態加入圖層，順序決定疊加層級 (先加的在下層)
if show_grid:
    active_layers.append(grid_layer)

if show_points:
    active_layers.append(point_layer)


# --- 加入功能分頁 ---
# tab1, tab2 = st.tabs(["單一地圖檢視", "雙圖對比模式"])
tab1, tab2, tab3 = st.tabs(["單一地圖", "雙圖對比", "數據統計"])


with tab1:
    # 這裡放你原本的單圖渲染代碼
    st.pydeck_chart(pdk.Deck(
        initial_view_state=pdk.ViewState(**st.session_state.map_view),
        layers=active_layers,
        map_style='light',
        tooltip={"html": "{tooltip_html}", "style": {"backgroundColor": "rgba(30,30,30,0.9)", "color": "white"}}
    ))

with tab2:
    st.subheader("同步對比模式")
    col1, col2 = st.columns(2)
    
    # 建立目前基準視角
    current_view = pdk.ViewState(
        latitude=st.session_state.map_view["latitude"],
        longitude=st.session_state.map_view["longitude"],
        zoom=st.session_state.map_view["zoom"],
        pitch=st.session_state.map_view["pitch"],
        bearing=st.session_state.map_view["bearing"],
        controller=True # 正確的參數位置在此
    )

    with col1:
        st.caption("圖層 A (超商點位)")
        st.pydeck_chart(pdk.Deck(
            initial_view_state=current_view,
            layers=[point_layer],
            map_style='light',
            tooltip={"html": "{tooltip_html}"}
        ), key="map_a", width='stretch')

    with col2:
        st.caption("圖層 B (網格統計)")
        st.pydeck_chart(pdk.Deck(
            initial_view_state=current_view,
            layers=[grid_layer],
            map_style='light',
            tooltip={"html": "{tooltip_html}"}
        ), key="map_b", width='stretch')


with tab3:
    st.subheader("各縣市超商分佈統計")
    if 'county_name' in df_polygon.columns:
        df_stats = df_polygon.groupby('county_name')['convenience_store_count'].sum().reset_index()
        df_stats = df_stats.sort_values(by='convenience_store_count', ascending=False)
        
        chart = alt.Chart(df_stats).mark_bar(color='steelblue').encode(
            x=alt.X('county_name:N', sort='-y', title='縣市'),
            y=alt.Y('convenience_store_count:Q', title='超商總數'),
            tooltip=['county_name', 'convenience_store_count']
        ).properties(height=400) # 移除 width='stretch'
        
        st.altair_chart(chart, width='stretch')
        st.dataframe(df_stats, width='stretch', hide_index=True)

st.subheader("連動資料表預覽")
st.dataframe(
    filtered_df[display_columns], 
    width='stretch', 
    hide_index=True # 隱藏左側索引，介面更乾淨
)
