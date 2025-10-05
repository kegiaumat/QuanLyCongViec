import psycopg2
import streamlit as st
import pandas as pd
import hashlib
from datetime import date, datetime, time, timedelta

# ==================== KẾT NỐI POSTGRES (SUPABASE) ====================

def get_connection():
    conn = psycopg2.connect(
        host=st.secrets["SUPABASE_HOST"],
        dbname=st.secrets["SUPABASE_DB"],
        user=st.secrets["SUPABASE_USER"],
        password=st.secrets["SUPABASE_PASSWORD"],
        port=st.secrets.get("SUPABASE_PORT", "5432")
    )
    return conn, conn.cursor()

def commit_and_sync(conn):
    conn.commit()

# ==================== HỖ TRỢ ====================

def hash_password(password): 
    return hashlib.sha256(password.encode()).hexdigest()

# ==================== USER ====================

def add_user(username, display_name, dob, password, role="user"):
    conn, c = get_connection()
    c.execute(
        "INSERT INTO users (username, display_name, dob, password, role) VALUES (%s, %s, %s, %s, %s)",
        (username, display_name, dob, hash_password(password), role)
    )
    commit_and_sync(conn)

def login_user(username, password):
    if username == "TDPRO" and password == "Giadinh12":
        return (0, "TDPRO", "TDPRO", None, hash_password(password), "admin", None, 1)

    conn, c = get_connection()
    c.execute(
        "SELECT * FROM users WHERE username=%s AND password=%s",
        (username, hash_password(password))
    )
    user = c.fetchone()
    if user:
        c.execute(
            "UPDATE users SET online=1, last_seen=NOW() WHERE username=%s",
            (username,)
        )
        commit_and_sync(conn)
    return user

def logout_user(username):
    conn, c = get_connection()
    c.execute("UPDATE users SET online=0 WHERE username=%s", (username,))
    commit_and_sync(conn)

def get_online_users():
    conn, _ = get_connection()
    return pd.read_sql(
        "SELECT username FROM users WHERE last_seen >= NOW() - INTERVAL '60 seconds'",
        conn
    )

# ==================== PROJECT ====================

def add_project(name, deadline, project_type="group", design_step=None):
    conn, c = get_connection()
    dl = pd.to_datetime(deadline).strftime("%Y-%m-%d") if deadline else None
    c.execute(
        "INSERT INTO projects (name, deadline, project_type, design_step) VALUES (%s, %s, %s, %s)",
        (name, dl, project_type, design_step)
    )
    commit_and_sync(conn)

def get_projects():
    conn, _ = get_connection()
    return pd.read_sql("SELECT * FROM projects", conn)

def delete_project(project_name):
    conn, c = get_connection()
    c.execute("DELETE FROM tasks WHERE project=%s", (project_name,))
    c.execute("DELETE FROM projects WHERE name=%s", (project_name,))
    commit_and_sync(conn)

def get_all_projects():
    conn, _ = get_connection()
    return pd.read_sql("SELECT id, name, deadline, project_type FROM projects", conn)

# ==================== TASKS ====================

def update_task(task_id, task_name=None, khoi_luong=None, deadline=None, note=None, progress=None):
    conn, c = get_connection()
    fields, values = [], []
    if task_name is not None: fields.append("task=%s"); values.append(task_name)
    if khoi_luong is not None: fields.append("khoi_luong=%s"); values.append(khoi_luong)
    if deadline is not None:
        dl = pd.to_datetime(deadline).strftime("%Y-%m-%d")
        fields.append("deadline=%s"); values.append(dl)
    if note is not None: fields.append("note=%s"); values.append(note)
    if progress is not None: fields.append("progress=%s"); values.append(progress)

    if not fields: return
    sql = f"UPDATE tasks SET {', '.join(fields)} WHERE id=%s"
    values.append(task_id)
    c.execute(sql, values)
    commit_and_sync(conn)

# ==================== TÍNH GIỜ ====================

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
