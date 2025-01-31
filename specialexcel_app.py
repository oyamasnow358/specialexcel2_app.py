import streamlit as st
from googleapiclient.discovery import build
from google.oauth2 import service_account
import os
from google.cloud import storage

# 環境変数または直接指定で認証情報ファイルのパスを取得
credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "propane-atrium-449411-e6-e1bccb92a993.json")
if not os.path.exists(credentials_path):
    st.error("認証情報ファイルが見つかりません。適切なJSONファイルを指定してください。")
    st.stop()  # アプリを終了

# Google Cloud Storage クライアント
try:
    client = storage.Client.from_service_account_json(credentials_path)
except Exception as e:
    st.error(f"Google Cloud Storage の認証に失敗しました: {e}")
    st.stop()

# Google Sheets API 認証
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

def authenticate_sheets():
    try:
        creds = service_account.Credentials.from_service_account_file(
            credentials_path, scopes=SCOPES)
        return build('sheets', 'v4', credentials=creds)
    except Exception as e:
        st.error(f"Google Sheets API の認証に失敗しました: {e}")
        st.stop()

# Googleスプレッドシート操作関数
def write_to_sheets(spreadsheet_id, sheet_name, cell, value):
    try:
        service = authenticate_sheets()
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
        service = authenticate_sheets()
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

if __name__ == "__main__":
    main()