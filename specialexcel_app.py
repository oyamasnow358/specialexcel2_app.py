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


# 棒グラフをスプレッドシートに追加する関数
def add_chart_to_sheet():
    try:
        categories = ["認知力・操作", "言語理解", "表出言語","視覚記憶","聴覚記憶","読字","書字","数","運動","生活動作"]
        requests = [
            {
                "addChart": {
                    "chart": {
                        "spec": {
                            "title": "選択肢別の棒グラフ",
                            "basicChart": {
                                "chartType": "BAR",
                                "legendPosition": "BOTTOM_LEGEND",
                                "axis": [
                                    {
                                        "position": "BOTTOM_AXIS",
                                        "title": "カテゴリー",
                                    },
                                    {
                                        "position": "LEFT_AXIS",
                                        "title": "選択肢数",
                                    }
                                ],
                                "domains": [
                                    {
                                        "domain": {
                                            "sourceRange": {
                                                "sources": [
                                                    {
                                                        "sheetId": 0,  # シートのID（シート1）
                                                        "startRowIndex": 1,
                                                        "endRowIndex": len(categories) + 2,  # カテゴリーの範囲
                                                        "startColumnIndex": 0,
                                                        "endColumnIndex": 1
                                                    }
                                                ]
                                            }
                                        }
                                    }
                                ],
                                "series": [
                                    {
                                        "series": {
                                            "sourceRange": {
                                                "sources": [
                                                    {
                                                        "sheetId": 0,
                                                        "startRowIndex": 1,
                                                        "endRowIndex": len(categories) + 2,
                                                        "startColumnIndex": 1,
                                                        "endColumnIndex": 2
                                                    }
                                                ]
                                            }
                                        },
                                        "targetAxis": "LEFT_AXIS"
                                    }
                                ]
                            }
                        },
                        "position": {
                            "overlayPosition": {
                                "anchorCell": "D4",  # グラフを表示するセル位置
                                "offsetXPixels": 0,
                                "offsetYPixels": 0
                            }
                        }
                    }
                }
            }
        ]
        # リクエストを実行してグラフを追加
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()

        st.success("棒グラフがスプレッドシートに追加されました！")
    except Exception as error:
        st.error(f"グラフの作成中にエラーが発生しました: {error}")


# Streamlit アプリ
def main():
    st.title("Webアプリ ⇔ スプレッドシート連携")

    sheet_name = "シート1"

    categories = ["認知力・操作", "言語理解", "表出言語","視覚記憶","聴覚記憶","読字","書字","数","運動","生活動作"]
    options = ["0〜3ヶ月", "3〜6ヶ月", "6〜9ヶ月", "9〜12ヶ月","12～18ヶ月","18～24ヶ月","2～3歳","3～4歳","4～5歳","5～6歳","6際～7歳","7歳以上"]

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

            # **スプレッドシートに書き込んだ後に棒グラフを追加する**
            add_chart_to_sheet()
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
