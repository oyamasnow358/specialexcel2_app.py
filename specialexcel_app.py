import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import os

# Google API 関連
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# =========================================================
# 🔐 0. 簡易ログイン & 設定
# =========================================================
PASSWORD = st.secrets.get("app_password", "school1234")
SPREADSHEET_ID = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"

# 🎨 デザイン・配色設定
# 12便まで対応 (GeoJSONのnameプロパティとCSVのroute列と一致させること)
ROUTE_COLORS = {
    "1便": "#E69F00",  # オレンジ
    "2便": "#56B4E9",  # スカイブルー
    "3便": "#009E73",  # 青緑
    "4便": "#F0E442",  # 黄色
    "5便": "#0072B2",  # 青
    "6便": "#D55E00",  # 朱色
    "7便": "#CC79A7",  # 赤紫
    "8便": "#999999",  # グレー
    "9便": "#882255",  # ワインレッド
    "10便": "#AA4499", # 紫
    "11便": "#332288", # 紺
    "12便": "#DDCC77"  # 薄茶
}
DEFAULT_COLOR = "#333333" # 定義外の路線は黒

def check_password():
    """ログイン認証画面"""
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if not st.session_state["logged_in"]:
        st.set_page_config(page_title="ログイン - スクールバス管理", layout="centered")
        st.markdown("## 🔒 スクールバス運行管理システム")
        input_pass = st.text_input("パスワードを入力してください", type="password")
        if st.button("ログイン", type="primary"):
            if input_pass == PASSWORD:
                st.session_state["logged_in"] = True
                st.rerun()
            else:
                st.error("パスワードが違います")
        return False
    return True

# ログインチェック
if not check_password():
    st.stop()

# =========================================================
# 🏗️ アプリ本体設定
# =========================================================
st.set_page_config(layout="wide", page_title="スクールバス運行マップ (Pro)")

# ---------------------------------------------------------
# 📥 データ読み込みロジック (API -> CSVフォールバック)
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

    # バス停 (A:G列 Time_to, Time_from含む)
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
        data_source = "Google Sheets (Live)"
    except Exception:
        stops_df, students_df, success = load_local_csv()
        if success:
            data_source = "CSV (Offline)"
        else:
            st.error("❌ データ読み込み失敗。管理者へ連絡してください。")
            st.stop()
            
    # データ補正
    if "time_to" not in stops_df.columns: stops_df["time_to"] = "-"
    if "time_from" not in stops_df.columns: stops_df["time_from"] = "-"
    
    return stops_df, students_df, data_source

stops_df, students_df, current_source = load_data()

# ---------------------------------------------------------
# 🧠 生徒検索 & モード管理ロジック
# ---------------------------------------------------------
st.sidebar.title("🚌 運行管理メニュー")

# 1. 登下校モード切替
mode = st.sidebar.radio(
    "時間帯・モード",
    ("☀️ 登校 (行き)", "🌙 下校 (帰り)"),
    horizontal=True
)
is_to_school = (mode == "☀️ 登校 (行き)")

# 2. 生徒検索機能
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 生徒検索")
search_query = st.sidebar.text_input("生徒名を入力", placeholder="例: 佐藤")

# 検索ロジック
found_student = None
search_hit_route = None

if search_query:
    # 部分一致で検索
    search_results = students_df[students_df["name"].str.contains(search_query, na=False)]
    if not search_results.empty:
        found_student = search_results.iloc[0] # 最初のヒットを取得
        search_hit_route = found_student["route"]
        
        # 検索結果をサイドバーに表示
        st.sidebar.success(f"発見: **{found_student['name']}** さん")
        st.sidebar.info(f"📍 {found_student['route']} - {found_student['stop_name']}")
        st.sidebar.caption(f"利用区分: {found_student['direction']}")
    else:
        st.sidebar.warning("該当する生徒が見つかりません")

# 3. 路線選択 (検索ヒット時は自動でその路線を選択状態にする)
st.sidebar.markdown("---")
route_options = ["すべて表示"] + sorted(stops_df["route"].unique().tolist())

# デフォルトの選択肢を決める
default_index = 0
if search_hit_route and search_hit_route in route_options:
    default_index = route_options.index(search_hit_route)

