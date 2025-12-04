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

# 🎨 配色設定
ROUTE_COLORS = {
    "1便": "#E69F00", "2便": "#56B4E9", "3便": "#009E73", "4便": "#F0E442",
    "5便": "#0072B2", "6便": "#D55E00", "7便": "#CC79A7", "8便": "#999999",
    "9便": "#882255", "10便": "#AA4499", "11便": "#332288", "12便": "#DDCC77",
    "Aコース": "#E69F00", "Bコース": "#56B4E9", "Cコース": "#009E73", "Dコース": "#F0E442",
    "Eコース": "#0072B2", "Fコース": "#D55E00", "Gコース": "#CC79A7", "Hコース": "#999999",
    "Iコース": "#882255", "Jコース": "#AA4499", "Kコース": "#332288", "Lコース": "#DDCC77"
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
# 📥 データ読み込み (頑丈なクリーニング処理)
# ---------------------------------------------------------
def clean_df(df):
    """全データを文字列化して空白除去"""
    if df.empty: return df
    # オブジェクト型(文字列)のカラムをきれいにする
    for col in df.select_dtypes(include=['object']).columns:
        df[col] = df[col].astype(str).str.strip()
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

    sheet_stops = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="bus_stops!A:G").execute()
    rows_stops = sheet_stops.get('values', [])
    stops_df = pd.DataFrame(rows_stops[1:], columns=rows_stops[0]) if rows_stops else pd.DataFrame()
    
    sheet_students = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range="students!A:D").execute()
    rows_students = sheet_students.get('values', [])
    students_df = pd.DataFrame(rows_students[1:], columns=rows_students[0]) if rows_students else pd.DataFrame()

    stops_df = clean_df(stops_df)
    students_df = clean_df(students_df)
    
    stops_df["lat"] = pd.to_numeric(stops_df["lat"], errors='coerce')
    stops_df["lng"] = pd.to_numeric(stops_df["lng"], errors='coerce')

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
            st.error("❌ データ読み込み失敗")
            st.stop()
    
    # 必須カラムの補完
    for col in ["time_to", "time_from"]:
        if col not in stops_df.columns: stops_df[col] = "-"
    if "direction" not in students_df.columns: students_df["direction"] = "-"
    
    return stops_df, students_df, data_source

stops_df, students_df, current_source = load_data()

# ---------------------------------------------------------
# 🧠 UI & ロジック
# ---------------------------------------------------------
st.sidebar.title("🚌 運行管理メニュー")

# 1. モード選択
mode_selection = st.sidebar.radio(
    "表示モード",
    ("☀️ 登校 (行き)", "🌙 下校 (帰り)", "🔄 すべて (全体)"),
    horizontal=False
)
is_to_school = (mode_selection == "☀️ 登校 (行き)")
is_from_school = (mode_selection == "🌙 下校 (帰り)")
is_all_mode = (mode_selection == "🔄 すべて (全体)")

target_student_info = None

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 生徒検索・指定")

# A. 名前検索
search_query = st.sidebar.text_input("名前検索", placeholder="名前を入力")
search_candidates = pd.DataFrame()

if search_query:
    # 検索処理 (大文字小文字無視なしでもOKなように一応astype(str))
    search_candidates = students_df[students_df["name"].str.contains(search_query, na=False)]

# B. 検索結果ハンドリング (バグ修正版: インデックスで管理)
if not search_candidates.empty:
    if len(search_candidates) == 1:
        target_student_info = search_candidates.iloc[0]
        st.sidebar.success(f"発見: {target_student_info['name']}")
    else:
        st.sidebar.warning(f"{len(search_candidates)}名 ヒットしました")
        # インデックスを使って一意に特定する
        candidate_indices = search_candidates.index.tolist()
        
        # 表示用関数
        def format_candidate(idx):
            row = search_candidates.loc[idx]
            return f"{row['name']} ({row['route']} - {row['stop_name']})"
        
        selected_idx = st.sidebar.selectbox("表示する生徒を選択", candidate_indices, format_func=format_candidate)
        target_student_info = search_candidates.loc[selected_idx]

elif search_query:
    st.sidebar.error("該当者なし")

# C. 路線選択
st.sidebar.markdown("---")
unique_routes = sorted(stops_df["route"].unique().tolist())
route_options = ["すべて表示"] + unique_routes

default_ix = 0
if target_student_info is not None:
    if target_student_info["route"] in route_options:
        default_ix = route_options.index(target_student_info["route"])

selected_route = st.sidebar.selectbox("📍 路線選択", route_options, index=default_ix)

