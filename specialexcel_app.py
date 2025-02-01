import streamlit as st
import io
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


# Googleスプレッドシートからデータを取得する
def read_from_sheets(sheet_name, cell):
    try:
        sheet_range = f"{sheet_name}!{cell}"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=sheet_range).execute()
        values = result.get('values', [])
        return values[0][0] if values else None
    except Exception as e:
        raise RuntimeError(f"スプレッドシートの読み取り中にエラーが発生しました: {e}")


# GoogleスプレッドシートをExcel形式でダウンロード
def download_spreadsheet():
    try:
        file_id = spreadsheet_id
        request = drive_service.files().export_media(
            fileId=file_id,
            mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_stream.seek(0)
        st.session_state["spreadsheet_data"] = file_stream  # **セッションにデータを保存**

    except Exception as e:
        st.error(f"ダウンロード中にエラーが発生しました: {e}")

# Streamlit アプリ
def main():
    st.title("Webアプリ ⇔ スプレッドシート連携")

    sheet_name = "シート1"

    categories = ["認知力・操作", "言語理解", "表出言語","視覚記憶","聴覚記憶","読字","書字","数","運動","生活動作"]
    options = ["0〜3か月", "3〜6か月", "6〜9か月", "9〜12か月","12～18ヶ月","18～24ヶ月","2～3歳","3～4歳","4～5歳","5～6歳","6際～7歳","7歳以上"]

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
        except RuntimeError as e:
            st.error(f"エラー: {e}")

# **選択肢を数値に変換**
option_values = {
    "0〜3か月": 1, "3〜6か月": 2, "6〜9か月": 3, "9〜12か月": 4,
    "12か月～18ヶ月": 5, "18ヶ月～24ヶ月": 6, "2～3歳": 7, "3～4歳": 8,
    "4～5歳": 9, "5～6歳": 10, "6歳～7歳": 11, "7歳以上": 12
}

# スプレッドシートにデータを書き込む
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

# Google Sheets に棒グラフを作成
def create_bar_chart(sheet_name):
    try:
        # グラフ作成のリクエスト
        requests = [{
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "発達段階 棒グラフ",
                        "basicChart": {
                            "chartType": "COLUMN",
                            "legendPosition": "BOTTOM",
                            "axis": [
                                {"position": "BOTTOM", "title": "カテゴリー"},
                                {"position": "LEFT", "title": "発達段階"}
                            ],
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": 0,  # シートのID（デフォルト 0）
                                            "startRowIndex": 1,
                                            "endRowIndex": 4,  # 3カテゴリ分
                                            "startColumnIndex": 0,
                                            "endColumnIndex": 1
                                        }]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": 0,
                                            "startRowIndex": 1,
                                            "endRowIndex": 4,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 2
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT"
                            }]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": 0,
                                "rowIndex": 6,
                                "columnIndex": 0
                            }
                        }
                    }
                }
            }
        }]

        # リクエスト送信
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

        st.success("スプレッドシートに棒グラフを作成しました！")

    except Exception as e:
        st.error(f"棒グラフ作成中にエラーが発生しました: {e}")

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


