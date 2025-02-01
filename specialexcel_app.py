import streamlit as st
import os
from google.cloud import storage
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials

# Secrets から認証情報を取得
credentials = Credentials.from_service_account_info(
    st.secrets["google_credentials"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)

# Google Sheets API クライアントを作成
sheets_service = build('sheets', 'v4', credentials=credentials)

# Google Drive API クライアントを作成
drive_service = build('drive', 'v3', credentials=credentials)

# スプレッドシートのコピー
def copy_spreadsheet(source_spreadsheet_id):
    try:
        copy_body = {"name": "コピーされたスプレッドシート"}
        copied_file = drive_service.files().copy(
            fileId=source_spreadsheet_id, body=copy_body
        ).execute()
        return copied_file['id']
    except Exception as e:
        st.error(f"スプレッドシートのコピーに失敗: {e}")
        return None

# Googleスプレッドシート操作関数
def write_to_sheets(spreadsheet_id, sheet_name, cell, value):
    try:
        sheet_range = f"{sheet_name}!{cell}"
        body = {'values': [[value]]}
        sheets_service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
            valueInputOption="RAW",
            body=body
        ).execute()
    except Exception as e:
        st.error(f"スプレッドシートへの書き込み中にエラー: {e}")

# スプレッドシートをダウンロード
def download_spreadsheet(spreadsheet_id):
    try:
        request = drive_service.files().export_media(
            fileId=spreadsheet_id, mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        file_path = f"{spreadsheet_id}.xlsx"
        with open(file_path, "wb") as f:
            f.write(request.execute())
        return file_path
    except Exception as e:
        st.error(f"スプレッドシートのダウンロードに失敗: {e}")
        return None

# Streamlitアプリ
def main():
    st.title("Webアプリ ⇔ スプレッドシート連携")

    source_spreadsheet_id = "10VA09yrqyv4m653x8LdyAxT1MEd3kRAtNfteO9liLcg"
    sheet_name = "シート1"

    # スプレッドシートをコピー
    if st.button("スプレッドシートをコピー"):
        new_spreadsheet_id = copy_spreadsheet(source_spreadsheet_id)
        if new_spreadsheet_id:
            st.session_state["spreadsheet_id"] = new_spreadsheet_id
            st.success(f"スプレッドシートがコピーされました！ ID: {new_spreadsheet_id}")

    # 選択肢
    categories = ["認知力・操作", "言語理解", "表出言語"]
    options = ["0〜3か月", "3〜6か月", "6〜9か月", "9〜12か月"]

    selected_options = {}
    for index, category in enumerate(categories, start=1):
        st.subheader(category)
        selected_options[category] = st.radio(f"{category}の選択肢を選んでください:", options, key=f"radio_{index}")

    # スプレッドシートに書き込み
    if st.button("スプレッドシートに書き込む"):
        spreadsheet_id = st.session_state.get("spreadsheet_id", source_spreadsheet_id)
        for index, (category, selected_option) in enumerate(selected_options.items(), start=1):
            write_to_sheets(spreadsheet_id, sheet_name, f"A{index + 2}", category)
            write_to_sheets(spreadsheet_id, sheet_name, f"B{index + 2}", selected_option)
        st.success("データがスプレッドシートに書き込まれました！")

    # スプレッドシートをダウンロード
    if st.button("スプレッドシートをダウンロード"):
        spreadsheet_id = st.session_state.get("spreadsheet_id", source_spreadsheet_id)
        file_path = download_spreadsheet(spreadsheet_id)
        if file_path:
            with open(file_path, "rb") as f:
                st.download_button("ダウンロード", f, file_name="spreadsheet.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    main()