selected_route = st.sidebar.selectbox("📍 表示路線の絞り込み", route_options, index=default_index)

# ステータス表示
st.sidebar.markdown("---")
st.sidebar.caption(f"Data Source: {current_source}")
if st.sidebar.button("ログアウト"):
    st.session_state["logged_in"] = False
    st.rerun()

# ---------------------------------------------------------
# 🗺️ メイン画面構成 (UIデザイン)
# ---------------------------------------------------------
# タイトルエリアの装飾
header_color = "blue" if is_to_school else "orange"
header_icon = "🏫" if is_to_school else "🏠"
st.markdown(f"""
    <div style="border-left: 5px solid {header_color}; padding-left: 15px; margin-bottom: 20px;">
        <h1 style='margin:0; font-size: 28px;'>{header_icon} スクールバス運行マップ <small style="color:gray; font-size:16px;">({mode})</small></h1>
    </div>
""", unsafe_allow_html=True)

# 地図の中心決定
if found_student is not None:
    # 検索ヒット時はそのバス停を中心に
    target_stop = stops_df[
        (stops_df["route"] == found_student["route"]) & 
        (stops_df["stop_name"] == found_student["stop_name"])
    ]
    if not target_stop.empty:
        center_lat = target_stop.iloc[0]["lat"]
        center_lng = target_stop.iloc[0]["lng"]
        zoom_start = 16 # ズームアップ
    else:
        center_lat, center_lng = stops_df["lat"].mean(), stops_df["lng"].mean()
        zoom_start = 14
else:
    center_lat = stops_df["lat"].mean() if not stops_df.empty else 35.6895
    center_lng = stops_df["lng"].mean() if not stops_df.empty else 139.6917
    zoom_start = 14

# 地図作成
m = folium.Map(location=[center_lat, center_lng], zoom_start=zoom_start, tiles="CartoDB positron")

# ---------------------------------------------------------
# 📍 レイヤー1: 路線図 (GeoJSON) - 12便対応・色分け
# ---------------------------------------------------------
geojson_path = "data/routes.geojson"
if os.path.exists(geojson_path):
    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        
        # GeoJSONの不備を自動補正 (ここが色分け復活の鍵)
        if "features" in geojson_data:
            for feature in geojson_data["features"]:
                if "properties" not in feature:
                    feature["properties"] = {}
                
                # nameがない、または空の場合の安全策
                if "name" not in feature["properties"]:
                    feature["properties"]["name"] = "不明"

        # スタイル関数
        def style_function(feature):
            # プロパティから路線名を取得（エラー回避のため安全に取得）
            props = feature.get('properties', {})
            r_name = props.get('name', '不明')
            
            # 検索ヒットまたは選択中の路線以外は薄くする
            is_active = (selected_route == "すべて表示") or (selected_route == r_name)
            
            # 色の決定（辞書にない場合はデフォルト色）
            line_color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR)
            
            return {
                'color': line_color,
                'weight': 6 if is_active else 2,
                'opacity': 0.9 if is_active else 0.2
            }

        folium.GeoJson(
            geojson_data,
            style_function=style_function,
            tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=['便名:'])
        ).add_to(m)
    except Exception as e:
        st.error(f"路線データ読み込みエラー: {e}")

