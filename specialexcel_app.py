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

# スプレッドシートのID
spreadsheet_id = "10VA09yrqyv4m653x8LdyAxT1MEd3kRAtNfteO9liLcg"

# シートIDを取得する関数
def get_sheet_id(sheet_name):
    try:
        spreadsheet = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheets = spreadsheet.get("sheets", [])
        for sheet in sheets:
            if sheet["properties"]["title"] == sheet_name:
                return sheet["properties"]["sheetId"]
        return None
    except Exception as e:
        st.error(f"シートID取得中にエラーが発生しました: {e}")
        return None

# Google Sheets に棒グラフを作成
def create_bar_chart(sheet_name):
    sheet_id = get_sheet_id(sheet_name)
    if sheet_id is None:
        st.error("シートIDが取得できませんでした。")
        return

    try:
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
                                            "sheetId": sheet_id,
                                            "startRowIndex": 1,
                                            "endRowIndex": 11,  # 10項目分
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
                                            "sheetId": sheet_id,
                                            "startRowIndex": 1,
                                            "endRowIndex": 11,
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
                                "sheetId": sheet_id,
                                "rowIndex": 15,
                                "columnIndex": 0
                            }
                        }
                    }
                }
            }
        }]

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

        st.success("スプレッドシートに棒グラフを作成しました！")

    except Exception as e:
        st.error(f"棒グラフ作成中にエラーが発生しました: {e}")

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

    # 棒グラフ作成ボタン
    if st.button("棒グラフを作成"):
        create_bar_chart(sheet_name)

if __name__ == "__main__":
    main()
