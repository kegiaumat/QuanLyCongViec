import os
import sqlite3
import pandas as pd
from datetime import datetime, date, time, timedelta

# Google Drive client libs
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io
import json

# default local DB file name
DEFAULT_LOCAL_DB = "tasks.db"

def _get_env(name, default=None):
    return os.environ.get(name, default)

def _build_drive_service_from_sa(sa_info: dict):
    scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    service = build('drive', 'v3', credentials=credentials, cache_discovery=False)
    return service

def download_db_from_drive(sa_info: dict, drive_file_id: str, local_path: str):
    service = _build_drive_service_from_sa(sa_info)
    request = service.files().get_media(fileId=drive_file_id)
    fh = io.FileIO(local_path, mode='wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.close()

def upload_db_to_drive(sa_info: dict, drive_file_id: str, local_path: str):
    service = _build_drive_service_from_sa(sa_info)
    media = MediaFileUpload(local_path, mimetype='application/x-sqlite3', resumable=True)
    if drive_file_id:
        service.files().update(fileId=drive_file_id, media_body=media).execute()
    else:
        file_metadata = {'name': os.path.basename(local_path)}
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        return file.get('id')

def get_db_path():
    backend = _get_env("DB_BACKEND", "local").lower()
    local_path = _get_env("DB_LOCAL_PATH", DEFAULT_LOCAL_DB)
    if backend == "drive":
        file_id = _get_env("GDRIVE_FILE_ID")
        sa_json = _get_env("GDRIVE_SA")
        if not file_id or not sa_json:
            return local_path
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        try:
            if not os.path.exists(local_path):
                creds_info = json.loads(sa_json) if sa_json.strip().startswith("{") else None
                if creds_info:
                    download_db_from_drive(creds_info, file_id, local_path)
        except Exception as e:
            print("⚠️ GDrive download error:", e)
        return local_path
    else:
        return local_path

DB_FILE = get_db_path()

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn, conn.cursor()

def init_db():
    conn, cursor = get_connection()
    cursor.execute("""CREATE TABLE IF NOT EXISTS tasks (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT,
                        description TEXT,
                        status TEXT,
                        start_time TEXT,
                        end_time TEXT,
                        hours REAL
                    )""")
    conn.commit()
    conn.close()

def update_task(task_id, **kwargs):
    conn, cursor = get_connection()
    updates = ", ".join([f"{key}=?" for key in kwargs])
    values = list(kwargs.values())
    values.append(task_id)
    cursor.execute(f"UPDATE tasks SET {updates} WHERE id=?", values)
    conn.commit()
    conn.close()
def add_project(name, deadline, project_type, design_step):
    conn, cursor = get_connection()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            deadline TEXT,
            project_type TEXT,
            design_step TEXT
        )
    """)
    conn.commit()

    cursor.execute(
        "INSERT INTO projects (name, deadline, project_type, design_step) VALUES (?,?,?,?)",
        (name, deadline, project_type, design_step)
    )
    conn.commit()
    conn.close()
