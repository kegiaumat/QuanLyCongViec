import os
import sys
import sqlite3
import streamlit as st
import hashlib
import pandas as pd
import datetime
from datetime import date, datetime, time, timedelta

# ==================== GOOGLE DRIVE SUPPORT (FOLDER-BASED) ====================
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
import io, json

DEFAULT_LOCAL_DB = "tasks.db"
def get_connection(sync_from_drive=True):
    """Mỗi lần mở kết nối, nếu dùng Drive thì tải DB mới nhất về"""
    if _get_env("DB_BACKEND", "local").lower() == "drive":
        sa_json = _get_env("GDRIVE_SA")
        folder_id = _get_env("GDRIVE_FOLDER_ID")
        if sa_json and folder_id and sync_from_drive:
            try:
                download_db_from_drive(json.loads(sa_json), folder_id, DB_FILE)
            except Exception as e:
                print("⚠️ Download DB failed:", e)

    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn, conn.cursor()


def commit_and_sync(conn):
    """Commit và nếu dùng Drive thì upload DB lên Drive"""
    conn.commit()   # <-- commit SQLite
    if _get_env("DB_BACKEND", "local").lower() == "drive":
        sa_json = _get_env("GDRIVE_SA")
        folder_id = _get_env("GDRIVE_FOLDER_ID")
        if sa_json and folder_id:
            try:
                upload_db_to_drive(json.loads(sa_json), folder_id, DB_FILE)
                print("✅ DB synced to Google Drive")
            except Exception as e:
                print("⚠️ Upload DB failed:", e)


def _get_env(name, default=None):
    return os.environ.get(name, default)

def _build_drive_service_from_sa(sa_info: dict):
    scopes = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]
    credentials = service_account.Credentials.from_service_account_info(sa_info, scopes=scopes)
    return build("drive", "v3", credentials=credentials, cache_discovery=False)

def _find_or_create_db_file(service, folder_id: str, filename: str = "tasks.db") -> str:
    """Tìm file trong folder. Nếu chưa có thì tạo mới và trả về fileId"""
    query = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
    results = service.files().list(q=query, spaces='drive', fields="files(id, name)", pageSize=1).execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]
    else:
        # tạo mới file rỗng
        file_metadata = {"name": filename, "parents": [folder_id]}
        media = MediaFileUpload(filename, resumable=True) if os.path.exists(filename) else None
        new_file = service.files().create(body=file_metadata, media_body=media, fields="id").execute()
        return new_file["id"]

def download_db_from_drive(sa_info: dict, folder_id: str, local_path: str):
    service = _build_drive_service_from_sa(sa_info)
    file_id = _find_or_create_db_file(service, folder_id, os.path.basename(local_path))
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, mode="wb")
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    fh.close()

def upload_db_to_drive(sa_info: dict, folder_id: str, local_path: str):
    service = _build_drive_service_from_sa(sa_info)
    file_id = _find_or_create_db_file(service, folder_id, os.path.basename(local_path))
    media = MediaFileUpload(local_path, mimetype="application/x-sqlite3", resumable=True)
    service.files().update(fileId=file_id, media_body=media).execute()

def get_db_path():
    backend = _get_env("DB_BACKEND", "local").lower()
    local_path = _get_env("DB_LOCAL_PATH", DEFAULT_LOCAL_DB)
    if backend == "drive":
        folder_id = _get_env("GDRIVE_FOLDER_ID")
        sa_json = _get_env("GDRIVE_SA")
        if not folder_id or not sa_json:
            return local_path
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        try:
            if not os.path.exists(local_path):
                creds_info = json.loads(sa_json) if sa_json.strip().startswith("{") else None
                if creds_info:
                    download_db_from_drive(creds_info, folder_id, local_path)
        except Exception as e:
            print("⚠️ GDrive download error:", e)
        return local_path
    else:
        return local_path

DB_FILE = get_db_path()

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    return conn, conn.cursor()

# ==================== GIỮ NGUYÊN TOÀN BỘ HÀM CŨ ====================

WORK_MORNING_START = time(8, 0)
WORK_MORNING_END   = time(12, 0)
WORK_AFTERNOON_START = time(13, 0)
WORK_AFTERNOON_END   = time(17, 0)

def _calc_hours_one_day(start_dt: datetime, end_dt: datetime) -> float:
    if end_dt <= start_dt:
        return 0
    day = start_dt.date()
    ms, me = datetime.combine(day, WORK_MORNING_START), datetime.combine(day, WORK_MORNING_END)
    as_, ae = datetime.combine(day, WORK_AFTERNOON_START), datetime.combine(day, WORK_AFTERNOON_END)
    total = 0.0
    if start_dt < me and end_dt > ms:
        s, e = max(start_dt, ms), min(end_dt, me)
        if e > s:
            total += (e - s).total_seconds() / 3600
    if end_dt > as_ and start_dt < ae:
        s, e = max(start_dt, as_), min(end_dt, ae)
        if e > s:
            total += (e - s).total_seconds() / 3600
    return total

def calc_hours(start_date: date, end_date: date, start_time: time, end_time: time) -> float:
    if not (start_date and end_date and start_time and end_time):
        return 0
    start_dt = datetime.combine(start_date, start_time)
    end_dt   = datetime.combine(end_date, end_time)
    if end_dt < start_dt:
        return 0
    if start_dt.date() == end_dt.date():
        return round(_calc_hours_one_day(start_dt, end_dt), 2)
    total = 0.0
    total += _calc_hours_one_day(start_dt, datetime.combine(start_dt.date(), WORK_AFTERNOON_END))
    d = start_dt.date() + timedelta(days=1)
    while d < end_dt.date():
        total += 8
        d += timedelta(days=1)
    total += _calc_hours_one_day(datetime.combine(end_dt.date(), WORK_MORNING_START), end_dt)
    return round(total, 2)

