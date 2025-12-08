import streamlit as st
import pandas as pd
import folium
from folium.plugins import Fullscreen
from streamlit_folium import st_folium
import json
import os
import unicodedata
import requests
import xml.etree.ElementTree as ET
import re

# 住所検索・距離計算用ライブラリ
try:
    from geopy.distance import geodesic
    HAS_GEOPY = True
except ImportError:
    HAS_GEOPY = False

# Google API 関連
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# =========================================================
# 🔐 0. 簡易ログイン & 設定
# =========================================================
PASSWORD = st.secrets.get("app_password", "bus")
SPREADSHEET_ID = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"

# 🎨 配色設定
ROUTE_COLORS = {
    "井沼便": "#FF0000",
    "東岩槻便": "#FF9900",
    "美園便": "#800080",
    "美園便（登校）": "#800080",
    "美園便（下校）": "#800080",
    "西原便": "#56B4E9",
    "諏訪便": "#009E73",
    "加倉便": "#F0E442",
    "小溝便": "#0072B2",
    "府内便": "#882255",
    "府内便（登校）": "#882255",
    "府内便（下校）": "#882255",
    "小中蓮田循環便": "#FF0000",
    "小中岩槻中央便": "#F0E442",
    "小中岩槻北便": "#009E73",
    "小中岩槻南便": "#800080",
    "小中岩槻公園便": "#753603",
    "小中蓮田便": "#120AF4",
    "高等部蓮田便": "#F13636",
    "高等部岩槻北便": "#56B4E9",
    "高等部岩槻南便": "#F0E442",
}
DEFAULT_COLOR = "#333333"

def check_password():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.set_page_config(page_title="ログイン", layout="centered")
        st.markdown("## 🔒 スクールバス運行管理")
        input_pass = st.text_input("パスワード", type="password")
        if st.button("ログイン", type="primary"):
            if input_pass == PASSWORD:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

if not check_password():
    st.stop()

st.set_page_config(layout="wide", page_title="スクールバス運行マップ (Pro)")

# ---------------------------------------------------------
# 📥 データ読み込み
# ---------------------------------------------------------
def clean_df(df):
    if df.empty: return df
    df = df.fillna("")
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
        df[col] = df[col].replace(["nan", "None"], "")
    return df

def read_csv_auto_encoding(file_path):
    try:
        return clean_df(pd.read_csv(file_path, encoding='utf-8'))
    except UnicodeDecodeError:
        return clean_df(pd.read_csv(file_path, encoding='cp932'))

def load_local_csv():
    try:
        s_df = read_csv_auto_encoding("data/bus_stops.csv")
        st_df = read_csv_auto_encoding("data/students.csv")
        return s_df, st_df, True
    except FileNotFoundError:
        return pd.DataFrame(), pd.DataFrame(), False

