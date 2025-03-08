import streamlit as st
import io
import requests
import sys
import io
import time

from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
from google.cloud import storage
from googleapiclient.http import MediaIoBaseDownload
from some_module import copy_spreadsheet

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
spreadsheet_id = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"#"10VA09yrqyv4m653x8LdyAxT1MEd3kRAtNfteO9liLcg"
excel_file_id = "16O5LLCft2o2q4Xz8H5WDx6zzVA_23DBQ"  # Googleドライブ上のExcelファイルのIDを入力
# **コピー先のフォルダIDを指定**
FOLDER_ID = "1RjW33xskP4Qfunc6HAkWxfTKNZWh5oMP"  # ← ここにフォルダIDを入れる

# セッションステートを使用してコピーIDと最終アクセス時間を管理
if "copied_spreadsheet_id" not in st.session_state:
    st.session_state.copied_spreadsheet_id = None
if "last_access_time" not in st.session_state:
    st.session_state.last_access_time = time.time()

#orijinaruno ID
def get_folder_id(file_id):
    """ 指定したファイルが所属するフォルダIDを取得する """
    file_info = drive_service.files().get(fileId=file_id, fields="parents").execute()
    return file_info.get("parents", [None])[0]  # 最初のフォルダIDを取得

# スプレッドシートのコピーを作成
#def copy_spreadsheet():
 #   try:
  #      copied_file = drive_service.files().copy(
   ##        body={
     #           "name": "コピーされたスプレッドシート",
      #          "parents": [FOLDER_ID]
       #     }
        #).execute()
       # copied_file_id = copied_file["id"]
        #st.session_state.copied_spreadsheet_id = copied_file_id
        #st.success("スプレッドシートのコピーを作成しました！")
    #except Exception as e:
     #   st.error(f"スプレッドシートのコピー作成中にエラーが発生: {e}")



# **一定時間（10分間）操作がなかったら削除**
def check_and_delete_old_copy():
    current_time = time.time()
    if st.session_state.copied_spreadsheet_id and (current_time - st.session_state.last_access_time > 600):  # 10分
      copy_spreadsheet()
# Streamlitのメインループ内で `check_and_delete_old_copy()` を定期的に実行
check_and_delete_old_copy()

def write_to_sheets(spreadsheet_id, sheet_name, cell, value):
    try:
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!{cell}",
            valueInputOption="RAW",
            body={"values": [[value]]}
        ).execute()
    except Exception as e:
        st.error(f"スプレッドシートの更新中にエラーが発生: {e}")


def main():
    st.title("📉発達段階能力チャート作成📈")
    st.info("児童・生徒の発達段階が分からない場合は下の「現在の発達段階を表から確認する」⇒「発達段階表」を順に押して下さい。")

    sheet_name = "シート1"
    categories = ["認知力・操作", "言語理解", "表出言語", "視覚記憶", "聴覚記憶", "読字", "書字", "粗大運動", "微細運動", "数の概念", "生活動作"]
    options = ["0〜3ヶ月", "3〜6ヶ月", "6〜9ヶ月", "9〜12ヶ月", "12～18ヶ月", "18～24ヶ月", "2～3歳", "3～4歳", "4～5歳", "5～6歳", "6～7歳", "7歳以上"]

    # ★ 修正：変数 selected_options を関数スコープ内に定義
    selected_options = {category: st.radio(f"{category}の選択肢を選んでください:", options, key=f"radio_{index}")
                        for index, category in enumerate(categories, start=1)}
    st.info("「スプレッドシートに書き込む」を押してから「スプレッドシートを開く」⇒保存したい人は「Excelに保存を」⇒「保存」を押してください。")
    if st.button("スプレッドシートに書き込む"):
     st.session_state.last_access_time = time.time()
    

    # コピーがまだない場合、作成する
    if st.session_state.copied_spreadsheet_id is None:
        copy_spreadsheet()

    copied_id = st.session_state.copied_spreadsheet_id
    if copied_id:
        update_values = [
            [category, selected_options[category]] for category in categories
        ]
        try:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=copied_id,
                body={
                    "valueInputOption": "RAW",
                    "data": [
                        {"range": f"{sheet_name}!A3:B13", "values": update_values}
                    ]
                }
            ).execute()

            # 入力データを基に処理を実行
            age_categories = {
                "0〜3ヶ月": 1, "3〜6ヶ月": 2, "6〜9ヶ月": 3, "9〜12ヶ月": 4,
                "12～18ヶ月": 5, "18～24ヶ月": 6, "2～3歳": 7, "3～4歳": 8,
                "4～5歳": 9, "5～6歳": 10, "6～7歳": 11, "7歳以上": 12
            }

            converted_values = [[age_categories.get(selected_options[category], "")] for category in categories]
        
            batch_requests = {
            "valueInputOption": "RAW",
            "data": [
                {"range": "シート1!A3:B13", "values": update_values},
                {"range": "シート1!C3:C13", "values": converted_values}
            ]
            }
        
            service.spreadsheets().values().batchUpdate(
            spreadsheetId=copied_id,
            body=batch_requests
            ).execute()

            # シート2のデータ取得
            sheet2_data = service.spreadsheets().values().get(
                spreadsheetId=copied_id,
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

            results = [[data_map.get(category, {}).get(age[0], "該当なし")]
           for category, age in zip(categories, converted_values)]


            # A3:C13をA18:C28にコピー
            sheet1_copy_data = update_values + converted_values

# C18:C28 の値を +1（最大値12を超えない）
            # C3:C13 から値を取得し、+1 する（最大12）
            source_values = converted_values[:11]  # C3:C13 のデータ（最大11行）

# データの不足を防ぐため、必ず11行にする
            while len(source_values) < 11:
              source_values.append([""])  # 足りない部分は空欄

# +1 した値を updated_c_values に格納（最大12）
            updated_c_values = [
             [min(12, int(row[0]) + 1) if row and str(row[0]).isdigit() else ""]
             for row in source_values
            ]
            # **デバッグ用に出力**
            print("updated_c_values:", updated_c_values)
            print("updated_c_values の行数:", len(updated_c_values))  # 11 になってるか確認
            if len(updated_c_values) != 11:
              raise ValueError(f"updated_c_values の行数が 11 ではありません: {len(updated_c_values)} 行")

# D18:D28 の計算
            new_results = [
             [data_map.get(category, {}).get(c_value[0], "該当なし")]
             for category, c_value in zip(categories, updated_c_values) if c_value[0] != ""
            ]

            
# すべての更新処理を batchUpdate にまとめる
            batch_requests["data"].extend([
              {"range": "シート1!D3:D13", "values": results},
              {"range": "シート1!A18:C28", "values": sheet1_copy_data[:11]},  # 11行に制限
              {"range": "シート1!C18:C28", "values": updated_c_values[:11]},  # 11行に制限
              {"range": "シート1!D18:D28", "values": new_results[:11]}  # 11行に制限
            ])

            service.spreadsheets().values().batchUpdate(
              spreadsheetId=copied_id,
              body=batch_requests
            ).execute()

            def delete_previous_scatter_chart(spreadsheet_id):
              """ 既存の散布図グラフを削除する """
            
            updated_c_values = [
                [min(12, int(row[2]) + 1) if row[2] and str(row[2]).isdigit() else ""]
                 for row in sheet1_copy_data
            ]
            def add_scatter_chart(spreadsheet_id):
             chart_request = {
    "requests": [
        {
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "項目別発達段階（能力チャート）",
                        "basicChart": {
                            "chartType": "SCATTER",  # 散布図
                            "legendPosition": "BOTTOM_LEGEND",
                            "axis": [
                                {"position": "BOTTOM_AXIS", "title": "カテゴリ"},
                                {"position": "LEFT_AXIS", "title": "数値"}
                            ],
                            
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": 0,
                                            "startRowIndex": 2, "endRowIndex": 13,
                                            "startColumnIndex": 0, "endColumnIndex": 1
                                        }]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": 0,
                                            "startRowIndex": 2, "endRowIndex": 13,
                                            "startColumnIndex": 2, "endColumnIndex": 3
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS"
                            }]
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": 0, "rowIndex": 13, "columnIndex": 6  # G14
                            }
                        }
                    }
                }
            }
        }
    ]
}
             service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=chart_request).execute()

