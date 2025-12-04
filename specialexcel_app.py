import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import json
import os

# Google API 関連のインポート
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.cloud import storage
from googleapiclient.http import MediaIoBaseDownload

# ---------------------------------------------------------
# 🎨 設定 & UIデザイン
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="スクールバス運行マップ (Google Sheets版)")

# 配色パレット
ROUTE_COLORS = {
    "Aコース": "#E69F00", "Bコース": "#56B4E9", "Cコース": "#009E73",
    "Dコース": "#F0E442", "Eコース": "#0072B2", "Fコース": "#D55E00",
    "Gコース": "#CC79A7", "Hコース": "#999999"
}
DEFAULT_COLOR = "#333333"

# ---------------------------------------------------------
# 🔑 Google API 認証 & 設定 (ご提示コードの統合)
# ---------------------------------------------------------

# Secrets から認証情報を取得
# .streamlit/secrets.toml に記述が必要です
try:
    credentials = Credentials.from_service_account_info(
        st.secrets["google_credentials"],
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
    )
except Exception as e:
    st.error("Google認証情報の読み込みに失敗しました。.streamlit/secrets.toml を確認してください。")
    st.stop()

# Google Sheets API クライアントを作成
service = build('sheets', 'v4', credentials=credentials)

# Google Drive API クライアントを作成（ダウンロード時に使用）
drive_service = build('drive', 'v3', credentials=credentials)

# Google Cloud Storage クライアントを作成（必要なら使用）
client = storage.Client(credentials=credentials)

# **スプレッドシートのIDをグローバル変数として定義**
spreadsheet_id = "1s8Y-uQ2GcKxF7Vv5qMWGB9hDE8Zy4fJMbEoGduuXoYE"

# 書き込み用関数（ご提示分）
def write_to_sheets(sheet_name, cell, value):
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!{cell}",
        valueInputOption="RAW",
        body={"values": [[value]]}
    ).execute()

# ---------------------------------------------------------
# 📥 データ読み込み関数 (Google Sheetsから取得)
# ---------------------------------------------------------
@st.cache_data(ttl=600) # 10分間キャッシュしてAPI制限を防ぐ
def load_data_from_sheets():
    """Google Sheetsからデータを読み込みDataFrame化する"""
    try:
        # 1. バス停データの取得 (シート名: bus_stops を想定)
        sheet_stops = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range="bus_stops!A:E").execute()
        rows_stops = sheet_stops.get('values', [])
        
        if len(rows_stops) > 1:
            stops_df = pd.DataFrame(rows_stops[1:], columns=rows_stops[0])
            # 緯度経度を数値に変換
            stops_df["lat"] = pd.to_numeric(stops_df["lat"], errors='coerce')
            stops_df["lng"] = pd.to_numeric(stops_df["lng"], errors='coerce')
        else:
            stops_df = pd.DataFrame()

        # 2. 生徒データの取得 (シート名: students を想定)
        sheet_students = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range="students!A:D").execute()
        rows_students = sheet_students.get('values', [])

        if len(rows_students) > 1:
            students_df = pd.DataFrame(rows_students[1:], columns=rows_students[0])
        else:
            students_df = pd.DataFrame()

        return stops_df, students_df

    except Exception as e:
        st.error(f"スプレッドシートの読み込みエラー: {e}")
        return pd.DataFrame(), pd.DataFrame()

# データのロード実行
stops_df, students_df = load_data_from_sheets()

if stops_df.empty or students_df.empty:
    st.warning("データが空です。スプレッドシートの「bus_stops」と「students」シートを確認してください。")
    st.stop()

# ---------------------------------------------------------
# 🧠 ロジック処理
# ---------------------------------------------------------
def get_students_at_stop(route, stop_name):
    filtered = students_df[
        (students_df["route"] == route) & 
        (students_df["stop_name"] == stop_name)
    ]
    if filtered.empty: return None
    
    to_school = filtered[filtered["direction"] == "登校"]["name"].tolist()
    from_school = filtered[filtered["direction"] == "下校"]["name"].tolist()
    return {"to": to_school, "from": from_school}

# ---------------------------------------------------------
# 📱 サイドバー & 検索機能
# ---------------------------------------------------------
st.sidebar.header("🚌 運行マップ検索")

