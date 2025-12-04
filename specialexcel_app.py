import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import os

# Google API 関連
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# ---------------------------------------------------------
# 🔐 0. 簡易ログインシステム
# ---------------------------------------------------------
PASSWORD = st.secrets.get("app_password", "bass")

def check_password():
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False
    if not st.session_state["logged_in"]:
        st.title("🔒 スクールバス管理システム")
        input_pass = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン"):
            if input_pass == PASSWORD:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

if not check_password():
    st.stop()

st.set_page_config(layout="wide", page_title="スクールバス運行マップ")

# 配色設定
ROUTE_COLORS = {
    "1便": "#E69F00", "2便": "#56B4E9", "3便": "#009E73",
    "4便": "#F0E442", "5便": "#0072B2", "6便": "#D55E00",
    "7便": "#CC79A7", "8便": "#999999"
}
DEFAULT_COLOR = "#333333"
SPREADSHEET_ID = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"

# ---------------------------------------------------------
# 📥 データ読み込み (time_to / time_from 対応)
# ---------------------------------------------------------
def read_csv_auto_encoding(file_path):
    try:
        return pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        return pd.read_csv(file_path, encoding='cp932')

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

    # バス停 (A:G列まで取得: time_to, time_fromを含む)
    sheet_stops = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="bus_stops!A:G").execute()
    rows_stops = sheet_stops.get('values', [])
    stops_df = pd.DataFrame(rows_stops[1:], columns=rows_stops[0])
    stops_df["lat"] = pd.to_numeric(stops_df["lat"], errors='coerce')
    stops_df["lng"] = pd.to_numeric(stops_df["lng"], errors='coerce')

    # 生徒
    sheet_students = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="students!A:D").execute()
    rows_students = sheet_students.get('values', [])
    students_df = pd.DataFrame(rows_students[1:], columns=rows_students[0])

    return stops_df, students_df

@st.cache_data(ttl=600)
def load_data():
    data_source = "未定義"
    try:
        stops_df, students_df = load_from_google_sheets()
        if stops_df.empty: raise ValueError("Sheet Empty")
        data_source = "Google Sheets"
    except Exception:
        stops_df, students_df, success = load_local_csv()
        if success:
            data_source = "CSVファイル (オフライン)"
        else:
            st.error("データ読み込み失敗。CSVまたはスプレッドシートを確認してください。")
            st.stop()
            
    # カラムの補完（CSVに列が足りない場合のエラー防止）
    if "time_to" not in stops_df.columns: stops_df["time_to"] = "-"
    if "time_from" not in stops_df.columns: stops_df["time_from"] = "-"

    return stops_df, students_df, data_source

stops_df, students_df, current_source = load_data()

# ---------------------------------------------------------
# 📱 サイドバー操作パネル
# ---------------------------------------------------------
st.sidebar.header(f"🚌 運行管理 ({current_source})")

# ★★★ ここが新機能：登下校モード切替 ★★★
mode = st.sidebar.radio(
    "時間帯・モード選択",
    ("☀️ 登校 (行き)", "🌙 下校 (帰り)"),
    index=0
)
is_to_school = (mode == "☀️ 登校 (行き)")

st.sidebar.markdown("---")

route_list = sorted(stops_df["route"].unique()) if not stops_df.empty else []
selected_route = st.sidebar.selectbox("📍 路線選択", ["すべて表示"] + route_list)

# ログアウト
if st.sidebar.button("ログアウト", type="primary"):
    st.session_state["logged_in"] = False
    st.rerun()

# ---------------------------------------------------------
# 🧠 データ処理ロジック (モードによって内容を変える)
# ---------------------------------------------------------
def get_route_details(route_name, is_to_school):
    """
    選択されたモード（登校/下校）に合わせて、時間と生徒リストを抽出する
    """
    route_stops = stops_df[stops_df["route"] == route_name].copy()
    
    if "sequence" in route_stops.columns:
        # 下校の場合は逆順にするか？通常はバス停順序は同じで時間が変わるだけと想定
        # もし逆順路ならここで sort_values(ascending=False) にするロジックも可
        route_stops = route_stops.sort_values("sequence")
        
    result_rows = []
    
    for _, stop in route_stops.iterrows():
        s_name = stop["stop_name"]
        
        # モードに応じた時間を取得
        s_time = stop.get("time_to", "-") if is_to_school else stop.get("time_from", "-")
        
        # そのバス停の生徒を探す
        students_here = students_df[
            (students_df["route"] == route_name) & 
            (students_df["stop_name"] == s_name)
        ]
        
        # モードに応じて対象生徒をフィルタリング
        # 登校モードなら「登校」生徒を表示、下校モードなら「下校」生徒を表示
        target_direction = "登校" if is_to_school else "下校"
        
        target_students = students_here[students_here["direction"] == target_direction]["name"].tolist()
        student_str = "、".join(target_students) if target_students else ""
        
        # 行を追加
        row_data = {
            "時間": s_time,
            "バス停名": s_name,
            "生徒リスト": student_str
        }
        result_rows.append(row_data)
        
    return pd.DataFrame(result_rows)

