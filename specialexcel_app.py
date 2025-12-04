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
# 🎨 設定 & UIデザイン
# ---------------------------------------------------------
st.set_page_config(layout="wide", page_title="スクールバス運行マップ")

# 配色パレット
ROUTE_COLORS = {
    "Aコース": "#E69F00", "Bコース": "#56B4E9", "Cコース": "#009E73",
    "Dコース": "#F0E442", "Eコース": "#0072B2", "Fコース": "#D55E00",
    "Gコース": "#CC79A7", "Hコース": "#999999"
}
DEFAULT_COLOR = "#333333"
SPREADSHEET_ID = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"

# ---------------------------------------------------------
# 📥 データ読み込みロジック (API -> 失敗ならCSV)
# ---------------------------------------------------------

def read_csv_auto_encoding(file_path):
    """CSV読み込み：UTF-8失敗時にShift-JISを試す"""
    try:
        return pd.read_csv(file_path, encoding='utf-8')
    except UnicodeDecodeError:
        return pd.read_csv(file_path, encoding='cp932')

def load_local_csv():
    """ローカルCSV読み込み"""
    try:
        s_df = read_csv_auto_encoding("data/bus_stops.csv")
        st_df = read_csv_auto_encoding("data/students.csv")
        return s_df, st_df, True
    except FileNotFoundError:
        return pd.DataFrame(), pd.DataFrame(), False

def load_from_google_sheets():
    """Google Sheets読み込み"""
    if "google_credentials" not in st.secrets:
        raise ValueError("Secretsなし")

    creds_dict = dict(st.secrets["google_credentials"])
    if "private_key" in creds_dict:
        creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

    credentials = Credentials.from_service_account_info(
        creds_dict,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    
    service = build('sheets', 'v4', credentials=credentials)

    # バス停
    sheet_stops = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="bus_stops!A:E").execute()
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
    """データ読み込みメイン処理"""
    data_source = "未定義"
    try:
        stops_df, students_df = load_from_google_sheets()
        if stops_df.empty: raise ValueError("Sheet Empty")
        data_source = "Google Sheets (オンライン)"
    except Exception as e:
        print(f"API Error: {e}") 
        stops_df, students_df, success = load_local_csv()
        if success:
            data_source = "CSVファイル (オフライン)"
        else:
            st.error("データ読み込み失敗。dataフォルダのCSVを確認してください。")
            st.stop()
    return stops_df, students_df, data_source

stops_df, students_df, current_source = load_data()

# ---------------------------------------------------------
# 🧠 ロジック
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
# 📱 サイドバー & 検索
# ---------------------------------------------------------
st.sidebar.header("🚌 運行マップ検索")
if "CSV" in current_source:
    st.sidebar.warning(f"⚠️ {current_source}")
else:
    st.sidebar.success(f"🟢 {current_source}")

route_list = sorted(stops_df["route"].unique()) if not stops_df.empty else []
selected_route = st.sidebar.selectbox("📍 路線を強調表示", ["すべて表示"] + route_list)

search_query = st.sidebar.text_input("🔍 生徒名で検索", placeholder="例: 佐藤")
found_student = None

if search_query:
    search_results = students_df[students_df["name"].str.contains(search_query, na=False)]
    if not search_results.empty:
        found_student = search_results.iloc[0]
        st.sidebar.success(f"発見: {found_student['name']} さん ({found_student['route']} - {found_student['stop_name']})")
        selected_route = found_student['route']
    else:
        st.sidebar.warning("該当生徒なし")

# ---------------------------------------------------------
# 🗺️ 地図生成
# ---------------------------------------------------------
if not stops_df.empty:
    center_lat = stops_df["lat"].mean()
    center_lng = stops_df["lng"].mean()
else:
    center_lat, center_lng = 35.6895, 139.6917

m = folium.Map(location=[center_lat, center_lng], zoom_start=13, tiles="CartoDB positron")

# ---------------------------------------------------------
# ■ レイヤー1: 路線図（GeoJSON）診断モード
# ---------------------------------------------------------
geojson_path = "data/routes.geojson"

# 1. ファイルが存在するかチェック
if not os.path.exists(geojson_path):
    st.error(f"⚠️ ファイルが見つかりません: {geojson_path}")
    st.info("dataフォルダの中に routes.geojson という名前で保存されていますか？")
else:
    try:
        # 2. JSONとして正しく読み込めるかチェック
        with open(geojson_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        
        # 3. データの個数チェック
        feature_count = len(geojson_data.get("features", []))
        st.success(f"✅ 路線データ読み込み成功: {feature_count} 本の路線が見つかりました")

        # 地図に描画
        # 地図に描画
        folium.GeoJson(
            geojson_data,
            style_function=lambda feature: {
                # ↓ ここを修正: .get() を使ってエラーを防ぐ
                'color': ROUTE_COLORS.get(feature.get('properties', {}).get('name'), DEFAULT_COLOR),
                'weight': 5 if (selected_route == "すべて表示" or selected_route == feature.get('properties', {}).get('name')) else 2,
                'opacity': 0.8 if (selected_route == "すべて表示" or selected_route == feature.get('properties', {}).get('name')) else 0.2
            },
            # Tooltipもエラー回避のため、nameがない場合は "-" を表示させる設定等はできないが、
            # データ不備でも落ちないようにシンプルな設定にする
            tooltip=folium.GeoJsonTooltip(fields=['name'], aliases=['路線:'])
        ).add_to(m)

    except json.JSONDecodeError as e:
        st.error(f"❌ JSONファイルの記述ミスがあります: {e}")
        st.warning("カンマ(,)の忘れや、カッコの閉じ忘れがないか確認してください。")
    except Exception as e:
        st.error(f"❌ 予期せぬエラー: {e}")

# バス停ピン
for _, row in stops_df.iterrows():
    r_name = row["route"]
    s_name = row["stop_name"]
    is_selected_route = (selected_route == "すべて表示") or (selected_route == r_name)
    is_search_target = False
    
    if found_student is not None:
        if found_student["route"] == r_name and found_student["stop_name"] == s_name:
            is_search_target = True

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

st.title("🚌 スクールバス運行マップ")

# 修正箇所: use_container_width=True を使用
st_folium(m, use_container_width=True, height=500)