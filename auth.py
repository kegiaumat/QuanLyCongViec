import os
import sys
import psycopg2
import streamlit as st
import hashlib
import pandas as pd
import datetime
from datetime import date, datetime, time, timedelta
from psycopg2 import sql


def get_connection():
    conn = psycopg2.connect(
        host=os.getenv("db.gvmolpovpsxvfgheoase.supabase.co"),
        dbname=os.getenv("postgres"),
        user=os.getenv("postgres"),
        password=os.getenv("Taobe1201@1"),
        port=os.getenv("SUPABASE_PORT", "5432")
    )
    return conn, conn.cursor()


def commit_and_sync(conn):
    conn.commit()  # chỉ commit, không còn sync lên Drive


def _get_env(name, default=None):
    return os.environ.get(name, default)


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

    if task_name is not None:
        fields.append("task = %s")
        values.append(task_name)
    if khoi_luong is not None:
        fields.append("khoi_luong = %s")
        values.append(khoi_luong)
    if deadline is not None:
        deadline = pd.to_datetime(deadline).strftime("%Y-%m-%d")
        fields.append("deadline = %s")
        values.append(deadline)
    if note is not None:
        fields.append("note = %s")
        values.append(note)
    if progress is not None:
        fields.append("progress = %s")
        values.append(progress)

    if not fields:
        return

    sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id = %s"
    values.append(task_id)
    c.execute(sql, values)
    commit_and_sync(conn)
    conn.close()

def ensure_column_exists(cursor, table, column, coltype):
    """
    Nếu bảng chưa có cột thì thêm vào (Postgres-safe)
    """
    cursor.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name=%s;
    """, (table,))
    cols = [r[0] for r in cursor.fetchall()]
    if column not in cols:
        cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} {};")
                       .format(sql.Identifier(table),
                               sql.Identifier(column),
                               sql.SQL(coltype)))
def init_db():
    conn, c = get_connection()

    # === USERS ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE,
            display_name TEXT,
            dob DATE,
            password TEXT,
            role TEXT,
            project_manager_of TEXT,
            project_leader_of TEXT,
            online BOOLEAN DEFAULT FALSE,
            last_seen TIMESTAMP
        );
    """)

    # === PROJECTS ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            deadline DATE,
            project_type TEXT DEFAULT 'group',
            design_step TEXT
        );
    """)

    # === TASKS ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            project TEXT,
            task TEXT,
            assignee TEXT,
            deadline DATE,
            khoi_luong REAL DEFAULT 0,
            note TEXT,
            progress INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # === LOGS ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            task_id INTEGER,
            action TEXT,
            user TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # === JOB_CATALOG ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS job_catalog (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            unit TEXT,
            parent_id INTEGER REFERENCES job_catalog(id),
            project_type TEXT DEFAULT 'group'
        );
    """)

    # === PAYMENTS ===
    c.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            payment_number INTEGER,
            percent REAL DEFAULT 0,
            note TEXT,
            paid_at DATE DEFAULT CURRENT_DATE
        );
    """)

    # === Đảm bảo cột tồn tại (chỉ thêm khi thiếu) ===
    ensure_column_exists(c, "users", "dob", "DATE")
    ensure_column_exists(c, "users", "role", "TEXT")
    ensure_column_exists(c, "users", "project_manager_of", "TEXT")
    ensure_column_exists(c, "users", "project_leader_of", "TEXT")
    ensure_column_exists(c, "users", "online", "BOOLEAN DEFAULT FALSE")
    ensure_column_exists(c, "users", "last_seen", "TIMESTAMP")

    commit_and_sync(conn)
    conn.close()

def add_project(name, deadline, project_type="group", design_step=None):
    conn, c = get_connection()
    if deadline is not None:
        deadline = pd.to_datetime(deadline).strftime("%Y-%m-%d")
    c.execute(
        "INSERT INTO projects (name, deadline, project_type, design_step) VALUES (%s, %s, %s, %s)",
        (name, deadline, project_type, design_step)
    )
    commit_and_sync(conn)
    conn.close()


def get_projects():
    conn, _ = get_connection()
    df = pd.read_sql("SELECT * FROM projects", conn)
    conn.close()
    return df


def delete_project(project_name):
    conn, c = get_connection()
    c.execute("DELETE FROM tasks WHERE project=%s", (project_name,))
    c.execute("DELETE FROM projects WHERE name=%s", (project_name,))
    commit_and_sync(conn)
    conn.close()



def get_all_projects():
    conn, _ = get_connection()
    df = pd.read_sql("SELECT id, name, deadline, project_type FROM projects", conn)
    conn.close()
    return df

def hash_password(password): 
    return hashlib.sha256(password.encode()).hexdigest()

def add_user(username, display_name, dob, password, role="user"):
    conn, c = get_connection()
    c.execute(
        "INSERT INTO users (username, display_name, dob, password, role) VALUES (%s, %s, %s, %s, %s)",
        (username, display_name, dob, hash_password(password), role)
    )
    commit_and_sync(conn)
    conn.close()

def login_user(username, password):
    if username == "TDPRO" and password == "Giadinh12":
        return (0, "TDPRO", "TDPRO", None, hash_password(password), "admin", None, True)
    conn, c = get_connection()
    c.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (username, hash_password(password))
    )
    user = c.fetchone()
    if user:
        c.execute("UPDATE users SET online=TRUE, last_seen=NOW() WHERE username=%s", (username,))
        commit_and_sync(conn)
    conn.close()
    return user

def logout_user(username):
    conn, c = get_connection()
    c.execute("UPDATE users SET online=FALSE WHERE username=%s", (username,))
    commit_and_sync(conn)
    conn.close()


def get_online_users():
    conn, _ = get_connection()
    df = pd.read_sql(
        "SELECT username FROM users WHERE last_seen >= NOW() - INTERVAL '60 seconds'",
        conn
    )
    conn.close()
    return df

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
        except Exception as e:
            if "duplicate key" in str(e).lower():
                st.error("⚠️ Tên đăng nhập đã tồn tại!")
            else:
                st.error(f"⚠️ Lỗi: {e}")