# ---------------------------------------------------------
# 🗺️ 地図生成
# ---------------------------------------------------------
if not stops_df.empty:
    center_lat = stops_df["lat"].mean()
    center_lng = stops_df["lng"].mean()
else:
    center_lat, center_lng = 35.6895, 139.6917

m = folium.Map(location=[center_lat, center_lng], zoom_start=14, tiles="CartoDB positron")

# 路線図 (GeoJSON)
geojson_path = "data/routes.geojson"
if os.path.exists(geojson_path):
    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        
        if "features" in geojson_data:
            for feature in geojson_data["features"]:
                if "properties" not in feature: feature["properties"] = {}
                if "name" not in feature["properties"]: feature["properties"]["name"] = "不明"

        folium.GeoJson(
            geojson_data,
            style_function=lambda feature: {
                'color': ROUTE_COLORS.get(feature['properties']['name'], DEFAULT_COLOR),
                'weight': 6 if (selected_route == "すべて表示" or selected_route == feature['properties']['name']) else 2,
                'opacity': 0.9 if (selected_route == "すべて表示" or selected_route == feature['properties']['name']) else 0.2
            },
            tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=['便名:'])
        ).add_to(m)
    except Exception:
        pass

# バス停ピン
for _, row in stops_df.iterrows():
    r_name = row["route"]
    s_name = row["stop_name"]
    
    # モードに応じた時間をポップアップに表示
    s_time = row.get("time_to", "-") if is_to_school else row.get("time_from", "-")
    time_label = "登校" if is_to_school else "下校"

    is_active = (selected_route == "すべて表示") or (selected_route == r_name)
    
    if is_active:
        color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR)
        radius = 6
        opacity = 0.9
    else:
        color = "#999999"
        radius = 3
        opacity = 0.4

    folium.CircleMarker(
        location=[row["lat"], row["lng"]],
        radius=radius,
        color="white",
        weight=1,
        fill=True,
        fill_color=color,
        fill_opacity=opacity,
        popup=f"<b>{s_name}</b><br>{time_label}: {s_time}<br>{r_name}"
    ).add_to(m)

# タイトル表示 (モードによって色を変える演出)
title_color = "blue" if is_to_school else "orange"
st.markdown(f"<h1 style='color:{title_color};'>🚌 スクールバス運行管理 ({mode})</h1>", unsafe_allow_html=True)

# 地図表示 (PC用に縦長)
st_folium(m, use_container_width=True, height=750)

# ---------------------------------------------------------
# 📋 詳細リスト表示 (モード連動)
# ---------------------------------------------------------
st.markdown("---")

if selected_route != "すべて表示":
    st.subheader(f"📄 {selected_route} - {mode} 予定表")
    
    # モード情報を渡してデータを取得
    details_df = get_route_details(selected_route, is_to_school)
    
    if not details_df.empty:
        # カラム名の動的設定
        student_col_name = "乗車する生徒 (登校)" if is_to_school else "降車する生徒 (下校)"
        
        st.dataframe(
            details_df, 
            hide_index=True, 
            use_container_width=True,
            column_config={
                "時間": st.column_config.TextColumn("予定時刻", width="small"),
                "バス停名": st.column_config.TextColumn("バス停名", width="medium"),
                "生徒リスト": st.column_config.TextColumn(student_col_name, width="large"),
            }
        )
    else:
        st.info("この条件での詳細データがありません。")

else:
    st.info("👆 地図上のメニュー、またはサイドバーから「路線」を選択すると、時刻表と生徒リストが表示されます。")