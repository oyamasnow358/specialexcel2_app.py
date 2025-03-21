import streamlit as st
import io
import requests
import sys
import os 
import json

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.cloud import storage
from googleapiclient.http import MediaIoBaseDownload

# 🔹 環境変数から Google 認証情報を取得
#google_credentials = json.loads(os.getenv("GOOGLE_CREDENTIALS"))

# 🔹 Google 認証情報を表示 (デバッグ用)
#st.write("Google Service Account:", google_credentials["client_email"])

# 環境変数から Google 認証情報を取得
#google_credentials_str = os.getenv("GOOGLE_CREDENTIALS")

#if google_credentials_str:
#    google_credentials = json.loads(google_credentials_str)
#else:
 #   st.error("GOOGLE_CREDENTIALS が設定されていません。環境変数を確認してください。")
  #  st.stop()
# 認証情報を取得
#if google_credentials:
 #   credentials = Credentials.from_service_account_info(
 #       google_credentials,
  #      scopes=[
   #         "https://www.googleapis.com/auth/spreadsheets",
    #        "https://www.googleapis.com/auth/drive"
     #   ]
    #)
#else:
 #   st.stop()  # 認証情報がない場合、アプリを停止

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
spreadsheet_id = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"

def write_to_sheets(sheet_name, cell, value):
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!{cell}",
        valueInputOption="RAW",
        body={"values": [[value]]}
    ).execute()

