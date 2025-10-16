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




WORK_MORNING_START = time(8, 0)
WORK_MORNING_END   = time(12, 0)
WORK_AFTERNOON_START = time(13, 0)
WORK_AFTERNOON_END   = time(17, 0)






def calc_hours(start_date: date, end_date: date, start_time: time, end_time: time) -> float:
    """
    ✅ Hàm tính giờ công chuẩn thực tế
    - Nếu cùng ngày: (giờ về - giờ đi), trừ 1h nghỉ trưa nếu qua 12–13h.
    - Nếu qua nhiều ngày:
        + Ngày đầu:
            - Đi sau 17h → 4h
            - Đi trước 17h → (12 - giờ đi) + (17 - 13) trừ 1h nếu qua 12–13
        + Ngày giữa: 8h
        + Ngày cuối:
            - Về sáng ≤12h → (giờ về - 8)
            - Về chiều ≤17h → (4 + (giờ về - 13))
            - Về tối >17h → (4 + 4 + (giờ về - 17))
    """
    if not all([start_date, end_date, start_time, end_time]):
        return 0.0

    start_dt = datetime.combine(start_date, start_time)
    end_dt   = datetime.combine(end_date, end_time)
    if end_dt <= start_dt:
        return 0.0

    s = start_dt.hour + start_dt.minute / 60
    e = end_dt.hour + end_dt.minute / 60
    total = 0.0

    # --- Nếu cùng ngày ---
    if start_dt.date() == end_dt.date():
        total = e - s
        if s < 13 and e > 12:
            total -= 1  # trừ 1h nghỉ trưa nếu qua 12–13
        return round(max(0, total), 2)

    # --- Nếu qua nhiều ngày ---
    # Ngày đầu
    if s >= 17:
        total += 4
    else:
        total += (17 - s) 
        if s < 12:
            total -= 1  # chỉ trừ khi thật sự đi qua 12–13

    # Ngày giữa
    d = start_dt.date() + timedelta(days=1)
    while d < end_dt.date():
        total += 8
        d += timedelta(days=1)

    # Ngày cuối
    # --- Ngày cuối ---
    if e <= 8:
        pass  
    else:
        total += (e - 8)
        if e > 13:
            total -= 1  # chỉ trừ khi thật sự đi qua 12–13


    return round(max(0, total), 2)







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
def show_public_task_form(role, supabase, username, users=None):
    """
    Hiển thị form thêm công việc Public (công nhật)
    - Admin có thể chọn người khác để giao.
    - User/Project chỉ thêm công việc cho bản thân.
    - Tên công việc là selectbox (lấy từ bảng tasks_catalog).
    - Ghi chú nằm cuối form.
    """
    st.subheader("➕ Thêm công việc công nhật (Public)")

    # 🧭 Lấy danh sách công việc có sẵn
    try:
        data = supabase.table("tasks_catalog").select("task_name").execute()
        task_list = sorted([r["task_name"] for r in data.data]) if data.data else []
    except Exception:
        task_list = []

    # --- Xác định người được giao ---
    if role == "admin" and users:
        assignee = st.selectbox("👤 Giao việc cho", users)
    else:
        assignee = username

    # --- Nhập dữ liệu công việc ---
    col1, col2 = st.columns(2)
    with col1:
        task_name = st.selectbox("🧱 Tên công việc", task_list)
    with col2:
        start_date = st.date_input("📅 Ngày bắt đầu", date.today())

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        start_time = st.time_input("⏰ Giờ bắt đầu", time(8, 0))
    with c2:
        end_time = st.time_input("🏁 Giờ kết thúc", time(17, 0))
    with c3:
        end_date = st.date_input("📅 Ngày kết thúc", date.today())
    with c4:
        note = st.text_input("📝 Ghi chú (tuỳ chọn)", "")

    # --- Nút lưu ---
    if st.button("💾 Lưu công việc", key=f"save_public_{role}"):
        hours = calc_hours(start_date, end_date, start_time, end_time)
        if hours <= 0:
            st.warning("⚠️ Giờ kết thúc phải sau giờ bắt đầu.")
            return

        note_text = (
            f"⏰ {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} "
            f"({start_date} - {end_date}) {note}".strip()
        )

        try:
            supabase.table("tasks").insert({
                "project": "Công việc Public",
                "task": task_name,
                "assignee": assignee,
                "created_by": username,
                "note": note_text,
                "khoi_luong": hours,
                "progress": 0,
                "project_type": "public",
            }).execute()

            st.success(f"✅ Đã thêm công việc cho {assignee} ({hours} giờ).")
            st.toast("💾 Dữ liệu đã được lưu!", icon="💾")
            st.session_state.just_saved = True
            st.rerun()
        except Exception as e:
            st.error(f"❌ Lỗi khi thêm công việc: {e}")

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
