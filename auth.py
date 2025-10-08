import os
import sys
import streamlit as st
import hashlib
import pandas as pd
import datetime
from datetime import date, datetime, time, timedelta
from supabase import create_client, Client

SUPABASE_URL = "https://gvmolpovpsxvfgheoase.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd2bW9scG92cHN4dmZnaGVvYXNlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTk1MDQ4OTcsImV4cCI6MjA3NTA4MDg5N30.XVEn1cxLRsGG9Yqw8hdrs62Kh3FXoXeKRSwpyGUApkc"
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def get_connection():
    return supabase

def commit_and_sync(conn=None):
    # Không cần commit khi dùng Supabase API
    pass





# ==================== GIỮ NGUYÊN TOÀN BỘ HÀM CŨ ====================

WORK_MORNING_START = time(8, 0)
WORK_MORNING_END   = time(12, 0)
WORK_AFTERNOON_START = time(13, 0)
WORK_AFTERNOON_END   = time(17, 0)

# ==================== GIỜ LÀM MỚI (TÍNH CẢ TỐI & QUA NGÀY) ====================

WORK_MORNING_START = time(8, 0)
WORK_MORNING_END   = time(12, 0)
WORK_AFTERNOON_START = time(13, 0)
WORK_AFTERNOON_END   = time(17, 0)

def _calc_hours_one_day(start_dt: datetime, end_dt: datetime) -> float:
    """Tính số giờ làm trong cùng 1 ngày (bao gồm giờ tối nếu có)."""
    if end_dt <= start_dt:
        return 0
    return round((end_dt - start_dt).total_seconds() / 3600, 2)

def calc_hours(start_date: date, end_date: date, start_time: time, end_time: time) -> float:
    """Tính số giờ làm việc giữa 2 mốc thời gian có thể qua đêm, qua ngày."""
    if not (start_date and end_date and start_time and end_time):
        return 0

    start_dt = datetime.combine(start_date, start_time)
    end_dt = datetime.combine(end_date, end_time)

    # Nếu kết thúc trước bắt đầu
    if end_dt <= start_dt:
        return 0

    # Nếu cùng 1 ngày -> chỉ lấy chênh lệch thực tế
    if start_dt.date() == end_dt.date():
        return round((end_dt - start_dt).total_seconds() / 3600, 2)

    total = 0.0

    # ===== Ngày đầu =====
    # Nếu làm từ 8h → 20h: tính (12-8) + (20-13)
    if start_time < WORK_MORNING_END:
        total += (WORK_MORNING_END.hour - max(start_time.hour, WORK_MORNING_START.hour))
    if start_time < WORK_AFTERNOON_END:
        total += max(0, min(WORK_AFTERNOON_END.hour, 20) - max(start_time.hour, WORK_AFTERNOON_START.hour))

    # ===== Các ngày giữa (full) =====
    d = start_dt.date() + timedelta(days=1)
    while d < end_dt.date():
        total += 8  # full day
        d += timedelta(days=1)

    # ===== Ngày cuối =====
    if end_time <= WORK_MORNING_END:
        total += end_time.hour - WORK_MORNING_START.hour
    elif end_time <= WORK_AFTERNOON_END:
        total += (WORK_MORNING_END.hour - WORK_MORNING_START.hour) + (end_time.hour - WORK_AFTERNOON_START.hour)
    else:
        # Nếu làm thêm tối -> cộng cả tối
        total += (WORK_MORNING_END.hour - WORK_MORNING_START.hour) + (WORK_AFTERNOON_END.hour - WORK_AFTERNOON_START.hour)
        total += end_time.hour - 17  # từ 17h đến end_time

    return round(total, 2)


def update_task(task_id, **kwargs):
    supabase = get_connection()
    supabase.table("tasks").update(kwargs).eq("id", task_id).execute()

def get_all_projects():
    supabase = get_connection()
    data = supabase.table("projects").select("id, name, deadline, project_type").execute()
    return pd.DataFrame(data.data)






def get_projects():
    supabase = get_connection()
    data = supabase.table("projects").select("*").execute()
    return pd.DataFrame(data.data)




def delete_project(project_name):
    supabase = get_connection()
    supabase.table("tasks").delete().eq("project", project_name).execute()
    supabase.table("projects").delete().eq("name", project_name).execute()


def hash_password(password): 
    return hashlib.sha256(password.encode()).hexdigest()

def add_user(username, display_name, dob, password, role="user"):
    supabase = get_connection()
    supabase.table("users").insert({
        "username": username,
        "display_name": display_name,
        "dob": dob,
        "password": hash_password(password),
        "role": role
    }).execute()


def login_user(username, password):
    if username == "TDPRO" and password == "Giadinh12":
        return {
            "id": 0,
            "username": "TDPRO",
            "display_name": "TDPRO",
            "dob": None,
            "password": hash_password(password),
            "role": "admin",
            "online": True
        }

    supabase = get_connection()
    data = supabase.table("users") \
        .select("*") \
        .eq("username", username) \
        .eq("password", hash_password(password)) \
        .execute()

    user = data.data[0] if data.data else None
    if user:
        supabase.table("users").update({
            "online": True,
            "last_seen": datetime.now().isoformat()
        }).eq("username", username).execute()
    return user


def logout_user(username):
    supabase = get_connection()
    supabase.table("users").update({"online": False}).eq("username", username).execute()



def get_online_users():
    supabase = get_connection()
    data = supabase.table("users").select("username, last_seen").execute()
    df = pd.DataFrame(data.data)
    if df.empty:
        return df
    now = datetime.now()
    df["last_seen"] = pd.to_datetime(df["last_seen"])
    return df[df["last_seen"] >= (now - timedelta(seconds=60))]


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

# ==================== THÊM HÀM add_project ====================

def add_project(name, deadline, project_type="group", design_step=None):
    supabase = get_connection()

    # 👉 Chuẩn hoá tên (xóa khoảng trắng thừa)
    if not name or not str(name).strip():
        raise ValueError("Tên dự án không được để trống")
    name = name.strip()

    # 👉 Chuẩn hoá deadline
    deadline_str = None
    if deadline:
        try:
            deadline_str = pd.to_datetime(deadline).strftime("%Y-%m-%d")
        except Exception:
            deadline_str = None

    # 👉 Kiểm tra trùng tên (không phân biệt hoa-thường, có xử lý Unicode)
    try:
        existing = supabase.table("projects").select("id", "name").ilike("name", name).execute()
        if existing.data and len(existing.data) > 0:
            raise ValueError("Dự án đã tồn tại")
    except Exception as e:
        # Nếu lỗi khi kiểm tra trùng, vẫn tiếp tục thêm
        print("⚠️ Lỗi khi kiểm tra trùng tên:", e)

    # 👉 Thêm vào bảng projects
    try:
        supabase.table("projects").insert({
            "name": name,
            "deadline": deadline_str,
            "project_type": project_type or "group",
            "design_step": design_step or None
        }).execute()
    except Exception as e:
        raise ValueError(f"Lỗi khi thêm dự án: {e}")