def main():
    st.title("📉発達段階能力チャート作成📈")
    st.info("児童・生徒の発達段階が分からない場合は下の「現在の発達段階を表から確認する」⇒「発達段階表」を順に押して下さい。")





    if st.button("現在の発達段階を表から確認する"):
     try:
        # 指定したシートのID（例: "0" は通常、最初のシート）
        sheet_gid = "643912489"  # 必要に応じて変更
        
        # スプレッドシートのURLを生成してブラウザで開けるようにする
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet_gid}"
        st.markdown(f"[発達段階表]({spreadsheet_url})", unsafe_allow_html=True)
        
     except Exception as e:
        st.error(f"スプレッドシートのリンク生成中にエラーが発生しました: {e}")


    sheet_name = "シート1"

    categories = ["認知力・操作", "認知力・注意力", "集団参加", "生活動作", "言語理解", "表出言語", "記憶", "読字", "書字", "粗大運動", "微細運動","数の概念"]
    options = ["0〜3ヶ月", "3〜6ヶ月", "6〜9ヶ月", "9〜12ヶ月", "12～18ヶ月", "18～24ヶ月", "2～3歳", "3～4歳", "4～5歳", "5～6歳", "6～7歳", "7歳以上"]
    #変更
    selected_options = {}

    for index, category in enumerate(categories, start=1):
        st.subheader(category)
        selected_options[category] = st.radio(f"{category}の選択肢を選んでください:", options, key=f"radio_{index}")

    st.markdown("""1.各項目の選択が終わりましたら、まず「スプレッドシートに書き込む」を押してください。  
                2.続いて「スプレッドシートを開く」を押して内容を確認してくだい。  
                3.Excelでデータを保存したい方は「EXCELを保存」を押してくだい。""")

    if st.button("スプレッドシートに書き込む"):
     try:
          # 各カテゴリと選択肢をスプレッドシートに書き込む
          for index, (category, selected_option) in enumerate(selected_options.items(), start=1):
              write_to_sheets(sheet_name, f"A{index + 2}", category)
              write_to_sheets(sheet_name, f"C{index + 2}", selected_option)  # C列に発達年齢を記入
      
          # 年齢カテゴリのマッピング
          age_categories = {
              "0〜3ヶ月": 1, "3〜6ヶ月": 2, "6〜9ヶ月": 3, "9〜12ヶ月": 4,
              "12～18ヶ月": 5, "18～24ヶ月": 6, "2～3歳": 7, "3～4歳": 8,
              "4～5歳": 9, "5～6歳": 10, "6～7歳": 11, "7歳以上": 12
          }
      
          # シート1のデータを取得
          sheet1_data = service.spreadsheets().values().get(
              spreadsheetId=spreadsheet_id,
              range="シート1!A3:C14"
          ).execute().get('values', [])
      
          # A列（カテゴリ名）とC列（発達年齢）を取得
          category_names = [row[0].strip() for row in sheet1_data]
          age_range = [row[2].strip() for row in sheet1_data]  # C列に発達年齢がある
      
          # 年齢を数値化
          converted_values = [[age_categories.get(age, "")] for age in age_range]
      
          # B3:B14に数値（段階）を設定
          service.spreadsheets().values().update(
              spreadsheetId=spreadsheet_id,
              range="シート1!B3:B14",
              valueInputOption="RAW",
              body={"values": converted_values}
          ).execute()
      
          # A3:C13をA18:C28にコピー
          sheet1_copy_data = service.spreadsheets().values().get(
              spreadsheetId=spreadsheet_id,
              range="シート1!A3:C14"
          ).execute().get('values', [])
          
          # シートの範囲を一度に更新
          service.spreadsheets().values().update(
              spreadsheetId=spreadsheet_id,
              range="シート1!A19:C30",
              valueInputOption="RAW",
              body={"values": sheet1_copy_data}
          ).execute()
      
          # B19:B30の段階を+1（最大値12を超えない）
          updated_b_values = [[min(12, int(row[1]) + 1) if row[1].isdigit() else ""] for row in sheet1_copy_data]
          service.spreadsheets().values().update(
              spreadsheetId=spreadsheet_id,
              range="シート1!B19:B30",
              valueInputOption="RAW",
              body={"values": updated_b_values}
          ).execute()
      
          # **🟢 B19:B30の段階データを取得**
          b19_b30_values = service.spreadsheets().values().get(
              spreadsheetId=spreadsheet_id,
              range="シート1!B19:B30"
          ).execute().get('values', [])
      
          # **🔵 B列の値（段階）を整数に変換**
          b19_b30_values = [int(row[0]) if row and row[0].isdigit() else None for row in b19_b30_values]
      
          # **🔵 段階に対応する発達年齢を取得**
          b_to_c_mapping = {  # B列の段階をC列の発達年齢に変換
              1: "0〜3ヶ月", 2: "3〜6ヶ月", 3: "6〜9ヶ月", 4: "9〜12ヶ月",
              5: "12～18ヶ月", 6: "18～24ヶ月", 7: "2～3歳", 8: "3～4歳",
              9: "4～5歳", 10: "5～6歳", 11: "6～7歳", 12: "7歳以上"
          }
      
          # **C19:C30に対応する発達年齢をセット**
          updated_c_values = [[b_to_c_mapping.get(b, "該当なし")] for b in b19_b30_values]
      
          # **Google SheetsにC19:C30のデータを更新**
          service.spreadsheets().values().update(
              spreadsheetId=spreadsheet_id,
              range="シート1!C19:C30",
              valueInputOption="RAW",
              body={"values": updated_c_values}
          ).execute()
      
          # **🟢 シート2のデータを取得**
          sheet2_data = service.spreadsheets().values().get(
              spreadsheetId=spreadsheet_id,
              range="シート2!A1:V"
          ).execute().get('values', [])
      
          # **データマッピングを作成**
          headers = [h.strip() for h in sheet2_data[0]]
          data_map = {}  # 🔵 ここで `data_map` を適切に定義
          for row in sheet2_data[1:]:
              age_step = row[21] if len(row) > 21 else ""
              if not age_step.isdigit():
                  continue
              for j, key in enumerate(headers):
                  if key not in data_map:
                      data_map[key] = {}
                  data_map[key][int(age_step)] = row[j]
      
          # **D3:D14にシート2の対応データを設定**
          results = [[data_map.get(category, {}).get(age[0], "該当なし")]
                     for category, age in zip(category_names, converted_values)]
          service.spreadsheets().values().update(
              spreadsheetId=spreadsheet_id,
              range="シート1!D3:D14",
              valueInputOption="RAW",
              body={"values": results}
          ).execute()
      
          # 🟢 B19:B30の値を取得（B列のデータ更新用）
          updated_b_values = [[row[1].strip()] for row in sheet1_copy_data]
      
          # **D19:D30も更新**
          new_results = [[data_map.get(row[0], {}).get(stage[0], "該当なし")]
                           for row, stage in zip(sheet1_copy_data, updated_b_values) if stage[0] != ""]
          service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="シート1!D19:D30",
                valueInputOption="RAW",
                body={"values": new_results}
            ).execute()

          st.success("スプレッドシートの更新が完了しました！")

     except Exception as e:
            st.error(f"エラーが発生しました: {e}")

  # ダウンロード機能
    if st.button("スプレッドシートを開く"):
     try:
        # 指定したシートのID（例: "0" は通常、最初のシート）
        sheet_gid = "0"  # 必要に応じて変更
        
        # スプレッドシートのURLを生成してブラウザで開けるようにする
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={sheet_gid}"
        st.markdown(f"[スプレッドシートを開く]({spreadsheet_url})", unsafe_allow_html=True)

        st.info("スプレッドシートを開いた後に、Excelとして保存できます。")
     except Exception as e:
        st.error(f"スプレッドシートのリンク生成中にエラーが発生しました: {e}")

    