def update_task(task_id, task_name=None, khoi_luong=None, deadline=None, note=None, progress=None):
    conn, c = get_connection()
    fields, values = [], []
    if task_name is not None: fields.append("task=?"); values.append(task_name)
    if khoi_luong is not None: fields.append("khoi_luong=?"); values.append(khoi_luong)
    if deadline is not None:
        deadline = pd.to_datetime(deadline).strftime("%Y-%m-%d")
        fields.append("deadline=?"); values.append(deadline)
    if note is not None: fields.append("note=?"); values.append(note)
    if progress is not None: fields.append("progress=?"); values.append(progress)
    if not fields: return
    sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id=?"
    values.append(task_id)
    c.execute(sql, values)
    commit_and_sync(conn)

def init_db():
    conn, c = get_connection()
    try:
        c.execute("""CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            display_name TEXT,
            dob DATE,
            password TEXT,
            role TEXT,
            project_manager_of TEXT,
            online INTEGER DEFAULT 0
        )""")
    except sqlite3.OperationalError: pass
    try:
        c.execute("""CREATE TABLE projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            deadline DATE,
            project_type TEXT DEFAULT 'group',
            design_step TEXT
        )""")
    except sqlite3.OperationalError: pass
    try:
        c.execute("""CREATE TABLE tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT,
            task TEXT,
            assignee TEXT,
            deadline DATE,
            khoi_luong REAL DEFAULT 0,
            note TEXT,
            progress INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    except sqlite3.OperationalError: pass
    try:
        c.execute("""CREATE TABLE logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            action TEXT,
            user TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    except sqlite3.OperationalError: pass
    try:
        c.execute("""CREATE TABLE job_catalog (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            unit TEXT,
            parent_id INTEGER REFERENCES job_catalog(id),
            project_type TEXT DEFAULT 'group'
        )""")
    except sqlite3.OperationalError: pass
    try:
        c.execute("""CREATE TABLE payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            payment_number INTEGER,
            percent REAL DEFAULT 0,
            note TEXT,
            paid_at DATE DEFAULT CURRENT_DATE,
            FOREIGN KEY(project_id) REFERENCES projects(id)
        )""")
    except sqlite3.OperationalError: pass
    commit_and_sync(conn)
    return conn, c

def add_project(name, deadline, project_type="group", design_step=None):
    conn, c = get_connection()
    if deadline is not None:
        deadline = pd.to_datetime(deadline).strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO projects (name, deadline, project_type, design_step) VALUES (?,?,?,?)",
        (name, deadline, project_type, design_step)
    )
    commit_and_sync(conn)

def get_projects():
    conn, _ = get_connection()
    return pd.read_sql("SELECT * FROM projects", conn)

def delete_project(project_name):
    conn, c = get_connection()
    c.execute("DELETE FROM tasks WHERE project=?", (project_name,))
    c.execute("DELETE FROM projects WHERE name=?", (project_name,))
    commit_and_sync(conn)

def get_all_projects():
    conn, _ = get_connection()
    return pd.read_sql("SELECT id, name, deadline, project_type FROM projects", conn)

def hash_password(password): return hashlib.sha256(password.encode()).hexdigest()

def add_user(username, display_name, dob, password, role="user"):
    conn, c = get_connection()
    c.execute("INSERT INTO users (username, display_name, dob, password, role) VALUES (?,?,?,?,?)",
              (username, display_name, dob, hash_password(password), role))
    commit_and_sync(conn)

def login_user(username, password):
    if username == "TDPRO" and password == "Giadinh12":
        return (0, "TDPRO", "TDPRO", None, hash_password(password), "admin", None, 1)
    conn, c = get_connection()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, hash_password(password)))
    user = c.fetchone()
    if user:
        c.execute("UPDATE users SET online=1, last_seen=CURRENT_TIMESTAMP WHERE username=?", (username,))
        commit_and_sync(conn)
    return user

def logout_user(username):
    conn, c = get_connection()
    c.execute("UPDATE users SET online=0 WHERE username=?", (username,))
    commit_and_sync(conn)

def get_online_users():
    conn, _ = get_connection()
    return pd.read_sql("SELECT username FROM users WHERE last_seen >= datetime('now', '-60 seconds')", conn)

def show_login():
    st.subheader("🔑 Đăng nhập")
    username = st.text_input("Tên đăng nhập")
    password = st.text_input("Mật khẩu", type="password")
    if st.button("Đăng nhập"):
        user = login_user(username, password)
        if user:
            st.session_state["user"] = user
            st.rerun()
        else:
            st.error("❌ Sai tài khoản hoặc mật khẩu")

def show_register():
    st.subheader("📝 Đăng ký tài khoản mới")
    username = st.text_input("Tên đăng nhập mới")
    display_name = st.text_input("Tên hiển thị")
    dob = st.date_input("Ngày sinh", min_value=date(1900,1,1), max_value=date.today())
    password = st.text_input("Mật khẩu", type="password")
    if st.button("Tạo tài khoản"):
        try:
            add_user(username, display_name, dob.isoformat(), password, role="user")
            st.success("✅ Tạo tài khoản thành công! (role mặc định: user)")
        except sqlite3.IntegrityError:
            st.error("⚠️ Tên đăng nhập đã tồn tại!")
