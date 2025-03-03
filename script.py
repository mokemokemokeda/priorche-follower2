import xlsxwriter
import pandas as pd
import requests
import time
import io
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from datetime import datetime
import os
import json

# 環境変数からサービスアカウントキーを取得
google_credentials_json = os.getenv("GOOGLE_SERVICE_ACCOUNT")
if not google_credentials_json:
    raise ValueError("GOOGLE_SERVICE_ACCOUNT が設定されていません。")
json_data = json.loads(google_credentials_json)

# Google Drive API 認証
credentials = service_account.Credentials.from_service_account_info(json_data)
drive_service = build("drive", "v3", credentials=credentials)
print("Google Drive API 認証完了")

# Google Drive からファイル ID を取得する関数
def get_file_id(file_name):
    query = f"name = '{file_name}' and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None

# Google Sheets ファイルを Excel にエクスポートしてダウンロードする関数
def download_google_sheets_file(file_id):
    request = drive_service.files().export_media(
        fileId=file_id, mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    fh.seek(0)
    return fh

# Twitter API 認証
twitter_bearer_token = os.getenv("TWITTER_BEARER_TOKEN")
if not twitter_bearer_token:
    raise ValueError("TWITTER_BEARER_TOKEN が設定されていません。")
headers = {"Authorization": f"Bearer {twitter_bearer_token}"}
url = "https://api.twitter.com/2/users/by/username/"

# Google Drive から Twitter アカウントリスト取得
file_id = get_file_id("priorche.csv")
if file_id:
    df = pd.read_csv(f"https://drive.google.com/uc?id={file_id}")
    print("Twitterアカウントリスト取得完了")
else:
    raise FileNotFoundError("priorche.csv が見つかりません。")

# 日付取得
today = datetime.today().strftime("%Y/%m/%d")
followers_data = {"Date": today}

# フォロワー数取得
for username in df["username"]:
    user_url = f"{url}{username}?user.fields=public_metrics"
    response = requests.get(user_url, headers=headers)
    if response.status_code == 200:
        user_data = response.json()
        followers_count = user_data["data"]["public_metrics"]["followers_count"]
        followers_data[username] = followers_count
        print(f"@{username} のフォロワー数: {followers_count}")
    else:
        print(f"⚠️ エラー: {response.status_code} - @{username}")
    time.sleep(1)  # API制限対策

new_data = pd.DataFrame([followers_data])

# 記録ファイルの取得と更新
history_file = "priorche.xlsx"
history_id = get_file_id(history_file)
if history_id:
    file_metadata = drive_service.files().get(fileId=history_id).execute()
    mime_type = file_metadata["mimeType"]
    if mime_type == "application/vnd.google-apps.spreadsheet":
        history_df = pd.read_excel(download_google_sheets_file(history_id))
    else:
        history_df = pd.read_excel(f"https://drive.google.com/uc?id={history_id}")
else:
    history_df = pd.DataFrame()

# 各列にデータを整列
df_columns = df["username"].tolist() + ["Date"]
if history_df.empty:
    history_df = pd.DataFrame(columns=df_columns)

history_df = pd.concat([history_df, new_data], ignore_index=True)

# ExcelファイルをGoogle Driveにアップロード
with io.BytesIO() as fh:
    with pd.ExcelWriter(fh, engine='xlsxwriter') as writer:
        history_df.to_excel(writer, index=False)
    fh.seek(0)
    media = MediaIoBaseUpload(fh, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    if history_id:
        drive_service.files().update(fileId=history_id, media_body=media).execute()
    else:
        file_metadata = {"name": history_file, "mimeType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
        drive_service.files().create(body=file_metadata, media_body=media).execute()

print("フォロワー数を更新しました")