# D. 路線内の生徒ドロップダウン
if selected_route != "すべて表示":
    students_in_route = students_df[students_df["route"] == selected_route].sort_values("name")
    
    # 選択肢作成 (インデックス管理で安全に)
    student_indices = students_in_route.index.tolist()
    
    # デフォルト選択位置の決定
    default_sel_idx = None
    if target_student_info is not None:
        if target_student_info.name in student_indices: # .name はDataFrameのindex値
            default_sel_idx = student_indices.index(target_student_info.name)

    # セレクトボックス (Noneを選択肢に加えるための工夫)
    options = [None] + student_indices
    def format_student_opt(idx):
        if idx is None: return "(選択なし)"
        return students_in_route.loc[idx, "name"]

    # index引数はintが必要なので調整
    box_idx = 0
    if default_sel_idx is not None:
        box_idx = default_sel_idx + 1 # Noneが先頭にあるため

    selected_student_idx = st.sidebar.selectbox(
        "👶 生徒詳細へジャンプ", 
        options, 
        format_func=format_student_opt, 
        index=box_idx
    )
    
    if selected_student_idx is not None:
        target_student_info = students_in_route.loc[selected_student_idx]

# ログアウト
st.sidebar.markdown("---")
st.sidebar.caption(f"Source: {current_source}")
if st.sidebar.button("ログアウト"):
    st.session_state["logged_in"] = False
    st.rerun()

# =========================================================
# 📝 メインエリア
# =========================================================

if is_to_school:
    header_color, header_icon, header_text = "blue", "🏫", "登校モード"
elif is_from_school:
    header_color, header_icon, header_text = "orange", "🏠", "下校モード"
else:
    header_color, header_icon, header_text = "green", "🔄", "全体表示モード"

st.markdown(f"""
    <div style="border-left: 5px solid {header_color}; padding-left: 15px; margin-bottom: 10px;">
        <h1 style='margin:0; font-size: 28px;'>{header_icon} 運行管理 <small style="color:gray;">({header_text})</small></h1>
    </div>
""", unsafe_allow_html=True)

# 生徒詳細カード
if target_student_info is not None:
    s_stop_info = stops_df[
        (stops_df["route"] == target_student_info["route"]) & 
        (stops_df["stop_name"] == target_student_info["stop_name"])
    ]
    time_to = s_stop_info.iloc[0].get("time_to", "-") if not s_stop_info.empty else "-"
    time_from = s_stop_info.iloc[0].get("time_from", "-") if not s_stop_info.empty else "-"

    st.info(f"""
    **👤 生徒情報: {target_student_info['name']} さん**  
    📍 路線: **{target_student_info['route']}** / バス停: **{target_student_info['stop_name']}** / 区分: {target_student_info['direction']}
    
    | ☀️ 行き (登校) | 🌙 帰り (下校) |
    |---|---|
    | ⏰ **{time_to}** | ⏰ **{time_from}** |
    """)

# 地図設定
if target_student_info is not None:
    target_stop = stops_df[
        (stops_df["route"] == target_student_info["route"]) & 
        (stops_df["stop_name"] == target_student_info["stop_name"])
    ]
    if not target_stop.empty:
        center_lat, center_lng = target_stop.iloc[0]["lat"], target_stop.iloc[0]["lng"]
        zoom_start = 16
    else:
        center_lat, center_lng = stops_df["lat"].mean(), stops_df["lng"].mean()
        zoom_start = 14
else:
    center_lat = stops_df["lat"].mean() if not stops_df.empty else 35.6895
    center_lng = stops_df["lng"].mean() if not stops_df.empty else 139.6917
    zoom_start = 14

m = folium.Map(location=[center_lat, center_lng], zoom_start=zoom_start, tiles="CartoDB positron")

# 📍 路線図 (GeoJSON)
geojson_path = "data/routes.geojson"
if os.path.exists(geojson_path):
    try:
        with open(geojson_path, "r", encoding="utf-8") as f:
            geojson_data = json.load(f)
        if "features" in geojson_data:
            for feature in geojson_data["features"]:
                if "properties" not in feature: feature["properties"] = {}
                if "name" not in feature["properties"]: feature["properties"]["name"] = "不明"

        def style_function(feature):
            r_name = feature.get('properties', {}).get('name', '不明')
            is_active = (selected_route == "すべて表示") or (selected_route == r_name)
            return {
                'color': ROUTE_COLORS.get(r_name, DEFAULT_COLOR),
                'weight': 6 if is_active else 3,
                'opacity': 0.9 if is_active else 0.4
            }
        folium.GeoJson(geojson_data, style_function=style_function).add_to(m)
    except Exception: pass