# ---------------------------------------------------------
# 📍 レイヤー2: バス停ピン - 12便対応・検索強調
# ---------------------------------------------------------
for _, row in stops_df.iterrows():
    r_name = row["route"]
    s_name = row["stop_name"]
    
    # 時間の取得
    s_time = row.get("time_to", "-") if is_to_school else row.get("time_from", "-")
    
    # 表示フィルタ
    is_route_selected = (selected_route == "すべて表示") or (selected_route == r_name)
    
    # 検索対象のバス停かどうか
    is_search_target = False
    if found_student is not None:
        if found_student["route"] == r_name and found_student["stop_name"] == s_name:
            is_search_target = True

    # デザイン決定
    if is_search_target:
        # 検索ヒット：赤色で大きく、枠線を太く
        icon_color = "#FF0000" # 赤
        radius = 12
        line_weight = 3
        fill_opacity = 1.0
        z_index_offset = 1000 # 最前面へ
    elif is_route_selected:
        # 選択路線：路線の色
        icon_color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR)
        radius = 7
        line_weight = 1
        fill_opacity = 0.9
        z_index_offset = 0
    else:
        # 非選択：グレーで小さく
        icon_color = "#CCCCCC"
        radius = 3
        line_weight = 0
        fill_opacity = 0.4
        z_index_offset = -1

    # ポップアップ内容
    popup_html = f"""
    <div style="font-family:sans-serif; width:180px;">
        <h4 style="margin:0; color:{ROUTE_COLORS.get(r_name, 'black')};">{s_name}</h4>
        <div style="background-color:#f0f0f0; padding:5px; margin:5px 0; border-radius:4px;">
            <b>{mode}</b><br>
            <span style="font-size:16px; font-weight:bold;">⏰ {s_time}</span>
        </div>
        <small>{r_name}</small>
    </div>
    """

    folium.CircleMarker(
        location=[row["lat"], row["lng"]],
        radius=radius,
        color="white" if is_search_target else icon_color, # 枠線
        weight=line_weight,
        fill=True,
        fill_color=icon_color,
        fill_opacity=fill_opacity,
        popup=folium.Popup(popup_html, max_width=200),
        z_index_offset=z_index_offset
    ).add_to(m)

    # 検索ヒット時は追加で目立つアイコンを置く
    if is_search_target:
        folium.Marker(
            location=[row["lat"], row["lng"]],
            icon=folium.Icon(color="red", icon="user", prefix="fa"),
            tooltip=f"{found_student['name']} さんの利用バス停"
        ).add_to(m)

# 地図描画 (PC用に見やすく縦長固定)
st_folium(m, use_container_width=True, height=750)

# ---------------------------------------------------------
# 📋 詳細リスト表示 (全路線対応版)
# ---------------------------------------------------------
st.markdown("---")

# 表示する路線を決定（すべて表示なら全路線、そうでなければ選択路線のみ）
if selected_route == "すべて表示":
    target_routes = sorted(stops_df["route"].unique().tolist())
    st.subheader(f"📄 全路線の運行予定 ({mode})")
else:
    target_routes = [selected_route]
    st.subheader(f"📄 {selected_route} 詳細スケジュール")

# 全データの結合処理
all_rows = []

for r_name in target_routes:
    # その路線のバス停を抽出
    route_stops = stops_df[stops_df["route"] == r_name].copy()
    if "sequence" in route_stops.columns:
        route_stops = route_stops.sort_values("sequence")
        
    for _, stop in route_stops.iterrows():
        s_name = stop["stop_name"]
        s_time = stop.get("time_to", "-") if is_to_school else stop.get("time_from", "-")
        
        # 生徒抽出
        target_direction = "登校" if is_to_school else "下校"
        
        students_here = students_df[
            (students_df["route"] == r_name) & 
            (students_df["stop_name"] == s_name) &
            (students_df["direction"] == target_direction)
        ]["name"].tolist()
        
        # ★検索ハイライト処理★
        if found_student is not None and found_student["name"] in students_here:
            display_stop_name = f"🔴 {s_name} (検索ヒット)"
            # リスト内でもその生徒名を強調
            students_here = [f"**{s}**" if s == found_student["name"] else s for s in students_here]
        else:
            display_stop_name = s_name

        all_rows.append({
            "路線名": r_name,
            "予定時刻": s_time,
            "バス停名": display_stop_name,
            f"{target_direction}生徒 ({len(students_here)}名)": "、".join(students_here)
        })

# データフレーム作成と表示
df_display = pd.DataFrame(all_rows)

if not df_display.empty:
    # 路線名でソートして見やすくする
    # df_display = df_display.sort_values(["路線名", "予定時刻"]) # 必要に応じてソート
    
    st.dataframe(
        df_display, 
        hide_index=True, 
        use_container_width=True,
        column_config={
            "路線名": st.column_config.TextColumn("🚌 便名", width="small"),
            "予定時刻": st.column_config.TextColumn("⏰ 時間", width="small"),
            "バス停名": st.column_config.TextColumn("🚏 バス停", width="medium"),
        }
    )
else:
    st.info("データがありません")