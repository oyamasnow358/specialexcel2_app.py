import streamlit as st
import io
import requests
import pandas as pd
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
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

drive_service = build('drive', 'v3', credentials=credentials)

# スプレッドシートID
spreadsheet_id = "10VA09yrqyv4m653x8LdyAxT1MEd3kRAtNfteO9liLcg"

# Google Apps Script のエンドポイント
apps_script_url = "https://script.google.com/macros/s/AKfycbyKSWcYKeVzuqHbM5oNjOv6wEDvJsaM8_wMf2CjSTZHlcuGNbqWkcmecjilw6JysCaiVw/exec"

def write_to_sheets(sheet_name, cell, value):
    """Googleスプレッドシートにデータを書き込む"""
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
        raise RuntimeError(f"スプレッドシートへの書き込みエラー: {e}")

def trigger_apps_script():
    """Google Apps Script を確実にトリガー"""
    try:
        response = requests.post(apps_script_url)
        if response.status_code == 200:
            st.success("スプレッドシートのプログラムが実行されました！")
        else:
            st.error(f"エラー: {response.text}")
    except Exception as e:
        st.error(f"Apps Script のトリガーエラー: {e}")

def download_spreadsheet():
    """スプレッドシートをダウンロード（Excel 形式）"""
    try:
        sheet_name = "シート1"
        sheet_range = f"{sheet_name}!A1:D14"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_range
        ).execute()
        values = result.get("values", [])
        
        df = pd.DataFrame(values)
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, header=False, sheet_name=sheet_name)
        output.seek(0)
        
        st.download_button(
            label="スプレッドシートをダウンロード (Excel)",
            data=output,
            file_name="spreadsheet.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        st.error(f"スプレッドシートのダウンロードエラー: {e}")

def main():
    st.title("Webアプリ ⇔ スプレッドシート連携")
    
    sheet_name = "シート1"
    categories = ["認知力・操作", "言語理解", "表出言語", "視覚記憶", "聴覚記憶", "読字", "書字", "粗大運動", "微細運動", "数の概念", "生活動作"]
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
            st.success("スプレッドシートに書き込みました！")
            
            trigger_apps_script()
        except RuntimeError as e:
            st.error(f"エラー: {e}")
    
    if st.button("スプレッドシートをダウンロード"):
        download_spreadsheet()

if __name__ == "__main__":
    main()