# 路線選択
route_list = sorted(stops_df["route"].unique()) if not stops_df.empty else []
selected_route = st.sidebar.selectbox("📍 路線を強調表示", ["すべて表示"] + route_list)

# 生徒検索
search_query = st.sidebar.text_input("🔍 生徒名で検索", placeholder="例: 佐藤")
found_student = None

if search_query:
    search_results = students_df[students_df["name"].str.contains(search_query, na=False)]
    if not search_results.empty:
        found_student = search_results.iloc[0]
        st.sidebar.success(f"発見: {found_student['name']} さん ({found_student['route']} - {found_student['stop_name']})")
        selected_route = found_student['route']
    else:
        st.sidebar.warning("該当する生徒が見つかりません")

# ---------------------------------------------------------
# 🗺️ 地図生成
# ---------------------------------------------------------
center_lat = stops_df["lat"].mean()
center_lng = stops_df["lng"].mean()

m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB positron")

# ■ レイヤー1: 路線図（GeoJSONファイルから読み込み）
# ※ Google Sheetsには座標点しか入れないので、綺麗な線はローカルファイルを使用
try:
    with open("data/routes.geojson", "r", encoding="utf-8") as f:
        geojson_data = json.load(f)

    folium.GeoJson(
        geojson_data,
        style_function=lambda feature: {
            'color': ROUTE_COLORS.get(feature['properties'].get('name'), DEFAULT_COLOR),
            'weight': 5 if (selected_route == "すべて表示" or selected_route == feature['properties'].get('name')) else 2,
            'opacity': 0.8 if (selected_route == "すべて表示" or selected_route == feature['properties'].get('name')) else 0.2
        },
        tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=['路線:'])
    ).add_to(m)
except FileNotFoundError:
    st.error("data/routes.geojson が見つかりません。")

# ■ レイヤー2: バス停ピン（Google Sheetsデータ）
for _, row in stops_df.iterrows():
    r_name = row["route"]
    s_name = row["stop_name"]
    
    is_selected_route = (selected_route == "すべて表示") or (selected_route == r_name)
    is_search_target = False
    
    if found_student is not None:
        if found_student["route"] == r_name and found_student["stop_name"] == s_name:
            is_search_target = True

    # スタイル設定
    if is_search_target:
        icon_color = "red"
        radius = 10
        fill_opacity = 1.0
    elif is_selected_route:
        icon_color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR)
        radius = 6
        fill_opacity = 0.9
    else:
        icon_color = "#999999"
        radius = 3
        fill_opacity = 0.5

    # Popup作成
    students_info = get_students_at_stop(r_name, s_name)
    popup_html = f"<b>{s_name}</b> ({r_name})"
    
    if students_info:
        to_str = ", ".join(students_info['to']) if students_info['to'] else "-"
        from_str = ", ".join(students_info['from']) if students_info['from'] else "-"
        popup_html += f"""
        <div style="width:200px; max-height:200px; overflow-y:auto;">
            <hr style="margin:5px 0;">
            <strong style="color:blue;">🚌 登校 ({len(students_info['to'])})</strong>: {to_str}<br>
            <hr style="margin:5px 0;">
            <strong style="color:green;">🏠 下校 ({len(students_info['from'])})</strong>: {from_str}
        </div>
        """
    else:
        popup_html += "<br><span style='font-size:12px;color:gray;'>利用生徒なし</span>"

    folium.CircleMarker(
        location=[row["lat"], row["lng"]],
        radius=radius,
        color="white" if not is_search_target else "red",
        weight=2,
        fill=True,
        fill_color=icon_color,
        fill_opacity=fill_opacity,
        popup=folium.Popup(popup_html, max_width=250)
    ).add_to(m)
    
    if is_search_target:
        folium.Marker(
            location=[row["lat"], row["lng"]],
            icon=folium.Icon(color="red", icon="user", prefix="fa"),
            tooltip="検索ヒット"
        ).add_to(m)

st.title("🚌 スクールバス運行マップ (Live Data)")
st_folium(m, width="100%", height=500, responsive=True)

with st.expander("データの更新について"):
    st.write(f"データは Google Sheets (ID: {spreadsheet_id}) から読み込んでいます。")
    st.write("シート名: `bus_stops` (バス停), `students` (生徒)")