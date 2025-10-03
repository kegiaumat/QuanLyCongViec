import streamlit as st
import pandas as pd
import datetime
from streamlit_cookies_manager import EncryptedCookieManager


from auth import init_db, get_connection
from admin_app import admin_app
from project_manager_app import project_manager_app
from user_app import user_app   # nếu vẫn muốn dùng giao diện user thường
from auth import commit_and_sync
# ==================== HỖ TRỢ ====================


def init_default_admin():
    conn, c = get_connection()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            display_name TEXT,
            dob TEXT,
            password TEXT,
            role TEXT,
            last_seen TEXT
        )
    """)
    commit_and_sync(conn)
    conn.close()


def check_login(username, password):
    u = (username or "").strip().lower()
    p = password or ""

    # --- Tài khoản đặc biệt TDPRO ---
    if u == "tdpro" and p == "Giadinh12":
        return (0, "tdpro", "TDPRO", None, "Giadinh12", "admin")

    # --- Kiểm tra trong DB ---
    conn, c = get_connection()
    row = c.execute(
        "SELECT id, username, display_name, dob, password, role FROM users WHERE lower(username)=?",
        (u,)
    ).fetchone()
    conn.close()

    if row and str(row[4] or "") == p:
        return row
    return None


def logout_user():
    st.session_state.pop("user", None)
    st.session_state.pop("page", None)


def role_display(role: str) -> str:
    return {"admin": "Admin", "project_manager": "Quản lý dự án", "user": "Nhân viên"}.get(role, role.capitalize())


# ==================== TRANG HỒ SƠ ====================

def profile_page(user):
    st.title("👤 Hồ sơ cá nhân")
    conn, c = get_connection()

    st.subheader("Thông tin cơ bản")
    new_display = st.text_input("Tên hiển thị", value=user[2] or "", key="pf_display")

    current_dob = pd.to_datetime(user[3]) if user[3] else None
    new_dob = st.date_input(
        "Ngày sinh",
        value=datetime.date(1985, 11, 12),
        min_value=datetime.date(1950, 1, 1),
        max_value=datetime.date.today(),
        key="reg_dob"
    )

    if st.button("💾 Lưu thông tin", key="pf_save"):
        c.execute(
            "UPDATE users SET display_name=?, dob=? WHERE lower(username)=lower(?)",
            (new_display, new_dob.strftime("%Y-%m-%d") if new_dob else None, user[1])
        )
        commit_and_sync(conn)
        st.success("✅ Đã cập nhật hồ sơ.")
        user = list(user)
        user[2] = new_display
        user[3] = new_dob.strftime("%Y-%m-%d") if new_dob else None
        st.session_state["user"] = tuple(user)
        st.rerun()

    st.subheader("Đổi mật khẩu")
    old_pw = st.text_input("Mật khẩu hiện tại", type="password", key="pf_old_pw")
    new_pw = st.text_input("Mật khẩu mới", type="password", key="pf_new_pw")
    confirm_pw = st.text_input("Xác nhận mật khẩu mới", type="password", key="pf_cf_pw")

    if st.button("✅ Đổi mật khẩu", key="pf_change_pw"):
        db_pw = c.execute(
            "SELECT password FROM users WHERE lower(username)=lower(?)",
            (user[1],)
        ).fetchone()
        if not db_pw or db_pw[0] != old_pw:
            st.error("⚠️ Mật khẩu hiện tại không đúng.")
        elif new_pw != confirm_pw:
            st.error("⚠️ Mật khẩu mới và xác nhận không khớp.")
        else:
            c.execute(
                "UPDATE users SET password=? WHERE lower(username)=lower(?)",
                (new_pw, user[1])
            )
            commit_and_sync(conn)
            st.success("✅ Đã đổi mật khẩu. Vui lòng đăng nhập lại.")
            logout_user()
            st.rerun()

    conn.close()


# ==================== MAIN ====================

def main():
    st.set_page_config(page_title="Quản lý công việc", layout="wide", page_icon="🔑")
    # Cookie manager
    cookies = EncryptedCookieManager(
        prefix="myapp",   # prefix để phân biệt app
        password="supersecretkey"  # bạn đổi secret key tuỳ ý
    )
    if not cookies.ready():
        st.stop()
    st.markdown(
        """
        <style>
            .title-container {
                text-align: center;
                padding: 3px;
                margin-top: -50;
                position: relative;
                z-index: 1;
            }
            .title-container h1 {
                font-size: 35px;
                margin: 0;
                padding: 0;
                margin-top: -40px;
                color: #333;
            }
            .title-container h4 {
                font-size: 20px;
                font-weight: normal;
                margin-top: -5px;
                color: #555;
            }
        </style>
        <div class="title-container">
            <h1>PHẦN MỀM QUẢN LÝ CÔNG VIỆC</h1>
            <h4>XÍ NGHIỆP KHẢO SÁT THIẾT KẾ ĐƯỜNG 1</h4>
        </div>
        """, unsafe_allow_html=True
    )

    # Nếu chưa có session_state["user"] nhưng cookie có username thì tự login lại
    if "user" not in st.session_state and "username" in cookies:
        username = cookies["username"]
        # Lấy lại user từ DB để khôi phục session
        conn, c = get_connection()
        row = c.execute(
            "SELECT id, username, display_name, dob, password, role FROM users WHERE lower(username)=?",
            (username.lower(),)
        ).fetchone()
        conn.close()
        if row:
            st.session_state["user"] = row
            st.session_state["page"] = "home"

    if "user" not in st.session_state:
        tab_login, tab_register = st.tabs(["Đăng nhập", "Đăng ký"])

        with tab_login:
            username = st.text_input("Tên đăng nhập", key="login_username")
            password = st.text_input("Mật khẩu", type="password", key="login_password")
            if st.button("Đăng nhập", key="btn_login"):
                user = check_login(username, password)
                if user:
                    st.session_state["user"] = user
                    st.session_state["page"] = "home"
                    # Lưu username vào cookie
                    cookies["username"] = user[1]  # user[1] là username
                    cookies.save()
                    st.rerun()

                else:
                    st.error("⚠️ Sai tên đăng nhập hoặc mật khẩu")

        with tab_register:
            new_user = st.text_input("Tên đăng nhập mới", key="reg_username")
            new_display = st.text_input("Tên hiển thị", key="reg_display")
            new_dob = st.date_input("Ngày sinh", value=datetime.date(1985, 12, 11))
            new_pass = st.text_input("Mật khẩu", type="password", key="reg_password")
            confirm_pass = st.text_input("Nhập lại mật khẩu", type="password", key="reg_confirm_password")

            if st.button("Đăng ký", key="btn_register"):
                if not new_user or not new_pass or not confirm_pass:
                    st.warning("⚠️ Vui lòng nhập đầy đủ tên đăng nhập, mật khẩu và xác nhận mật khẩu")
                elif new_pass != confirm_pass:
                    st.error("⚠️ Mật khẩu nhập lại không khớp")
                else:
                    conn, c = get_connection()
                    try:
                        existed = c.execute(
                            "SELECT 1 FROM users WHERE lower(username)=lower(?)",
                            (new_user.strip(),)
                        ).fetchone()
                        if existed:
                            st.error("⚠️ Tên đăng nhập đã tồn tại.")
                        else:
                            c.execute(
                                "INSERT INTO users (username, display_name, dob, password, role) VALUES (?,?,?,?,?)",
                                (
                                    new_user.strip(),
                                    new_display or new_user.strip(),
                                    new_dob.strftime("%Y-%m-%d"),
                                    new_pass,
                                    "user",
                                )
                            )
                            commit_and_sync(conn)
                            st.success("✅ Đăng ký thành công! Hãy đăng nhập.")
                    finally:
                        conn.close()
    else:
        user = st.session_state["user"]
        role = user[5]
        current_page = st.session_state.get("page", "home")

        with st.sidebar:
            if st.sidebar.button(f"👋 Xin chào\n\n{user[2]} ({role_display(role)})", key="btn_goto_profile"):
                st.session_state["page"] = "profile"
                st.rerun()
            if current_page == "profile":
                if st.sidebar.button("⬅️ Quay lại trang chính", key="btn_back_home"):
                    st.session_state["page"] = "home"
                    st.rerun()
            if st.sidebar.button("🚪 Đăng xuất", key="btn_logout"):
                logout_user()
                # Xoá cookie
                cookies.pop("username")
                cookies.save()
                st.rerun()


        if current_page == "profile":
            profile_page(user)
        else:
            role = (user[5] or "")
            if "admin" in role.lower():
                admin_app(user)
            elif ("Chủ nhiệm dự án" in role) or ("Chủ trì dự án" in role) or ("project_manager" in role):
                project_manager_app(user)
            else:
                user_app(user)


if __name__ == "__main__":
    main()