# 📍 バス停ピン
for _, row in stops_df.iterrows():
    r_name = row["route"]
    s_name = row["stop_name"]
    
    is_route_selected = (selected_route == "すべて表示") or (selected_route == r_name)
    is_target_stop = False
    if target_student_info is not None:
        if target_student_info["route"] == r_name and target_student_info["stop_name"] == s_name:
            is_target_stop = True

    if is_target_stop:
        icon_color = "#FF0000"; radius = 12; line_weight = 3; fill_opacity = 1.0; z_index = 1000
    elif is_route_selected:
        icon_color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR); radius = 7; line_weight = 1; fill_opacity = 0.9; z_index = 0
    else:
        icon_color = "#CCCCCC"; radius = 3; line_weight = 0; fill_opacity = 0.4; z_index = -1

    t_display = f"行き:{row.get('time_to','-')} / 帰り:{row.get('time_from','-')}"

    popup_html = f"""
    <div style="font-family:sans-serif; width:200px;">
        <h4 style="margin:0; color:{ROUTE_COLORS.get(r_name, 'black')};">{s_name}</h4>
        <div style="background-color:#f0f0f0; padding:5px; margin:5px 0; border-radius:4px;">
            <small>{t_display}</small>
        </div>
        <small>{r_name}</small>
    </div>
    """
    folium.CircleMarker(
        location=[row["lat"], row["lng"]], radius=radius,
        color="white" if is_target_stop else icon_color, weight=line_weight,
        fill=True, fill_color=icon_color, fill_opacity=fill_opacity,
        popup=folium.Popup(popup_html, max_width=250), z_index_offset=z_index
    ).add_to(m)
    
    if is_target_stop:
        folium.Marker(
            location=[row["lat"], row["lng"]],
            icon=folium.Icon(color="red", icon="user", prefix="fa"),
            tooltip=f"{target_student_info['name']} さん"
        ).add_to(m)

st_folium(m, use_container_width=True, height=750)

# =========================================================
# 📋 詳細リスト
# =========================================================
st.markdown("---")

if selected_route == "すべて表示":
    target_routes = sorted(stops_df["route"].unique().tolist())
else:
    target_routes = [selected_route]

for r_name in target_routes:
    r_color = ROUTE_COLORS.get(r_name, DEFAULT_COLOR)
    st.markdown(f"### <span style='color:{r_color};'>■</span> {r_name}", unsafe_allow_html=True)
    
    route_stops = stops_df[stops_df["route"] == r_name].copy()
    if "sequence" in route_stops.columns:
        route_stops = route_stops.sort_values("sequence")
    
    table_rows = []
    
    for _, stop in route_stops.iterrows():
        s_name = stop["stop_name"]
        
        # 生徒抽出 (安全なロジックに変更)
        # そのバス停の生徒データだけを抽出
        students_at_stop = students_df[
            (students_df["route"] == r_name) & 
            (students_df["stop_name"] == s_name)
        ]
        
        students_list_str = []
        
        # モード別フィルタリング
        # ★ここが重要：AttributeErrorを防ぐため、pandasのapplyを使わずPythonリスト処理を行う
        if is_to_school:
            # 登校を含む生徒
            filtered = students_at_stop[students_at_stop["direction"].str.contains("登校", na=False)]
            students_list_str = filtered["name"].tolist()
        elif is_from_school:
            # 下校を含む生徒
            filtered = students_at_stop[students_at_stop["direction"].str.contains("下校", na=False)]
            students_list_str = filtered["name"].tolist()
        else:
            # すべて: 名前(方向) の形式で作る
            for _, st_row in students_at_stop.iterrows():
                # 方向の1文字目を取得 (登校 -> 登, 下校 -> 下)
                d_raw = str(st_row["direction"])
                d_label = d_raw[0] if len(d_raw) > 0 else "?"
                students_list_str.append(f"{st_row['name']}({d_label})")

        # ハイライト処理
        display_stop = s_name
        if target_student_info is not None and target_student_info["stop_name"] == s_name and target_student_info["route"] == r_name:
            display_stop = f"🔴 {s_name}"
            # 名前リストの中でも強調
            target_name = target_student_info["name"]
            # 部分一致で強調 (例: "佐藤(登)"の中に "佐藤" があれば太字)
            students_list_str = [f"**{s}**" if target_name in s else s for s in students_list_str]

        final_student_str = "、".join(students_list_str)
        
        row_data = {"バス停名": display_stop}
        
        if is_all_mode:
            row_data["行き"] = stop.get("time_to", "-")
            row_data["帰り"] = stop.get("time_from", "-")
            row_data["利用生徒"] = final_student_str
        elif is_to_school:
            row_data["時間"] = stop.get("time_to", "-")
            row_data["登校生徒"] = final_student_str
        else:
            row_data["時間"] = stop.get("time_from", "-")
            row_data["下校生徒"] = final_student_str
            
        table_rows.append(row_data)
    
    df_table = pd.DataFrame(table_rows)
    
    if not df_table.empty:
        # カラム設定
        cols_config = {
            "バス停名": st.column_config.TextColumn("🚏 バス停", width="medium"),
        }
        if is_all_mode:
            cols_config["行き"] = st.column_config.TextColumn("☀️ 行き", width="small")
            cols_config["帰り"] = st.column_config.TextColumn("🌙 帰り", width="small")
            cols_config["利用生徒"] = st.column_config.TextColumn("👶 全生徒", width="large")
        else:
            time_label = "時間"
            student_label = "登校生徒" if is_to_school else "下校生徒"
            cols_config[time_label] = st.column_config.TextColumn("⏰ 時間", width="small")
            cols_config[student_label] = st.column_config.TextColumn(f"👶 {student_label}", width="large")

        st.dataframe(
            df_table, hide_index=True, use_container_width=True, column_config=cols_config
        )
    else:
        st.caption("データなし")
    st.markdown("<br>", unsafe_allow_html=True)