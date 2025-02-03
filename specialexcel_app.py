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

        # スプレッドシートのコピーを作成する関数
def copy_spreadsheet():
    try:
        # スプレッドシートのコピーを作成
        copied_file = drive_service.files().copy(fileId=spreadsheet_id, body={"name": "コピー - オリジナル"}).execute()
        copied_file_id = copied_file["id"]

        # **コピーの共有設定を「リンクを知っている全員が閲覧可能」に変更**
        permission = {
            "type": "anyone",  # 誰でもアクセス可能
            "role": "writer"   # 閲覧者（編集権限を付けたい場合は "writer" に変更）
        }
        drive_service.permissions().create(fileId=copied_file_id, body=permission).execute()

        # 共有可能なリンクを取得
        copied_file_metadata = drive_service.files().get(fileId=copied_file_id, fields="webViewLink").execute()
        copied_file_link = copied_file_metadata["webViewLink"]

        return copied_file_id, copied_file_link  # IDとリンクを返す
    except Exception as e:
        st.error(f"スプレッドシートのコピー作成中にエラーが発生しました: {e}")
        return None, None


# スプレッドシートをダウンロードする（コピーを作成して開く）
def download_spreadsheet():
    try:
        copied_file_id, copied_file_link = copy_spreadsheet()  # 修正: IDとリンクを受け取る

        if copied_file_link:
            st.success("スプレッドシートのコピーを開いて、スクリプトを実行してください。")
            st.markdown(f"[スプレッドシートを開く]({copied_file_link})")
            st.warning("スプレッドシートを開いた後に、以下のボタンを押してください。")

        else:
                    st.error("スプレッドシートのコピーが正しく作成されませんでした。")
    except Exception as e:
        raise RuntimeError(f"スプレッドシートのダウンロードリンク生成中にエラーが発生しました: {e}")

def export_to_excel(file_id):
    try:
        request = drive_service.files().export_media(fileId=file_id, mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        file_data = io.BytesIO()
        downloader = MediaIoBaseDownload(file_data, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        file_data.seek(0)
        return file_data
    except Exception as e:
        st.error(f"Excel変換中にエラーが発生しました: {e}")
        return None



# Streamlit アプリ
def main():
    st.title("📈発達段階能力チャート作成📉")

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



  # **区切り線**
    st.markdown("---")

    # **別のWebアプリへのリンク**
    st.markdown("関連Webアプリに移動する")
    st.markdown("[自立活動指導支援内容](https://aspecialeducationapp-6iuvpdfjbflp4wyvykmzey.streamlit.app/)")


if __name__ == "__main__":
    main()