def load_from_google_sheets():
    if "google_credentials" not in st.secrets:
        raise ValueError("Secretsなし")
    creds_dict = dict(st.secrets["google_credentials"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    credentials = Credentials.from_service_account_info(
        creds_dict, scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    service = build('sheets', 'v4', credentials=credentials)
    sheet_stops = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="bus_stops!A:H").execute()
    rows_stops = sheet_stops.get('values', [])
    stops_df = pd.DataFrame(rows_stops[1:], columns=rows_stops[0]) if rows_stops else pd.DataFrame()
    sheet_students = service.spreadsheets().values().get(spreadsheetId=SPREADSHEET_ID, range="students!A:I").execute()
    rows_students = sheet_students.get('values', [])
    students_df = pd.DataFrame(rows_students[1:], columns=rows_students[0]) if rows_students else pd.DataFrame()
    return clean_df(stops_df), clean_df(students_df)

@st.cache_data(ttl=600)
def load_data():
    data_source = "未定義"
    try:
        stops_df, students_df = load_from_google_sheets()
        if stops_df.empty: raise ValueError("Sheet Empty")
        data_source = "Google Sheets (Live)"
    except Exception:
        stops_df, students_df, success = load_local_csv()
        if success: data_source = "CSV (Offline)"
        else:
            st.error("❌ データ読み込み失敗"); st.stop()
    stops_df["lat"] = pd.to_numeric(stops_df["lat"], errors='coerce')
    stops_df["lng"] = pd.to_numeric(stops_df["lng"], errors='coerce')
    for col in ["time_to", "time_from"]:
        if col not in stops_df.columns: stops_df[col] = "-"
    if "direction" not in students_df.columns: students_df["direction"] = "-"
    return stops_df, students_df, data_source

raw_stops_df, raw_students_df, current_source = load_data()

# ---------------------------------------------------------
# 🧠 UI & ロジック
# ---------------------------------------------------------
st.sidebar.title("🚌 運行管理メニュー")

schedule_mode = st.sidebar.selectbox("📅 運行スケジュール", ("通常便", "小中時差便", "高時差便"), index=0)

if "current_schedule_mode" not in st.session_state:
    st.session_state["current_schedule_mode"] = schedule_mode
if st.session_state["current_schedule_mode"] != schedule_mode:
    st.session_state["search_results_df"] = None
    st.session_state["search_coords"] = None
    st.session_state["current_schedule_mode"] = schedule_mode

st.sidebar.markdown("---")

# データ前処理
target_schedule_type = "通常"
if schedule_mode == "小中時差便": target_schedule_type = "時差"
elif schedule_mode == "高時差便": target_schedule_type = "高等部"

if "schedule_type" in raw_stops_df.columns:
    stops_df = raw_stops_df[raw_stops_df["schedule_type"] == target_schedule_type].copy()
else:
    stops_df = raw_stops_df.copy()

students_df = raw_students_df.copy()
if schedule_mode == "通常便": src_route_col, src_stop_col = "route_normal", "stop_normal"
elif schedule_mode == "小中時差便": src_route_col, src_stop_col = "route_jisa", "stop_jisa"
else: src_route_col, src_stop_col = "route_kotobu", "stop_kotobu"

if src_route_col in students_df.columns and src_stop_col in students_df.columns:
    students_df["route"] = students_df[src_route_col]
    students_df["stop_name"] = students_df[src_stop_col]

students_df = students_df[students_df["route"] != ""]

geojson_file_path = "data/routes.geojson"
if schedule_mode == "小中時差便": geojson_file_path = "data/routes_jisa.geojson"
elif schedule_mode == "高時差便": geojson_file_path = "data/routes_kotobu.geojson"

mode_selection = st.sidebar.radio("表示モード", ("☀️ 登校 (行き)", "🌙 下校 (帰り)", "🔄 すべて (全体)"), horizontal=False)
is_to_school = (mode_selection == "☀️ 登校 (行き)")
is_from_school = (mode_selection == "🌙 下校 (帰り)")
is_all_mode = (mode_selection == "🔄 すべて (全体)")

# 🆕 地図スタイルの切り替えボタン（選択肢を網羅）
st.sidebar.markdown("---")
st.sidebar.subheader("🗺️ 地図設定")
map_style_selection = st.sidebar.radio(
    "地図の見た目",
    (
        "見やすい地図 (国土地理院・淡色)", 
        "標準地図 (国土地理院)", 
        "航空写真 (国土地理院)", 
        "シンプル (路線強調)", 
        "詳細 (OpenStreetMap)"
    ),
    index=0
)

target_student_info = None

if "search_results_df" not in st.session_state: st.session_state["search_results_df"] = None
if "search_coords" not in st.session_state: st.session_state["search_coords"] = None

# -----------------------------------------------------
# 🆕 住所で最寄りバス停検索機能 (最強版: 国土地理院API + 自動フォールバック)
# -----------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.subheader("🏠 住所でバス停検索")
input_address = st.sidebar.text_input("住所を入力", placeholder="例: 〇〇区〇〇町 3-15")
st.sidebar.caption("※番地が見つからない場合は自動で周辺を表示します。")

def search_address_ultimate(address_str):
    """
    1. 国土地理院API (最強・あいまい検索可)
    2. 農研機構API
    3. Geocoding.jp
    4. 最後の手段: 数字を削除して町名だけで検索
    """
    normalized_addr = unicodedata.normalize('NFKC', address_str)
    
    # 検索リスト（そのままの住所 と、数字を除去した町名のみ）
    search_queries = [normalized_addr]
    
    # 数字除去バージョンの作成 (例: 深作3 -> 深作)
    addr_without_digits = re.sub(r'\d+[-]*\d*', '', normalized_addr).strip()
    if addr_without_digits and addr_without_digits != normalized_addr:
        search_queries.append(addr_without_digits)

    for query in search_queries:
        # --- 1. 国土地理院 API (Msearch) ---
        try:
            url_gsi = "https://msearch.gsi.go.jp/address-search/AddressSearch"
            res_gsi = requests.get(url_gsi, params={"q": query}, timeout=10)
            if res_gsi.status_code == 200:
                data = res_gsi.json()
                if len(data) > 0:
                    coords = data[0]["geometry"]["coordinates"] # [lon, lat]
                    return float(coords[1]), float(coords[0]), "国土地理院"
        except Exception:
            pass

        # --- 2. 農研機構 API ---
        try:
            url_naro = "https://aginfo.cgk.affrc.go.jp/ws/geocode/search"
            headers = {"User-Agent": "school_bus_app_v5"}
            res_naro = requests.get(url_naro, params={"addr": query}, headers=headers, timeout=10)
            if res_naro.status_code == 200:
                data = res_naro.json()
                if data.get("result") and len(data["result"]) > 0:
                    top = data["result"][0]
                    return float(top["lat"]), float(top["lon"]), "農研機構"
        except Exception:
            pass

        # --- 3. Geocoding.jp ---
        try:
            url_geo = f"https://www.geocoding.jp/api/?q={query}"
            res_geo = requests.get(url_geo, timeout=10)
            if res_geo.status_code == 200:
                tree = ET.fromstring(res_geo.content)
                lat_node = tree.find("coordinate/lat")
                lng_node = tree.find("coordinate/lng")
                if lat_node is not None and lng_node is not None:
                    return float(lat_node.text), float(lng_node.text), "Geocoding.jp"
        except Exception:
            pass
            
    return None, None, None

if st.sidebar.button("最寄りバス停を探す"):
    if not HAS_GEOPY:
        st.sidebar.error("⚠️ 'geopy' ライブラリ不足")
    elif not input_address:
         st.sidebar.warning("住所を入力してください。")
    else:
        # 実行
        lat, lng, source_api = search_address_ultimate(input_address)
            
        if lat and lng:
            st.session_state["search_coords"] = (lat, lng)
            
            valid_stops_for_search = stops_df.dropna(subset=["lat", "lng"]).copy()
            if not valid_stops_for_search.empty:
                valid_stops_for_search["distance"] = valid_stops_for_search.apply(
                    lambda row: geodesic((lat, lng), (row["lat"], row["lng"])).meters, axis=1
                )
                top3_stops = valid_stops_for_search.sort_values("distance").head(3)
                st.session_state["search_results_df"] = top3_stops
                
                msg = f"発見しました！ ({source_api})"
                st.sidebar.success(msg)
            else:
                st.sidebar.warning("バス停データがありません。")
                st.session_state["search_results_df"] = None
        else:
            st.sidebar.error("❌ 住所が見つかりませんでした。別の書き方をお試しください。")

if st.session_state["search_results_df"] is not None and not st.session_state["search_results_df"].empty:
    st.sidebar.success("📍 **最寄りバス停 (近い順)**")
    for i, (idx, row) in enumerate(st.session_state["search_results_df"].iterrows()):
        dist = int(row["distance"])
        rank_icon = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
        st.sidebar.info(f"{rank_icon} **{row['stop_name']}**\n路線: {row['route']} (約{dist}m)")
    
    if st.sidebar.button("住所確認を終了する（リセット）", type="primary"):
        st.session_state["search_results_df"] = None
        st.session_state["search_coords"] = None
        st.rerun()

# -----------------------------------------------------

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 生徒検索・指定")

search_query = st.sidebar.text_input("名前検索", placeholder="名前を入力")
search_candidates = pd.DataFrame()
if search_query:
    search_candidates = students_df[students_df["name"].str.contains(search_query, na=False)]

if not search_candidates.empty:
    if len(search_candidates) == 1:
        target_student_info = search_candidates.iloc[0]
        st.sidebar.success(f"発見: {target_student_info['name']}")
    else:
        st.sidebar.warning(f"{len(search_candidates)}名 ヒット")
        candidate_indices = search_candidates.index.tolist()
        def format_candidate(idx):
            row = search_candidates.loc[idx]
            dept = f"[{row['department']}] " if "department" in row and row['department'] else ""
            return f"{dept}{row['name']} ({row['route']} - {row['stop_name']})"
        selected_idx = st.sidebar.selectbox("生徒を選択", candidate_indices, format_func=format_candidate)
        if selected_idx in search_candidates.index:
            target_student_info = search_candidates.loc[selected_idx]
elif search_query:
    st.sidebar.error("該当者なし")

st.sidebar.markdown("---")
unique_routes = sorted(stops_df["route"].unique().tolist())
route_options = ["すべて表示"] + unique_routes
default_ix = 0
if target_student_info is not None:
    if target_student_info["route"] in route_options: default_ix = route_options.index(target_student_info["route"])
elif st.session_state["search_results_df"] is not None:
    nearest_one = st.session_state["search_results_df"].iloc[0]
    if nearest_one["route"] in route_options: default_ix = route_options.index(nearest_one["route"])

selected_route = st.sidebar.selectbox("📍 路線選択", route_options, index=default_ix)

if selected_route != "すべて表示":
    students_in_route = students_df[students_df["route"] == selected_route].sort_values("name")
    student_indices = students_in_route.index.tolist()
    default_sel_idx = None
    if target_student_info is not None:
        if target_student_info.name in student_indices: default_sel_idx = student_indices.index(target_student_info.name)
    options = [None] + student_indices
    def format_student_opt(idx):
        if idx is None: return "(選択なし)"
        if idx in students_in_route.index: return students_in_route.loc[idx, "name"]
        return "不明"
    box_idx = 0
    if default_sel_idx is not None: box_idx = default_sel_idx + 1
    selected_student_idx = st.sidebar.selectbox("👶 生徒詳細へジャンプ", options, format_func=format_student_opt, index=box_idx)
    if selected_student_idx is not None and selected_student_idx in students_in_route.index:
        target_student_info = students_in_route.loc[selected_student_idx]

st.sidebar.markdown("---")
st.sidebar.caption(f"Source: {current_source}")
if st.sidebar.button("ログアウト"):
    st.session_state["logged_in"] = False; st.rerun()

# =========================================================
# 📝 メインエリア
# =========================================================
if is_to_school: header_color, header_icon, header_text = "blue", "🏫", "登校モード"
elif is_from_school: header_color, header_icon, header_text = "orange", "🏠", "下校モード"
else: header_color, header_icon, header_text = "green", "🔄", "全体表示モード"

st.markdown(f"""
<div style="border-left: 5px solid {header_color}; padding-left: 15px; margin-bottom: 10px;">
    <h1 style='margin:0; font-size: 28px;'>{header_icon} 運行管理 <small style="color:gray;">({header_text})</small></h1>
    <span style="background-color: #eee; padding: 2px 8px; border-radius: 4px; font-size: 0.8em;">設定: {schedule_mode}</span>
</div>
""", unsafe_allow_html=True)

if target_student_info is not None:
    s_stop_info = stops_df[(stops_df["route"] == target_student_info["route"]) & (stops_df["stop_name"] == target_student_info["stop_name"])]
    t_to = s_stop_info.iloc[0].get("time_to", "-") if not s_stop_info.empty else "-"
    t_from = s_stop_info.iloc[0].get("time_from", "-") if not s_stop_info.empty else "-"
    dept_info = f" ({target_student_info['department']})" if "department" in target_student_info and target_student_info['department'] else ""
    st.info(f"""
    **👤 生徒詳細: {target_student_info['name']} さん{dept_info}**
    📍 **{target_student_info['route']}** - **{target_student_info['stop_name']}** (登録区分: {target_student_info['direction']})
    | ☀️ 行き (登校) | 🌙 帰り (下校) |
    |:---:|:---:|
    | ⏰ **{t_to}** | ⏰ **{t_from}** |
    """)

if st.session_state["search_results_df"] is not None and not st.session_state["search_results_df"].empty:
    nearest_row = st.session_state["search_results_df"].iloc[0]
    st.success(f"""
    **🏠 住所検索結果: 一番近いバス停**
    📍 **{nearest_row['stop_name']}** ({nearest_row['route']}) まで **約{int(nearest_row['distance'])}m**
    """)

valid_stops = stops_df.dropna(subset=["lat", "lng"])

if st.session_state["search_coords"] is not None:
    center_lat, center_lng = st.session_state["search_coords"]
    zoom_start = 15
elif target_student_info is not None:
    target_stop = stops_df[(stops_df["route"] == target_student_info["route"]) & (stops_df["stop_name"] == target_student_info["stop_name"])]
    if not target_stop.empty and pd.notna(target_stop.iloc[0]["lat"]) and pd.notna(target_stop.iloc[0]["lng"]):
        center_lat, center_lng = target_stop.iloc[0]["lat"], target_stop.iloc[0]["lng"]
        zoom_start = 16
    else:
        if not valid_stops.empty: center_lat, center_lng = valid_stops["lat"].mean(), valid_stops["lng"].mean()
        else: center_lat, center_lng = 35.6895, 139.6917
        zoom_start = 14
else:
    if not valid_stops.empty: center_lat, center_lng = valid_stops["lat"].mean(), valid_stops["lng"].mean()
    else: center_lat, center_lng = 35.6895, 139.6917
    zoom_start = 14

# 🆕 地図タイルの設定 (全選択肢対応)
attr = None
if "見やすい地図" in map_style_selection:
    # 🆕 国土地理院「淡色地図」
    selected_tiles = "https://cyberjapandata.gsi.go.jp/xyz/pale/{z}/{x}/{y}.png"
    attr = "<a href='https://maps.gsi.go.jp/development/ichiran.html' target='_blank'>国土地理院</a>"
elif "標準地図" in map_style_selection:
    # 復活: 国土地理院「標準地図」
    selected_tiles = "https://cyberjapandata.gsi.go.jp/xyz/std/{z}/{x}/{y}.png"
    attr = "<a href='https://maps.gsi.go.jp/development/ichiran.html' target='_blank'>国土地理院</a>"
elif "航空写真" in map_style_selection:
    selected_tiles = "https://cyberjapandata.gsi.go.jp/xyz/seamlessphoto/{z}/{x}/{y}.jpg"
    attr = "<a href='https://maps.gsi.go.jp/development/ichiran.html' target='_blank'>国土地理院</a>"
elif "シンプル" in map_style_selection:
    selected_tiles = "CartoDB positron"
else:
    selected_tiles = "OpenStreetMap"

m = folium.Map(
    location=[center_lat, center_lng], 
    zoom_start=zoom_start, 
    tiles=selected_tiles, 
    attr=attr,
    scrollWheelZoom=False
)
Fullscreen(position="topright", title="全画面表示", title_cancel="元のサイズに戻す", force_separate_button=True).add_to(m)

if st.session_state["search_coords"] is not None:
    folium.Marker(location=st.session_state["search_coords"], icon=folium.Icon(color="green", icon="home", prefix="fa"), tooltip="検索した住所").add_to(m)
    if st.session_state["search_results_df"] is not None:
        nearest_row = st.session_state["search_results_df"].iloc[0]
        folium.PolyLine(locations=[st.session_state["search_coords"], (nearest_row["lat"], nearest_row["lng"])], color="blue", weight=2, dash_array="5, 5", tooltip=f"約{int(nearest_row['distance'])}m").add_to(m)

nearest_route_name = None
if st.session_state["search_results_df"] is not None and not st.session_state["search_results_df"].empty:
    nearest_route_name = st.session_state["search_results_df"].iloc[0]["route"]

if os.path.exists(geojson_file_path):
    try:
        with open(geojson_file_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        if "features" in geojson_data:
            for feature in geojson_data["features"]:
                if "properties" not in feature: feature["properties"] = {}
                props = feature["properties"]
                if "name" not in props or props["name"] == "不明":
                    for key in props.keys():
                        if key in ROUTE_COLORS:
                            props["name"] = key; break
                    if "name" not in props: props["name"] = "不明"

        def style_function(feature):
            props = feature.get('properties', {})
            r_name = props.get("name", "不明")
            is_active = False
            is_hit = False
            if selected_route == "すべて表示": is_hit = True
            else:
                rn, sr = r_name.strip(), selected_route.strip()
                if (rn == sr) or (rn in sr) or (sr in rn): is_hit = True
            if is_hit:
                if "（登校）" in r_name:
                    if is_to_school or is_all_mode: is_active = True
                elif "（下校）" in r_name:
                    if is_from_school or is_all_mode: is_active = True
                else: is_active = True
            if nearest_route_name:
                n_r, r_n = nearest_route_name.strip(), r_name.strip()
                if (n_r == r_n) or (n_r in r_n) or (r_n in n_r):
                    if "（登校）" in r_name:
                        if is_to_school or is_all_mode: is_active = True
                    elif "（下校）" in r_name:
                        if is_from_school or is_all_mode: is_active = True
                    else: is_active = True
            line_color = ROUTE_COLORS.get(r_name, ROUTE_COLORS.get(selected_route, DEFAULT_COLOR))
            return {'color': line_color, 'weight': 6 if is_active else 0, 'opacity': 0.9 if is_active else 0}

        folium.GeoJson(geojson_data, style_function=style_function, tooltip=folium.GeoJsonTooltip(fields=["name"], aliases=["便名: "])).add_to(m)
    except Exception: pass

for _, row in stops_df.iterrows():
    if pd.isna(row["lat"]) or pd.isna(row["lng"]): continue
    r_name, s_name = row["route"], row["stop_name"]
    is_route_selected = (selected_route == "すべて表示") or (selected_route == r_name)
    is_target_stop = False
    search_rank = None
    if st.session_state["search_results_df"] is not None:
        for i, (idx, res_row) in enumerate(st.session_state["search_results_df"].iterrows()):
            if res_row["route"] == r_name and res_row["stop_name"] == s_name:
                search_rank = i; break
    if target_student_info is not None:
        if target_student_info["route"] == r_name and target_student_info["stop_name"] == s_name: is_target_stop = True

    if is_target_stop:
        icon_color, radius, line_weight, fill_opacity, z_index = "#FF0000", 12, 3, 1.0, 1000
    elif search_rank == 0:
        icon_color, radius, line_weight, fill_opacity, z_index = "green", 10, 3, 1.0, 900
    elif search_rank is not None:
        icon_color, radius, line_weight, fill_opacity, z_index = "lightgreen", 8, 2, 1.0, 800
    elif is_route_selected:
        icon_color, radius, line_weight, fill_opacity, z_index = ROUTE_COLORS.get(r_name, DEFAULT_COLOR), 7, 1, 0.9, 0
    else:
        icon_color, radius, line_weight, fill_opacity, z_index = "#CCCCCC", 3, 0, 0.4, -1
    
    t_display = f"行き:{row.get('time_to','-')} / 帰り:{row.get('time_from','-')}"
    students_at_stop_map = students_df[(students_df["route"] == r_name) & (students_df["stop_name"] == s_name)]
    if is_to_school: students_at_stop_map = students_at_stop_map[students_at_stop_map["direction"].str.contains("登校", na=False)]
    elif is_from_school: students_at_stop_map = students_at_stop_map[students_at_stop_map["direction"].str.contains("下校", na=False)]
    s_names_list = students_at_stop_map["name"].tolist()
    s_names_str = "、".join(s_names_list) if s_names_list else "(なし)"
    popup_html = f"""
    <div style="font-family:sans-serif; width:220px;">
        <h4 style="margin:0; color:{ROUTE_COLORS.get(r_name, 'black')};">{s_name}</h4>
        <div style="background-color:#f0f0f0; padding:5px; margin:5px 0; border-radius:4px;"><small>{t_display}</small></div>
        <div style="margin-top:5px; font-size:0.9em;"><strong>生徒:</strong> {s_names_str}</div>
        <small style="color:gray;">{r_name}</small>
    </div>
    """
    folium.CircleMarker(
        location=[row["lat"], row["lng"]], radius=radius, color="white" if (is_target_stop or search_rank is not None) else icon_color,
        weight=line_weight, fill=True, fill_color=icon_color, fill_opacity=fill_opacity, popup=folium.Popup(popup_html, max_width=250), z_index_offset=z_index
    ).add_to(m)
    if is_target_stop:
        folium.Marker(location=[row["lat"], row["lng"]], icon=folium.Icon(color="red", icon="user", prefix="fa"), tooltip=f"{target_student_info['name']} さん").add_to(m)
    elif search_rank == 0:
         folium.Marker(location=[row["lat"], row["lng"]], icon=folium.Icon(color="green", icon="info-sign", prefix="fa"), tooltip=f"最寄り1位: {s_name}").add_to(m)

with st.expander("🗺️ 運行マップ (クリックで開閉)", expanded=True): st_folium(m, use_container_width=True, height=500)

st.markdown("---")
if selected_route == "すべて表示": target_routes = sorted(stops_df["route"].unique().tolist())
else: target_routes = [selected_route]

for r_name in target_routes:
    r_color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR)
    st.markdown(f"### <span style='color:{r_color};'>■</span> {r_name}", unsafe_allow_html=True)
    route_stops = stops_df[stops_df["route"] == r_name].copy()
    if "sequence" in route_stops.columns: route_stops = route_stops.sort_values("sequence")
    table_rows = []
    for _, stop in route_stops.iterrows():
        s_name = stop["stop_name"]
        students_at_stop = students_df[(students_df["route"] == r_name) & (students_df["stop_name"] == s_name)]
        students_list_str = []
        if is_all_mode:
            for _, st_row in students_at_stop.iterrows():
                d_raw = str(st_row["direction"])
                d_mark = d_raw[0] if len(d_raw) > 0 else "?"
                students_list_str.append(f"{st_row['name']}({d_mark})")
        else:
            target_str = "登校" if is_to_school else "下校"
            filtered = students_at_stop[students_at_stop["direction"].str.contains(target_str, na=False)]
            students_list_str = filtered["name"].tolist()
        display_stop = s_name
        if target_student_info is not None and target_student_info["stop_name"] == s_name and target_student_info["route"] == r_name:
            display_stop = f"🔴 {s_name}"; target_name = target_student_info["name"]
            students_list_str = [f"**{s}**" if target_name in s else s for s in students_list_str]
        if st.session_state["search_results_df"] is not None:
             for i, (idx, res_row) in enumerate(st.session_state["search_results_df"].iterrows()):
                 if res_row["stop_name"] == s_name and res_row["route"] == r_name:
                     rank_icon = ["🥇", "🥈", "🥉"][i] if i < 3 else ""
                     display_stop = f"{rank_icon} {s_name} (最寄り{i+1})"
        final_student_str = "、".join(students_list_str)
        row_data = {"バス停名": display_stop}
        if is_all_mode:
            row_data["行き"] = stop.get("time_to", "-"); row_data["帰り"] = stop.get("time_from", "-"); row_data["利用生徒"] = final_student_str
        elif is_to_school:
            row_data["時間"] = stop.get("time_to", "-"); row_data["登校生徒"] = final_student_str
        else:
            row_data["時間"] = stop.get("time_from", "-"); row_data["下校生徒"] = final_student_str
        table_rows.append(row_data)
    df_table = pd.DataFrame(table_rows)
    if not df_table.empty:
        cols_config = {"バス停名": st.column_config.TextColumn("🚏 バス停", width="medium")}
        if is_all_mode:
            cols_config["行き"] = st.column_config.TextColumn("☀️ 行き", width="small")
            cols_config["帰り"] = st.column_config.TextColumn("🌙 帰り", width="small")
            cols_config["利用生徒"] = st.column_config.TextColumn("👶 全利用生徒", width="large")
        else:
            time_label = "時間"; student_label = "登校生徒" if is_to_school else "下校生徒"
            cols_config[time_label] = st.column_config.TextColumn("⏰ 時間", width="small")
            cols_config[student_label] = st.column_config.TextColumn(f"👶 {student_label}", width="large")
        st.dataframe(df_table, hide_index=True, use_container_width=True, column_config=cols_config)
    else: st.caption("データなし")
    st.markdown("<br>", unsafe_allow_html=True)

if selected_route != "すべて表示":
    st.markdown("---")
    st.subheader(f"👥 {selected_route} 利用生徒名簿 (バス停順)")
    roster_df = students_df[students_df["route"] == selected_route].copy()
    if is_to_school: roster_df = roster_df[roster_df["direction"].str.contains("登校", na=False)]
    elif is_from_school: roster_df = roster_df[roster_df["direction"].str.contains("下校", na=False)]
    route_stops_order = stops_df[stops_df["route"] == selected_route][["stop_name", "sequence"]]
    if not route_stops_order.empty and not roster_df.empty:
        roster_df = pd.merge(roster_df, route_stops_order, on="stop_name", how="left")
        if "sequence" in roster_df.columns: roster_df = roster_df.sort_values(by=["sequence", "name"])
        else: roster_df = roster_df.sort_values(by="name")
    if not roster_df.empty:
        display_cols = ["name", "stop_name", "direction"]
        if "department" in roster_df.columns: display_cols.insert(1, "department")
        roster_display = roster_df[display_cols]
        col_config = {
            "name": st.column_config.TextColumn("👤 生徒名", width="medium"),
            "stop_name": st.column_config.TextColumn("🚏 利用バス停", width="medium"),
            "direction": st.column_config.TextColumn("↔️ 区分", width="small"),
        }
        if "department" in roster_df.columns: col_config["department"] = st.column_config.TextColumn("🎓 学部", width="small")
        st.dataframe(roster_display, hide_index=True, use_container_width=True, column_config=col_config)
    else: st.info("この条件での利用者はいません。")