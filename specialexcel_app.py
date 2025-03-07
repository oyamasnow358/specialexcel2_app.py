import gspread
from google.oauth2.service_account import Credentials

# 認証情報の設定
scopes = ["https://www.googleapis.com/auth/spreadsheets"]
credentials = Credentials.from_service_account_file("config/credentials.json", scopes=scopes)

# スプレッドシートに接続
client = gspread.authorize(credentials)
spreadsheet_id = "1yXSXSjYBaV2jt2BNO638Y2YZ6U7rdOCv5ScozlFq_EE"

# シートを開く（最初のシートを取得）
spreadsheet = client.open_by_key(spreadsheet_id)
worksheet = spreadsheet.sheet1  # 最初のシート

# シートの全データを取得
data = worksheet.get_all_values()

# データの表示
for row in data:
    print(row)