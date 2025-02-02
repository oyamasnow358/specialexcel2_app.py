import streamlit as st
import io
import requests
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.cloud import storage
from googleapiclient.http import MediaIoBaseDownload

# Secrets から認証情報を取得
credentials = Credentials.from_service_account_info(
    st.secrets["google_credentials"],
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)

# Google Sheets API クライアントを作成
service = build('sheets', 'v4', credentials=credentials)

# Google Drive API クライアントを作成（ダウンロード時に使用）
drive_service = build('drive', 'v3', credentials=credentials)

# Google Cloud Storage クライアントを作成（必要なら使用）
client = storage.Client(credentials=credentials)

# **スプレッドシートのIDをグローバル変数として定義**
spreadsheet_id = "10VA09yrqyv4m653x8LdyAxT1MEd3kRAtNfteO9liLcg"

# Googleスプレッドシートにデータを書き込む
def write_to_sheets(sheet_name, cell, value):
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

# Google Apps Script をトリガーする関数
def trigger_apps_script():
    try:
        # Apps Script Web アプリケーションの URL
        apps_script_url = "https://script.google.com/macros/s/AKfycbyKSWcYKeVzuqHbM5oNjOv6wEDvJsaM8_wMf2CjSTZHlcuGNbqWkcmecjilw6JysCaiVw/exec"  # 先ほどコピーした URL を貼り付ける

        # Apps Script にリクエストを送信
        response = requests.get(apps_script_url)
        if response.status_code == 200:
            st.success("スプレッドシートのプログラムが実行されました！")
        else:
            st.error(f"プログラムの実行中にエラーが発生しました: {response.text}")
    except Exception as e:
        st.error(f"Apps Script のトリガー中にエラーが発生しました: {e}")

# Googleスプレッドシートからデータを読み取る
def read_from_sheets(sheet_name, cell):
    try:
        sheet_range = f"{sheet_name}!{cell}"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_range
        ).execute()
        values = result.get("values", [])
        if not values:
            return "データが見つかりませんでした"
        return values[0][0]  # セルの値を返す
    except Exception as e:
        raise RuntimeError(f"スプレッドシートからの読み取り中にエラーが発生しました: {e}")

# スプレッドシートをダウンロードする
def download_spreadsheet():
    try:
        # ファイルのメタデータを取得
        file_metadata = drive_service.files().get(fileId=spreadsheet_id, fields="name, webViewLink").execute()
        file_name = file_metadata["name"]
        web_view_link = file_metadata["webViewLink"]  # スプレッドシートのビューリンク

        # ユーザーにダウンロード用リンクを表示
        st.success(f"スプレッドシート '{file_name}' を以下のリンクからダウンロードしてください。")
        st.markdown(f"[スプレッドシートをダウンロードする]({web_view_link})")
    except Exception as e:
        raise RuntimeError(f"スプレッドシートのリンク生成中にエラーが発生しました: {e}")

# Streamlit アプリ
def main():
    st.title("Webアプリ ⇔ スプレッドシート連携")

    sheet_name = "シート1"

    categories = ["認知力・操作", "言語理解", "表出言語", "視覚記憶", "聴覚記憶", "読字", "書字", "粗大運動", "微細運動","数の概念","生活動作"]
    options = ["0〜3ヶ月", "3〜6ヶ月", "6〜9ヶ月", "9〜12ヶ月", "12～18ヶ月", "18～24ヶ月", "2～3歳", "3～4歳", "4～5歳", "5～6歳", "6～7歳", "7歳以上"]

    selected_options = {}

    for index, category in enumerate(categories, start=1):
        st.subheader(category)
        selected_options[category] = st.radio(f"{category}の選択肢を選んでください:", options, key=f"radio_{index}")

    if st.button("スプレッドシートに書き込む"):
        try:
            for index, (category, selected_option) in enumerate(selected_options.items(), start=1):
                write_to_sheets(sheet_name, f"A{index + 2}", category)
                write_to_sheets(sheet_name, f"B{index + 2}", selected_option)
            st.success("各項目と選択肢がスプレッドシートに書き込まれました！")

            # Google Apps Script をトリガー
            trigger_apps_script()
        except RuntimeError as e:
            st.error(f"エラー: {e}")

    if st.button("スプレッドシートの答えを取得"):
        try:
            result = read_from_sheets(sheet_name, "B2")
            st.write(f"スプレッドシートの答え: {result}")
        except RuntimeError as e:
            st.error(f"エラー: {e}")

    # **ダウンロードボタン**
    if st.button("スプレッドシートをダウンロード"):
        download_spreadsheet()

    # **ダウンロードデータが準備できたら自動的に表示**
    if "spreadsheet_data" in st.session_state:
        st.download_button(
            label="スプレッドシートを保存",
            data=st.session_state["spreadsheet_data"],
            file_name="spreadsheet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


if __name__ == "__main__":
    main()
