import streamlit as st
import os
import requests
from google.cloud import storage
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.cloud import storage

# Secrets から認証情報を取得
credentials = Credentials.from_service_account_info(
    st.secrets["google_credentials"],
    scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/devstorage.full_control"]
)

# Google Sheets API クライアントを作成
service = build('sheets', 'v4', credentials=credentials)

# Google Cloud Storage クライアントを作成
client = storage.Client(credentials=credentials)

# Googleスプレッドシート操作関数
def write_to_sheets(spreadsheet_id, sheet_name, cell, value):
    try:
        sheet_range = f"{sheet_name}!{cell}"
        body = {'values': [[value]]}
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
            valueInputOption="RAW",
            body=body
        ).execute()
    except Exception as e:
        raise RuntimeError(f"スプレッドシートへの書き込み中にエラーが発生しました: {e}")

def read_from_sheets(spreadsheet_id, sheet_name, cell):
    try:
        sheet_range = f"{sheet_name}!{cell}"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=sheet_range).execute()
        values = result.get('values', [])
        return values[0][0] if values else None
    except Exception as e:
        raise RuntimeError(f"スプレッドシートの読み取り中にエラーが発生しました: {e}")

# Streamlitアプリ
def main():
    st.title("Webアプリ ⇔ スプレッドシート連携")

    spreadsheet_id = "10VA09yrqyv4m653x8LdyAxT1MEd3kRAtNfteO9liLcg"
    sheet_name = "シート1"

    # 項目と選択肢リスト
    categories = ["認知力・操作", "言語理解", "表出言語"]
    options = ["0〜3か月", "3〜6か月", "6〜9か月", "9〜12か月"]

    # 選択結果を格納する辞書
    selected_options = {}

    # 各項目ごとに選択肢を表示
    for index, category in enumerate(categories, start=1):
        st.subheader(category)
        selected_options[category] = st.radio(f"{category}の選択肢を選んでください:", options, key=f"radio_{index}")

    if st.button("スプレッドシートに書き込む"):
        try:
            for index, (category, selected_option) in enumerate(selected_options.items(), start=1):
                write_to_sheets(spreadsheet_id, sheet_name, f"A{index + 2}", category)  # A3, A4, A5に項目
                write_to_sheets(spreadsheet_id, sheet_name, f"B{index + 2}", selected_option)  # B3, B4, B5に選択肢
            st.success("各項目と選択肢がスプレッドシートに書き込まれました！")
        except RuntimeError as e:
            st.error(f"エラー: {e}")

    if st.button("スプレッドシートの答えを取得"):
        try:
            result = read_from_sheets(spreadsheet_id, sheet_name, "B2")
            st.write(f"スプレッドシートの答え: {result}")
        except RuntimeError as e:
            st.error(f"エラー: {e}")

def download_spreadsheet(spreadsheet_id):
    try:
        # スプレッドシートをExcel形式でエクスポート
        url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export?format=xlsx"
        headers = {"Authorization": f"Bearer {credentials.token}"}

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            with open("spreadsheet.xlsx", "wb") as f:
                f.write(response.content)
            
            with open("spreadsheet.xlsx", "rb") as f:
                st.download_button("スプレッドシートをダウンロード", f, file_name="spreadsheet.xlsx")
        else:
            st.error("スプレッドシートのダウンロードに失敗しました。")
    
    except Exception as e:
        st.error(f"ダウンロード中にエラーが発生しました: {e}")

if __name__ == "__main__":
    main()