# 実行処理
            spreadsheet_id = st.session_state.copied_spreadsheet_id
            
            add_scatter_chart(spreadsheet_id)  # 新しい散布図を追加

        except Exception as e:
            st.error(f"エラーが発生しました: {e}")
    else:
        st.error("スプレッドシートのコピーが存在しません。")



            
    
# スプレッドシートを開く
    if st.button("スプレッドシートを開く"):
       st.session_state.last_access_time = time.time()  # 最終アクセス時間を更新

       if st.session_state.copied_spreadsheet_id:
        sheet_gid = "0"  # 必要に応じて変更
        spreadsheet_url = f"https://docs.google.com/spreadsheets/d/{st.session_state.copied_spreadsheet_id}/edit#gid={sheet_gid}"
        st.markdown(f"[スプレッドシートを開く]({spreadsheet_url})", unsafe_allow_html=True)
       else:
        st.warning("まだスプレッドシートのコピーが作成されていません。")

 

# EXCELを保存
    # Excelのダウンロード機能
    if st.button("EXCELを保存"):
     copied_id = st.session_state.copied_spreadsheet_id
    if copied_id:
        try:
            request = drive_service.files().export_media(
                fileId=copied_id,
                mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            file_data = io.BytesIO()
            downloader = MediaIoBaseDownload(file_data, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            
            file_data.seek(0)
            st.download_button(
                label="保存（EXCELを保存を押した後）",
                data=file_data.read(),
                file_name="spreadsheet.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.error(f"Excelの保存中にエラーが発生: {e}")
    else:
        st.warning("スプレッドシートのコピーが作成されていません。")

        st.info("保存EXCELにレーダーチャートは反映されません。必要な方は、画像保存〔（Windowsキー ＋ Shift + S ）⇒ダウンロードしたEXCELに貼り付け（Ctrl ＋ V）〕するか、スプレッドシートをそのまま印刷してください。")
   
# Excelダウンロード機能
    #if st.button("EXCELを保存"):
     #try:
        # Google Drive API を使用してスプレッドシートをエクスポート
      #  request = drive_service.files().export_media(
       #     fileId=spreadsheet_id,
        #    mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        #)
        #file_data = io.BytesIO()
        #downloader = MediaIoBaseDownload(file_data, request)
        #done = False
        #while not done:
         #   status, done = downloader.next_chunk()

#        file_data.seek(0)
 #       st.download_button(
  #          label="PCに結果を保存",
   #         data=file_data,
    #        file_name="spreadsheet.xlsx",
     #       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
      #  )
        


             # **区切り線**
               # **別のWebアプリへのリンク**
               

if __name__ == "__main__":
    main()
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