import os
import sys
import streamlit as st
import hashlib
import pandas as pd
import datetime
from datetime import date, datetime, time, timedelta
from supabase import create_client, Client
import re
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


# ==========================================================
# 🧩 CÔNG VIỆC GIÁN TIẾP — DÙNG CHUNG CHO ADMIN, USER, PROJECT
# ==========================================================

def show_indirect_task_form(role, supabase, username, users=None):
    """
    Hiển thị form giao việc gián tiếp (admin, user, project)
    """
    st.subheader("➕ Thêm công việc gián tiếp")

    with st.form(key=f"{role}_add_indirect"):
        task_name = st.text_input("Tên công việc")
        start_time = st.time_input("Giờ bắt đầu", datetime.time(8, 0))
        end_time = st.time_input("Giờ kết thúc", datetime.time(17, 0))
        note = st.text_area("Ghi chú")

        # Nếu là admin hoặc project manager thì có thể chọn người khác
        if role in ["admin", "project"]:
            assignee = st.selectbox("Người được giao", users)
        else:
            assignee = username

        submitted = st.form_submit_button("💾 Lưu công việc")

        if submitted:
            start_str = start_time.strftime("%H:%M")
            end_str = end_time.strftime("%H:%M")
            today = datetime.date.today()
            note_text = f"⏰ {start_str} - {end_str} ({today} - {today}) {note}".strip()

            # Tính khối lượng
            from auth import calc_hours
            hours = calc_hours(today, today, start_time, end_time)

            data = {
                "project": "Công việc gián tiếp",
                "task": task_name.strip(),
                "assignee": assignee,
                "note": note_text,
                "khoi_luong": round(hours, 2),
                "progress": 0,
                "created_by": username,
            }

            supabase.table("tasks").insert(data).execute()
            st.success(f"✅ Đã thêm công gián tiếp cho {assignee}")
            st.toast("💾 Đã lưu công việc gián tiếp!", icon="💾")
            st.session_state.just_saved = True


def show_indirect_task_table(role, supabase, username, df_tasks):
    """
    Hiển thị & cho phép chỉnh sửa công việc gián tiếp (chung cho admin/user/project)
    """
    st.subheader("🗂️ Danh sách công việc gián tiếp")

    df_show = df_tasks[df_tasks["project"] == "Công việc gián tiếp"].copy()
    if df_show.empty:
        st.info("Chưa có công việc gián tiếp nào.")
        return

    # --- Hàm tách giờ, ngày, note ---
    def split_times(note_text: str):
        if not isinstance(note_text, str):
            return "", "", "", ""
        block_re = r'⏰\s*(\d{1,2}:\d{2}(?::\d{2})?)\s*[-–]\s*(\d{1,2}:\d{2}(?::\d{2})?)'
        date_re  = r'\(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}\)'
        full_re  = rf'{block_re}\s*(?:{date_re})?'
        m = re.search(full_re, note_text)
        if not m:
            m = re.search(block_re, note_text)
        start = m.group(1) if m else ""
        end = m.group(2) if m else ""
        dm = re.search(date_re, note_text)
        date_part = dm.group(0) if dm else ""
        note_rest = re.sub(full_re, "", note_text).strip()
        return start, end, date_part, note_rest

    df_show[["Giờ bắt đầu", "Giờ kết thúc", "Ngày", "Ghi chú"]] = df_show["note"].apply(
        lambda x: pd.Series(split_times(x))
    )

    edited = st.data_editor(
        df_show[["task", "Giờ bắt đầu", "Giờ kết thúc", "Ghi chú", "khoi_luong"]],
        key=f"{role}_indirect_edit",
        use_container_width=True
    )

    if st.button("💾 Lưu thay đổi", key=f"{role}_save_indirect"):
        for i, row in edited.iterrows():
            task_id = int(df_show.iloc[i]["id"])
            update_data = {}
            start_time = row.get("Giờ bắt đầu", "")
            end_time = row.get("Giờ kết thúc", "")
            note_text = str(row.get("Ghi chú", "")).strip()
            date_part = df_show.iloc[i]["Ngày"]

            # Ghi chú mới
            if start_time and end_time:
                start_str = str(start_time)
                end_str = str(end_time)
                new_note = f"⏰ {start_str} - {end_str} {date_part} {note_text}".strip()
            else:
                new_note = note_text

            update_data["note"] = new_note

            # --- Tính lại khối lượng ---
            try:
                from auth import calc_hours
                today = datetime.date.today()
                hours = calc_hours(today, today, start_time, end_time)
                if hours > 0:
                    update_data["khoi_luong"] = round(hours, 2)
            except Exception as e:
                st.warning(f"Lỗi tính khối lượng: {e}")

            supabase.table("tasks").update(update_data).eq("id", task_id).execute()

        st.success("✅ Đã cập nhật công việc gián tiếp!")
        st.session_state.just_saved = True