# Excelダウンロード機能
    if st.button("EXCELを保存"):
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
        st.info("保存EXCELにレーダーチャートは反映されません。必要な方は、画像保存〔（Windowsキー ＋ Shift + S ）⇒ダウンロードしたEXCELに貼り付け（Ctrl ＋ V）〕するか、スプレッドシートをそのまま印刷してください。")
     except Exception as e:
        st.error(f"Excel保存中にエラーが発生しました: {e}")


             # **区切り線**
                # **別のWebアプリへのリンク**
    st.markdown("---")  # 区切り線   
    st.markdown("🌎関連Webアプリに移動する")
    st.markdown("[自立活動指導支援内容](https://aspecialeducationapp-6iuvpdfjbflp4wyvykmzey.streamlit.app/)")
    st.markdown("[特別支援教育で使える療法・分析法一覧](https://bunnsekiapppy-6zctfql94fk2x3ghmu5pmx.streamlit.app/)")
    st.markdown("---")  # 区切り線  
    st.markdown("📁教育・心理分析ツール") 
    st.markdown("[応用行動分析](https://abaapppy-k7um2qki5kggexf8qkfxjc.streamlit.app/)")
    st.markdown("[機能的行動評価分析](https://kinoukoudou-ptfpnkq3uqgaorabcyzgf2.streamlit.app/)") 
    st.markdown("---")  # 区切り線
    st.markdown("📁統計学分析ツール") 
    st.markdown("[相関分析ツール](https://soukan-jlhkdhkradbnxssy29aqte.streamlit.app/)")
    st.markdown("[多変量回帰分析](https://kaikiapp-tjtcczfvlg2pyhd9bjxwom.streamlit.app/)")
    st.markdown("[t検定](https://tkentei-flhmnqnq6dti6oyy9xnktr.streamlit.app/)")
    st.markdown("[ロジスティック回帰分析ツール](https://rojisthik-buklkg5zeh6oj2gno746ix.streamlit.app/)")
    st.markdown("[ノンパラメトリック統計分析ツール](https://nonparametoric-nkk2awu6yv9xutzrjmrsxv.streamlit.app/)")
    st.markdown("---")  # 区切り線
    st.write("""※ それぞれのアプリに記載してある内容、分析ツールのデータや図、表を外部に出す物（研究など）に使用する場合は小山までご相談ください。無断での転記・利用を禁じます。""")

if __name__ == "__main__":
    main()
 
