import streamlit as st
import io
import requests
import sys
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

def write_to_sheets(sheet_name, cell, value):
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!{cell}",
        valueInputOption="RAW",
        body={"values": [[value]]}
    ).execute()

def main():
    st.title("発達段階能力チャート作成")

    sheet_name = "シート1"

    categories = ["認知力・操作", "言語理解", "表出言語", "視覚記憶", "聴覚記憶", "読字", "書字", "粗大運動", "微細運動","数の概念","生活動作"]
    options = ["0〜3ヶ月", "3〜6ヶ月", "6〜9ヶ月", "9〜12ヶ月", "12～18ヶ月", "18～24ヶ月", "2～3歳", "3～4歳", "4～5歳", "5～6歳", "6～7歳", "7歳以上"]

    selected_options = {}

    for index, category in enumerate(categories, start=1):
        st.subheader(category)
        selected_options[category] = st.radio(f"{category}の選択肢を選んでください:", options, key=f"radio_{index}")

    if st.button("スプレッドシートに書き込む（これを押してから下記のボタンを押して下さい）"):
        try:
            # 各カテゴリと選択肢をスプレッドシートに書き込む
            for index, (category, selected_option) in enumerate(selected_options.items(), start=1):
                write_to_sheets(sheet_name, f"A{index + 2}", category)
                write_to_sheets(sheet_name, f"B{index + 2}", selected_option)

            # 年齢カテゴリのマッピング
            age_categories = {
                "0〜3ヶ月": 1, "3〜6ヶ月": 2, "6〜9ヶ月": 3, "9〜12ヶ月": 4,
                "12～18ヶ月": 5, "18～24ヶ月": 6, "2～3歳": 7, "3～4歳": 8,
                "4～5歳": 9, "5～6歳": 10, "6～7歳": 11, "7歳以上": 12
            }

            # シート1のデータを取得
            sheet1_data = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="シート1!A3:B13"
            ).execute().get('values', [])

            category_names = [row[0].strip() for row in sheet1_data]
            age_range = [row[1].strip() for row in sheet1_data]

            # 年齢を数値に変換
            converted_values = [[age_categories.get(age, "")] for age in age_range]

            # シート1のC3:C13に数値を設定
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="シート1!C3:C13",
                valueInputOption="RAW",
                body={"values": converted_values}
            ).execute()

            # シート2のデータを取得
            sheet2_data = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="シート2!A1:V"
            ).execute().get('values', [])

            headers = [h.strip() for h in sheet2_data[0]]
            data_map = {}
            for row in sheet2_data[1:]:
                age_step = row[21] if len(row) > 21 else ""
                if not age_step.isdigit():
                    continue
                for j, key in enumerate(headers):
                    if key not in data_map:
                        data_map[key] = {}
                    data_map[key][int(age_step)] = row[j]

            # シート1のD3:D13に対応する値を設定
            results = [[data_map.get(category, {}).get(age[0], "該当なし")]
                       for category, age in zip(category_names, converted_values)]
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="シート1!D3:D13",
                valueInputOption="RAW",
                body={"values": results}
            ).execute()

            # A3:C13をA18:C28にコピー
            sheet1_copy_data = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range="シート1!A3:C13"
            ).execute().get('values', [])
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="シート1!A18:C28",
                valueInputOption="RAW",
                body={"values": sheet1_copy_data}
            ).execute()

            # C18:C28の値を+1（最大値12を超えない）
            updated_c_values = [[min(12, int(row[2]) + 1) if row[2].isdigit() else ""] for row in sheet1_copy_data]
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="シート1!C18:C28",
                valueInputOption="RAW",
                body={"values": updated_c_values}
            ).execute()

            # D18:D28にシート2のデータを基に対応値を設定
            new_results = [[data_map.get(row[0], {}).get(c_value[0], "該当なし")]
                           for row, c_value in zip(sheet1_copy_data, updated_c_values) if c_value[0] != ""]
            service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="シート1!D18:D28",
                valueInputOption="RAW",
                body={"values": new_results}
            ).execute()

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")

   # ダウンロード機能
    if st.button("スプレッドシートを開く"):
     try:
        # スプレッドシートのURLを生成してブラウザで開けるようにする
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        st.markdown(f"[スプレッドシートを開く]({spreadsheet_url})", unsafe_allow_html=True)

        st.info("スプレッドシートを開いた後に、Excelとして保存できます。")
     except Exception as e:
        st.error(f"スプレッドシートのリンク生成中にエラーが発生しました: {e}")

# Excelダウンロード機能
    if st.button("EXCELを保存(レーダーチャートは反映されません)"):
     try:
        # Google Drive API を使用してスプレッドシートをエクスポート
        request = drive_service.files().export_media(
            fileId=spreadsheet_id,
            mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_data.seek(0)
        st.download_button(
            label="PCに結果を保存",
            data=file_data,
            file_name="spreadsheet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
     except Exception as e:
        st.error(f"Excel保存中にエラーが発生しました: {e}")
             # **区切り線**
    st.markdown("---")

    # **別のWebアプリへのリンク**
    st.markdown("関連Webアプリに移動する")
    st.markdown("[自立活動指導支援内容](https://aspecialeducationapp-6iuvpdfjbflp4wyvykmzey.streamlit.app/)")



if __name__ == "__main__":
    main()
 
