import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import datetime as dt
import json
from auth import get_connection, calc_hours, get_projects, add_user, hash_password, add_project
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode, DataReturnMode
import io  # đảm bảo có import này ở đầu file
import re
import time

# ====== CACHE DỮ LIỆU TỪ SUPABASE ======
@st.cache_data(ttl=15)
def load_users_cached():
    supabase = get_connection()
    data = supabase.table("users").select("id, stt, username, display_name, dob, role, project_manager_of, project_leader_of").order("stt").execute()

    return pd.DataFrame(data.data)

def load_users_fresh():
    supabase = get_connection()
    data = supabase.table("users").select("*").execute()
    return pd.DataFrame(data.data)
@st.cache_data(ttl=15)
def load_projects_cached():
    supabase = get_connection()
    data = supabase.table("projects").select("id, name, deadline, project_type, design_step").execute()
    return pd.DataFrame(data.data)

@st.cache_data(ttl=30)
def load_job_catalog_cached():
    supabase = get_connection()
    data = supabase.table("job_catalog").select("id, name, unit, parent_id, project_type").execute()
    return pd.DataFrame(data.data)

def refresh_all_cache():
    """Xóa cache và session_state khi có cập nhật thêm/xóa"""
    st.cache_data.clear()
    for k in ["users_df", "projects_df", "jobs_df"]:
        st.session_state.pop(k, None)


st.set_page_config(layout="wide")

def load_projects_fresh():
    supabase = get_connection()
    data = supabase.table("projects").select("id, name, deadline, project_type, design_step").execute()
    return pd.DataFrame(data.data)



# Hàm search: lọc options theo query gõ vào
def search_units(query: str):
    options = ["Km", "m", "cái", "Công"]
    # Khi chưa gõ gì → trả về tất cả
    if not query:
        return options
    return [o for o in options if query.lower() in o.lower()]

def update_last_seen(username):
    supabase = get_connection()
    supabase.table("users").update({"last_seen": datetime.datetime.now().isoformat()}).eq("username", username).execute()

    

@st.cache_resource
def get_supabase_client():
    return get_connection()

def admin_app(user):
    supabase = get_supabase_client()

    # 🔹 Tải dữ liệu có cache
    if "df_users" not in st.session_state:
        st.session_state["df_users"] = load_users_cached()
    if "df_projects" not in st.session_state:
        st.session_state["df_projects"] = load_projects_cached()
    if "df_jobs" not in st.session_state:
        st.session_state["df_jobs"] = load_job_catalog_cached()

    df_users = st.session_state["df_users"]
    df_projects = st.session_state["df_projects"]
    df_jobs = st.session_state["df_jobs"]

    # --- Map username -> display_name ---
    user_map = dict(zip(df_users["username"], df_users["display_name"]))


    # ✅ cập nhật trạng thái online (last_seen)
    # ✅ Cập nhật thời gian đăng nhập nếu có user
    try:
        current_user = user if user else st.session_state.get("username") or st.session_state.get("user")
        if current_user:
            supabase.table("users").update({
                "last_seen": datetime.datetime.now().isoformat()
            }).eq("username", current_user).execute()
        else:
            print("⚠️ Không thể cập nhật last_seen vì chưa xác định user.")
    except Exception as e:
        print(f"⚠️ Lỗi khi cập nhật last_seen: {e}")


    

    menu = ["Quản lý người dùng", "Mục lục công việc", "Quản lý dự án", "Quản lý Giao Việc", "Chấm công – Nghỉ phép", "Thống kê công việc"]


    choice = st.sidebar.radio("Chức năng", menu)
    if choice == "Quản lý người dùng":
        st.subheader("👥 Quản lý user")

        # === Chỉ tải lại nếu chưa có trong session (để tránh nhảy bảng) ===
        if "df_users" not in st.session_state or "df_projects" not in st.session_state:
            st.session_state.df_users = load_users_cached()
            st.session_state.df_projects = load_projects_cached()

        df_users = st.session_state.df_users.copy()
        df_projects = st.session_state.df_projects.copy()
        supabase = get_supabase_client()

        # === Chuẩn hóa cột ===
        # === Chuẩn hóa cột từ database ===
        df_users = df_users.rename(columns={
            "username": "Tên đăng nhập",
            "display_name": "Tên hiển thị",
            "dob": "Ngày sinh",
            "role": "Vai trò",
            "project_manager_of": "Chủ nhiệm dự án",
            "project_leader_of": "Chủ trì dự án",
            "stt": "STT"
        })
        # ✅ Nếu DB chưa có cột STT thì tự tạo STT tăng dần
        if "STT" not in df_users.columns:
            df_users["STT"] = range(1, len(df_users) + 1)
        # ✅ Đưa cột STT lên đầu
        cols = ["STT"] + [c for c in df_users.columns if c != "STT"]
        df_users = df_users[cols]
        # ✅ Xóa hoàn toàn cột ID để không xuất hiện nữa
        df_users = df_users.drop(columns=["id"], errors="ignore")

        # ✅ Sắp xếp theo STT
        df_users = df_users.sort_values("STT").reset_index(drop=True)

        # ✅ Thêm cột Xóa? nếu chưa có
        if "Xóa?" not in df_users.columns:
            df_users["Xóa?"] = False


        # === Dữ liệu cho selectbox ===
        role_options = ["user", "admin", "Chủ nhiệm dự án", "Chủ trì dự án"]
        project_options = df_projects["name"].dropna().tolist()

        # === Chuẩn hóa dữ liệu ===
        df_users["Ngày sinh"] = pd.to_datetime(df_users["Ngày sinh"], errors="coerce").dt.date
        df_users["Xóa?"] = df_users["Xóa?"].fillna(False).astype(bool)
        # 🧹 Chuẩn hóa dữ liệu vai trò và danh sách dự án
        for col in ["Vai trò", "Chủ nhiệm dự án", "Chủ trì dự án"]:
            df_users[col] = df_users[col].astype(str).fillna("")

        # ✅ Chuyển dữ liệu dự án từ chuỗi -> danh sách (để MultiSelectColumn hiểu)
        for col in ["Chủ nhiệm dự án", "Chủ trì dự án"]:
            df_users[col] = df_users[col].apply(lambda x: x.split("|") if x else [])


        # === Bảng chỉnh sửa ===
        edited_users = st.data_editor(
            df_users,
            width="stretch",
            hide_index=True,
            key="user_editor",
            column_config={
                 "STT": st.column_config.NumberColumn("STT", min_value=1, step=1),
                # ✅ Không cho sửa tên đăng nhập
                "Tên đăng nhập": st.column_config.TextColumn(
                    "Tên đăng nhập",
                    disabled=True,
                    help="Không thể chỉnh sửa tên đăng nhập"
                ),
                "Tên hiển thị": st.column_config.TextColumn("Tên hiển thị"),
                "Ngày sinh": st.column_config.DateColumn("Ngày sinh", format="YYYY-MM-DD"),
                "Vai trò": st.column_config.MultiselectColumn(
                    "Vai trò",
                    options=role_options,
                    help="Có thể chọn nhiều vai trò (user, admin, Chủ nhiệm dự án, Chủ trì dự án)"
                ),
                "Chủ nhiệm dự án": st.column_config.MultiselectColumn("Chủ nhiệm dự án", options=project_options),
                "Chủ trì dự án": st.column_config.MultiselectColumn("Chủ trì dự án", options=project_options),

                "Xóa?": st.column_config.CheckboxColumn("Xóa?", help="Tick để đánh dấu user cần xoá")
            }
        )

        # col1, col2 = st.columns(2)
        col1, col2 = st.columns([1,1])
        # === Nút cập nhật ===
        with col1:

            if st.button("💾 Update", key="btn_update_user"):
                changed_count = 0

                for i, row in edited_users.iterrows():
                    username = row["Tên đăng nhập"]
                    original = df_users.loc[df_users["Tên đăng nhập"] == username].iloc[0]
                    update_data = {}

                    for col, db_field in [
                        ("STT", "stt"),
                        ("Tên hiển thị", "display_name"),
                        ("Ngày sinh", "dob"),
                        ("Vai trò", "role"),
                        ("Chủ nhiệm dự án", "project_manager_of"),
                        ("Chủ trì dự án", "project_leader_of"),
                    ]:
                        new_val = row[col]
                        old_val = original[col]

                        # Chuẩn hóa list -> string
                        if isinstance(new_val, list):
                            new_val = "|".join(map(str, new_val))
                        if isinstance(old_val, list):
                            old_val = "|".join(map(str, old_val))

                        # Chuẩn hóa None, NaN, 'None', rỗng
                        def clean_value(v):
                            if pd.isna(v) or v in ["None", "nan", "", None, "NaT"]:
                                return None
                            return str(v).strip()

                        new_val = clean_value(new_val)
                        old_val = clean_value(old_val)

                        # So sánh sâu bằng json để loại bỏ khác kiểu (vd "1" vs 1)
                        if json.dumps(new_val, ensure_ascii=False) != json.dumps(old_val, ensure_ascii=False):
                            update_data[db_field] = new_val

                    # ✅ Chỉ update nếu có thay đổi
                    if update_data:
                        try:
                            supabase.table("users").update(update_data).eq("username", username).execute()
                            changed_count += 1
                        except Exception as e:
                            st.error(f"⚠️ Lỗi khi cập nhật {username}: {e}")

                if changed_count > 0:
                    st.success(f"✅ Đã cập nhật {changed_count} user có thay đổi.")
                    refresh_all_cache()
                    st.session_state.df_users = load_users_cached()
                else:
                    st.info("ℹ️ Không có user nào thay đổi, không cần cập nhật.")




        # === Nút xóa ===
        with col2:
            # ✅ Khởi tạo tránh lỗi
            if "confirm_delete" not in st.session_state:
                st.session_state.confirm_delete = False

            if st.button("❌ Xóa user", key="btn_delete_user"):
                to_delete = edited_users[edited_users["Xóa?"] == True]
                if to_delete.empty:
                    st.warning("⚠️ Bạn chưa tick user nào để xoá.")
                else:
                    st.session_state.to_delete = to_delete
                    st.session_state.confirm_delete = True

            # ✅ Sử dụng get() để tránh lỗi AttributeError
            if st.session_state.get("confirm_delete", False):
                to_delete = st.session_state.to_delete
                st.error(f"⚠️ Bạn có chắc muốn xoá {len(to_delete)} user: "
                         f"{', '.join(to_delete['Tên hiển thị'].tolist())}?")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Yes, xoá ngay"):
                        for _, row in to_delete.iterrows():
                            supabase.table("users").delete().eq("username", row["Tên đăng nhập"]).execute()
                        st.success("🗑️ Đã xoá user được chọn")
                        refresh_all_cache()
                        st.session_state.df_users = load_users_cached()

                        st.session_state.confirm_delete = False
                        st.rerun()

                with c2:
                    if st.button("❌ No, huỷ"):
                        st.info("Đã huỷ thao tác xoá")
                        st.session_state.confirm_delete = False


        st.divider()
        st.subheader("🔐 Đổi mật khẩu User")

        # Danh sách user
        user_list = df_users["Tên đăng nhập"].tolist()
        selected_user = st.selectbox("Chọn user", user_list, key="select_user_password")

        new_password = st.text_input("Nhập mật khẩu mới", type="password", key="new_pw")

        if st.button("✅ Đổi mật khẩu", key="btn_change_pw"):
            if not new_password:
                st.warning("⚠️ Bạn chưa nhập mật khẩu mới!")
            else:
                try:
                    hashed = hash_password(new_password)
                    supabase.table("users").update({
                        "password": hashed
                    }).eq("username", selected_user).execute()

                    st.success(f"✅ Đã đổi mật khẩu cho user **{selected_user}** ✔️")
                    time.sleep(1)
                    st.rerun()

                except Exception as e:
                    st.error(f"⚠️ Lỗi khi đổi mật khẩu: {e}")
            
    elif choice == "Mục lục công việc":
        st.subheader("📚 Mục lục công việc")

        # =======================
        # 1) THÊM CÔNG VIỆC MỚI
        # =======================
        st.markdown("#### ➕ Thêm công việc mới")

        jobs_all = df_jobs.copy()

        parent_jobs = jobs_all[jobs_all["parent_id"].isnull()].sort_values("name")

        col1, col2, col3, col4 = st.columns([2, 1, 2, 1])
        with col1:
            new_job = st.text_input("Tên công việc", placeholder="Nhập tên công việc…")
        with col2:
            new_unit = st.text_input("Đơn vị", placeholder="Ví dụ: m, Km, cái, Công…")
        with col3:
            parent_options = ["— Không chọn (tạo Đầu mục công việc) —"] + parent_jobs["name"].tolist()
            parent_choice = st.selectbox("Thuộc công việc lớn", parent_options)
        with col4:
            new_project_type = st.selectbox("Nhóm dự án", ["public", "group"], index=1)

        if st.button("➕ Thêm vào mục lục"):
            try:
                parent_id = None
                if parent_choice != "— Không chọn (tạo Đầu mục công việc) —":
                    parent_id = int(parent_jobs[parent_jobs["name"] == parent_choice]["id"].iloc[0])
                
                supabase.table("job_catalog").insert({
                    "name": new_job.strip(),
                    "unit": new_unit.strip() if new_unit else None,
                    "parent_id": parent_id,
                    "project_type": new_project_type
                }).execute()
                
                st.success(f"✅ Đã thêm: {new_job} ({new_unit}, {new_project_type})"
                           + (f" → thuộc '{parent_choice}'" if parent_id else ""))
                refresh_all_cache()
            except Exception as e:
                if "duplicate key" in str(e).lower():
                    st.error(f"⚠️ Công việc '{new_job}' đã tồn tại")
                else:
                    st.error(f"⚠️ Lỗi khác: {e}")


        st.divider()


        # ======================================
        # 2) HIỂN THỊ & CHỈNH SỬA CHA – CON – ĐƠN VỊ – NHÓM DỰ ÁN (AG-GRID)
        # ======================================

        jobs = df_jobs.copy()

        if jobs.empty:
            st.info("⚠️ Chưa có công việc nào trong mục lục")
        else:

            # ===== CHUẨN BỊ BẢNG CHA – CON =====
            rows = []
            for _, p in jobs[jobs["parent_id"].isnull()].iterrows():

                rows.append({
                    "Cha": p["name"],
                    "Con": "",
                    "Đơn vị": p["unit"] or "",
                    "Nhóm dự án": p["project_type"] or "group",
                    "Xóa?": False,
                    "_id": p["id"],
                    "_is_parent": True,
                    "_orig_name": p["name"]
                })

                children = jobs[jobs["parent_id"] == p["id"]]
                for _, c in children.iterrows():
                    rows.append({
                        "Cha": "",
                        "Con": c["name"],
                        "Đơn vị": c["unit"] or "",
                        "Nhóm dự án": c["project_type"] or "group",
                        "Xóa?": False,
                        "_id": c["id"],
                        "_is_parent": False,
                        "_orig_name": c["name"]
                    })

            df_display = pd.DataFrame(rows)
            meta_cols = [c for c in df_display.columns if c.startswith("_")]

            # -----------------------------
            # CONFIG AGGRID
            # -----------------------------
            gb = GridOptionsBuilder.from_dataframe(df_display)

            # Cho phép sửa trực tiếp
            gb.configure_columns(
                ["Cha", "Con", "Đơn vị", "Nhóm dự án"],
                editable=True,
            )

            # Checkbox xoá
            gb.configure_column("Xóa?", editable=True)

            # Ẩn cột metadata
            for col in meta_cols:
                gb.configure_column(col, hide=True)

            # Tô màu dòng cha
            gb.configure_row_style(
                js_code="""
                    function(params) {
                        if (params.data._is_parent){
                            return {'backgroundColor': '#e8f4ff'};
                        }
                        return {};
                    }
                """
            )

            grid_options = gb.build()

            st.markdown("### ✏️ Danh sách công việc – AG Grid (Editable)")

            grid = AgGrid(
                df_display,
                gridOptions=grid_options,
                update_mode=GridUpdateMode.NO_UPDATE,   # ❗ KHÔNG RERUN KHI EDIT
                allow_unsafe_jscode=True,
                fit_columns_on_grid_load=True,
                height=500
            )

            edited = grid["data"]        # bản cập nhật không gây rerun
            selected = [r for r in edited if r["Xóa?"]]

            # ======================================
            # 3) HAI NÚT: CẬP NHẬT & XOÁ
            # ======================================
            col1, col2 = st.columns([1,1])

            # ====================
            # NÚT CẬP NHẬT
            # ====================
            with col1:
                if st.button("💾 Cập nhật mục lục"):

                    full = pd.DataFrame(edited)

                    for _, row in full.iterrows():
                        job_id = int(row["_id"])
                        old_name = row["_orig_name"]

                        new_name = row["Cha"] if row["_is_parent"] else row["Con"]
                        new_unit = row["Đơn vị"]
                        new_project_type = row["Nhóm dự án"]

                        if not new_name:
                            continue

                        try:
                            supabase.table("job_catalog").update({
                                "name": new_name,
                                "unit": new_unit or None,
                                "project_type": new_project_type
                            }).eq("id", job_id).execute()

                            if new_name != old_name:
                                # cập nhật tasks liên quan
                                supabase.table("tasks").update({"task": new_name}).eq("task", old_name).execute()

                        except Exception as e:
                            st.error(f"⚠️ Lỗi khi cập nhật {old_name}: {e}")

                    st.success("✔ Đã cập nhật mục lục công việc")
                    refresh_all_cache()

            # ====================
            # NÚT XOÁ
            # ====================
            with col2:
                if st.button("❌ Xóa công việc đã chọn"):
                    if not selected:
                        st.warning("⚠️ Bạn chưa tick công việc nào để xoá")
                    else:
                        st.session_state["confirm_delete_jobs"] = selected

            # ============================
            # POPUP XÁC NHẬN XOÁ
            # ============================
            if "confirm_delete_jobs" in st.session_state:
                to_delete = pd.DataFrame(st.session_state["confirm_delete_jobs"])

                st.error(
                    f"⚠️ Bạn có chắc muốn xoá {len(to_delete)} công việc: "
                    f"{', '.join(to_delete['Cha'] + to_delete['Con'])}?"
                )

                c1, c2 = st.columns(2)

                with c1:
                    if st.button("✔ Yes, xoá ngay"):
                        for _, row in to_delete.iterrows():
                            job_id = int(row["_id"])
                            job_name = row["_orig_name"]

                            supabase.table("tasks").delete().eq("task", job_name).execute()
                            supabase.table("job_catalog").delete().eq("id", job_id).execute()

                        st.success("🗑️ Đã xoá các công việc được chọn")
                        del st.session_state["confirm_delete_jobs"]
                        refresh_all_cache()

                with c2:
                    if st.button("❌ No, huỷ"):
                        st.info("Đã huỷ thao tác xoá")
                        del st.session_state["confirm_delete_jobs"]



    elif choice == "Quản lý dự án":
        st.subheader("🗂️ Quản lý dự án")

        # ===== Thêm dự án mới =====
        project_name = st.text_input("Tên dự án mới")
        project_deadline = st.date_input("Deadline dự án")
        project_type = st.selectbox("Nhóm dự án", ["public", "group"], index=1)
        design_step = st.selectbox("Bước thiết kế", [
            "Lập DA", "TKKT", "BVTC (2 bước)", "BVTC (3 bước)", "Báo cáo KTKT", "Hồ sơ mời thầu"
        ])


        if st.button("➕ Thêm dự án", key="add_project_btn"):
            try:
                add_project(project_name, project_deadline, project_type, design_step)
                st.success(f"✅ Đã thêm dự án: {project_name}")
                refresh_all_cache()
                st.session_state["df_projects"] = load_projects_fresh()
                df_projects = st.session_state["df_projects"].copy()
                st.rerun()


            except Exception as e:
                if "duplicate key" in str(e).lower():
                    st.error("⚠️ Dự án đã tồn tại")
                else:
                    st.error(f"⚠️ Lỗi: {e}")


        # ===== Đọc danh sách dự án và tính tổng thanh toán =====
        df_proj = df_projects.copy()



        if not df_proj.empty:
            # Tính tổng % thanh toán của mỗi dự án

            # 👉 Tự tính tổng % thanh toán của mỗi dự án (không cần hàm SQL trong Supabase)
            data = supabase.table("payments").select("project_id, percent").execute()
            df_pay_total = pd.DataFrame(data.data) if data.data else pd.DataFrame(columns=["project_id", "percent"])
            df_pay_total = df_pay_total.groupby("project_id", as_index=False)["percent"].sum()
            df_pay_total.rename(columns={"percent": "total_paid"}, inplace=True)

            df_proj = df_proj.merge(df_pay_total, how="left", left_on="id", right_on="project_id")
            df_proj["total_paid"] = df_proj["total_paid"].astype(float).fillna(0)


            # Chuẩn hóa dữ liệu
            df_proj["deadline"] = pd.to_datetime(df_proj["deadline"], errors="coerce").dt.date
            df_proj["project_type"] = df_proj["project_type"].fillna("group")
            df_proj.rename(columns={"total_paid": "Tổng thanh toán (%)"}, inplace=True)

            # Thêm cột Xóa?
            df_proj["Xóa?"] = False
            df_display = df_proj.drop(columns=["id", "project_id"]).copy()

            st.write("### 📋 Danh sách dự án")
            edited_proj = st.data_editor(
                df_display,
                width="stretch",
                key="proj_editor_main",
                column_config={
                    "name": st.column_config.TextColumn("Tên dự án"),
                    "deadline": st.column_config.DateColumn("Deadline", format="YYYY-MM-DD"),
                    "project_type": st.column_config.SelectboxColumn("Nhóm dự án", options=["public", "group"]),
                    "design_step": st.column_config.SelectboxColumn("Bước thiết kế", options=[
                        "Lập DA", "TKKT", "BVTC (2 bước)", "BVTC (3 bước)", "Báo cáo KTKT", "Hồ sơ mời thầu"
                    ]),
                    "Tổng thanh toán (%)": st.column_config.NumberColumn("Tổng thanh toán (%)", disabled=True),
                    "Xóa?": st.column_config.CheckboxColumn("Xóa?", help="Tick để xoá"),
                }
            )


            col1, col2 = st.columns(2)

            # ===== Cập nhật =====
            with col1:
                if st.button("💾 Cập nhật dự án", key="update_project_btn"):
                    for idx, row in edited_proj.iterrows():
                        row_id   = int(df_proj.loc[idx, "id"])
                        old_name = df_proj.loc[idx, "name"]

                        # Chuẩn hoá deadline
                        dl = row["deadline"]
                        if pd.isna(dl):
                            dl_str = None
                        else:
                            dl_str = pd.to_datetime(dl, errors="coerce")
                            dl_str = dl_str.strftime("%Y-%m-%d") if pd.notna(dl_str) else None

                        # Update project
                        supabase.table("projects").update({
                            "name": row["name"],
                            "deadline": dl_str,
                            "project_type": row["project_type"],
                            "design_step": row["design_step"]
                        }).eq("id", row_id).execute()


                        # Nếu đổi tên dự án → cập nhật tasks + users
                        if row["name"] != old_name:
                            supabase.table("tasks").update({"project": row["name"]}).eq("project", old_name).execute()
                            for colu in ("project_manager_of", "project_leader_of"):
                                
                                data_users = supabase.table("users").select(f"username, {colu}").not_.is_(colu, None).execute()
                                for user in data_users.data:
                                    username = user["username"]
                                    csv_vals = user.get(colu) or ""
                                    parts = [p.strip() for p in re.split(r"[|,]", csv_vals) if p.strip()]
                                    changed = False
                                    for i, p in enumerate(parts):
                                        if p == old_name:
                                            parts[i] = row["name"]
                                            changed = True
                                    if changed:
                                        new_csv = ",".join(parts) if parts else None
                                        supabase.table("users").update({colu: new_csv}).eq("username", username).execute()


                    
                    st.success("✅ Đã cập nhật thông tin dự án")
                    refresh_all_cache()

            # ===== Xóa dự án =====
            with col2:
                # Dùng biến session để nhớ trạng thái xác nhận
                if "confirm_delete" not in st.session_state:
                    st.session_state["confirm_delete"] = None

                if st.button("❌ Xóa dự án", key="delete_project_btn"):
                    to_delete = edited_proj[edited_proj["Xóa?"] == True]
                    if to_delete.empty:
                        st.warning("⚠️ Bạn chưa tick dự án nào để xoá.")
                    else:
                        st.session_state["confirm_delete"] = to_delete["name"].tolist()

            # Hiển thị xác nhận chỉ khi người dùng vừa bấm nút và có dữ liệu
            if st.session_state.get("confirm_delete"):
                proj_list = st.session_state["confirm_delete"]
                proj_names = ", ".join(map(str, proj_list))
                st.error(f"⚠️ Bạn có chắc muốn xoá {len(proj_list)} dự án sau: {proj_names} ?")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Yes, xoá ngay", key="confirm_delete_yes"):
                        for proj_name in proj_list:
                            supabase.table("tasks").delete().eq("project", proj_name).execute()
                            supabase.table("projects").delete().eq("name", proj_name).execute()

                            # Cập nhật lại trường project_manager_of / project_leader_of trong users
                            for colu in ("project_manager_of", "project_leader_of"):
                                data_users = supabase.table("users").select(f"username, {colu}").not_.is_(colu, None).execute()
                                for user in data_users.data:
                                    username = user["username"]
                                    csv_vals = user.get(colu) or ""
                                    parts = [p.strip() for p in re.split(r"[|,]", csv_vals) if p.strip()]
                                    parts = [p for p in parts if p != proj_name]
                                    new_csv = ",".join(parts) if parts else None
                                    supabase.table("users").update({colu: new_csv}).eq("username", username).execute()

                        st.success("🗑️ Đã xoá các dự án được chọn.")
                        refresh_all_cache()
                        st.session_state["df_projects"] = load_projects_fresh()
                        st.session_state["confirm_delete"] = None
                        df_projects = st.session_state["df_projects"].copy()
                        st.rerun()


                with c2:
                    if st.button("❌ No, huỷ", key="confirm_delete_no"):
                        st.info("Đã huỷ thao tác xoá.")
                        st.session_state["confirm_delete"] = None

        else:
            st.info("⚠️ Chưa có dự án nào")

        # ===== Quản lý thanh toán =====
        st.divider()
        st.markdown("### 💳 Quản lý thanh toán cho dự án")

        if not df_proj.empty:
            proj_options = df_proj["name"].tolist()
            selected_proj = st.selectbox("Chọn dự án để xem/nhập thanh toán", proj_options, key="select_proj_for_payment")
            proj_id = int(df_proj.loc[df_proj["name"] == selected_proj, "id"].iloc[0])

            
            data = supabase.table("payments").select("id, payment_number, percent, note, paid_at").eq("project_id", proj_id).order("payment_number").execute()
            df_pay = pd.DataFrame(data.data)

            st.write("#### Danh sách thanh toán")
            if df_pay.empty:
                st.info("Chưa có thông tin thanh toán nào")
                total_paid = 0
            else:
                total_paid = df_pay["Tỉ lệ (%)"].sum()
                st.dataframe(df_pay, width="stretch")
                st.success(f"💵 Tổng đã thanh toán: **{total_paid:.1f}%**")

            st.write("#### ➕ Thêm lần thanh toán mới")

            # 👉 Gom 4 input vào cùng 1 hàng
            col1, col2, col3, col4 = st.columns([1, 1, 2, 2])
            with col1:
                next_num = (df_pay["Lần thanh toán"].max() + 1) if not df_pay.empty else 1
                pay_num = st.number_input("Lần", value=int(next_num), step=1, min_value=1, key="pay_num")
            with col2:
                pay_percent = st.number_input("%", min_value=0.0, max_value=100.0, step=0.1, key="pay_percent")
            with col3:
                pay_note = st.text_input("Ghi chú", key="pay_note")
            with col4:
                pay_date = st.date_input("Ngày", key="pay_date")

            if st.button("💾 Lưu lần thanh toán", key="save_payment_btn"):
                if total_paid + pay_percent > 100:
                    st.warning("⚠️ Tổng thanh toán sẽ vượt quá 100%!")
                
                supabase.table("payments").insert({
                    "project_id": proj_id,
                    "payment_number": pay_num,
                    "percent": pay_percent,
                    "note": pay_note,
                    "paid_at": pay_date.strftime("%Y-%m-%d")
                }).execute()
                
                st.success("✅ Đã thêm lần thanh toán mới")
                st.rerun()

   
 


    elif choice == "Quản lý Giao Việc":
        st.subheader("📝 Giao việc")

        # --- Lấy danh sách dự án ---
        projects = df_projects[["id", "name", "deadline", "project_type"]].copy()

        if projects.empty:
            st.info("⚠️ Chưa có dự án nào.")
            st.stop()

        project = st.selectbox("Chọn dự án", projects["name"].tolist())
        prow = projects.loc[projects["name"] == project].iloc[0]
        proj_deadline = prow["deadline"]
        proj_type = (prow["project_type"] or "group").strip().lower()

        # --- Đồng bộ dữ liệu cũ: NULL -> 'group' ---
        
        if "fixed_job_catalog" not in st.session_state:
            supabase.table("job_catalog").update({"project_type": "group"}).is_("project_type", None).execute()
            st.session_state["fixed_job_catalog"] = True
        

        # --- Lọc job_catalog theo project_type ---
        jobs = df_jobs[df_jobs["project_type"] == proj_type][["id", "name", "unit", "parent_id"]].copy()


        users_display = df_users["display_name"].tolist()
        assignee_display = st.selectbox("Giao việc cho", users_display)
        assignee = df_users.loc[df_users["display_name"] == assignee_display, "username"].iloc[0]


        # ======== Đầu mục công việc ========
        parent_jobs = jobs[jobs["parent_id"].isnull()].sort_values("name")
        parent_options = parent_jobs["name"].tolist()



        # ========== FORM GIAO VIỆC ==========
        if proj_type == "public":
            # -------- Form mới cho dự án public (công nhật) --------
            st.markdown("### ➕ Giao công nhật (Public)")

            if "task_rows" not in st.session_state:
                st.session_state.task_rows = [0]

            h1, h2, h3, h4, h5 = st.columns([2,2,2,2,2])
            h1.markdown("**Công việc**")
            h2.markdown("**Ngày bắt đầu**")
            h3.markdown("**Giờ bắt đầu**")
            h4.markdown("**Ngày kết thúc**")
            h5.markdown("**Giờ kết thúc**")

            for i, _ in enumerate(st.session_state.task_rows):
                c1, c2, c3, c4, c5 = st.columns([2,2,2,2,2])
                

                with c1:
                    task_choice = st.selectbox(
                        "", jobs["name"].tolist(),
                        key=f"pub_task_{i}", label_visibility="collapsed"
                    )
                with c2:
                    start_date = st.date_input("", key=f"pub_start_date_{i}", label_visibility="collapsed")
                with c3:
                    start_time = st.time_input("", datetime.time(8, 0), key=f"pub_start_time_{i}", label_visibility="collapsed")
                with c4:
                    end_date = st.date_input("", key=f"pub_end_date_{i}", value=start_date,
                                             label_visibility="collapsed")
                with c5:
                    # Đảm bảo sử dụng datetime.time(17, 0) thay vì pd.to_datetime("17:00").time()
                    end_time = st.time_input("", datetime.time(17, 0),  # Đã thay đổi đây
                                             key=f"pub_end_time_{i}", label_visibility="collapsed")


            st.button("➕ Thêm dòng", key="pub_add_row",
                      on_click=lambda: st.session_state.task_rows.append(len(st.session_state.task_rows)))

            pub_note = st.text_area("📝 Ghi chú chung", key="pub_note")

            if st.button("✅ Giao việc", key="pub_assign_btn"):
                for i in range(len(st.session_state.task_rows)):
                    task = st.session_state.get(f"pub_task_{i}")
                    if not task:
                        continue
                    s_date = st.session_state.get(f"pub_start_date_{i}")
                    e_date = st.session_state.get(f"pub_end_date_{i}")
                    s_time = st.session_state.get(f"pub_start_time_{i}")
                    e_time = st.session_state.get(f"pub_end_time_{i}")
                    total_hours = calc_hours(s_date, e_date, s_time, e_time)

                    # ✅ Ghi chú chuẩn định dạng, dùng biến pub_note
                    note_txt = f"⏰ {s_time.strftime('%H:%M')} - {e_time.strftime('%H:%M')} ({s_date} - {e_date})"
                    if pub_note:
                        note_txt += f" {pub_note}"

                    supabase.table("tasks").insert({
                        "project": project,
                        "task": task,
                        "assignee": assignee,
                        "start_date": s_date,
                        "khoi_luong": total_hours,
                        "note": note_txt,
                        "progress": 0,
                        "approved": False
                    }).execute()


                st.success("✅ Đã giao công nhật")
                st.session_state.task_rows = [0]
                st.rerun()


        else:
            # -------- Form cũ cho dự án KHÔNG phải public --------
            if "task_rows" not in st.session_state:
                st.session_state.task_rows = [0]

            col = st.columns([2,2,2,2,2])
            col[0].markdown("**Đầu mục công việc**")
            col[1].markdown("**Công việc chi tiết**")

            # đặt header 3 cột còn lại theo đơn vị của dòng mẫu
            first_unit = ""
            if parent_options:
                parent_choice0 = parent_options[0]
                if parent_choice0 in jobs["name"].values:
                    first_unit = jobs.loc[jobs["name"] == parent_choice0, "unit"].iloc[0] or ""

            if first_unit.strip().lower() == "công":
                col[2].markdown("**Giờ bắt đầu**")
                col[3].markdown("**Giờ kết thúc**")
                col[4].markdown("—")
            else:
                col[2].markdown("**Khối lượng**")
                col[3].markdown("**Đơn vị**")
                col[4].markdown("**Deadline**")

            # các dòng nhập
            for i, _ in enumerate(st.session_state.task_rows):
                c1, c2, c3, c4, c5 = st.columns([2,2,2,2,2])

                with c1:
                    parent_choice = st.selectbox("", parent_options, key=f"parent_{i}",
                                                 label_visibility="collapsed")

                pid = parent_jobs.loc[parent_jobs["name"] == parent_choice, "id"]
                pid = int(pid.iloc[0]) if not pid.empty else None
                child_jobs = jobs[jobs["parent_id"] == pid].sort_values("name") if pid else pd.DataFrame()

                with c2:
                    child_choice = st.selectbox(
                        "", child_jobs["name"].tolist() if not child_jobs.empty else [],
                        key=f"child_{i}", label_visibility="collapsed"
                    )

                task_name = child_choice if child_choice else parent_choice
                unit = jobs.loc[jobs["name"] == task_name, "unit"].iloc[0] if task_name in jobs["name"].values else ""

                if unit.strip().lower() == "công":
                    with c3:
                        st.time_input("", value=pd.to_datetime("08:00").time(),
                                      key=f"start_{i}", label_visibility="collapsed")
                    with c4:
                        st.time_input("", value=pd.to_datetime("17:00").time(),
                                      key=f"end_{i}", label_visibility="collapsed")
                    c5.markdown("—")
                else:
                    with c3:
                        st.number_input("", min_value=0.0, step=0.1,
                                        key=f"khoi_luong_{i}", label_visibility="collapsed")
                    with c4:
                        st.text_input("", value=unit, key=f"unit_{i}",
                                      disabled=True, label_visibility="collapsed")
                    with c5:
                        default_deadline = pd.to_datetime(proj_deadline) if proj_deadline else None
                        st.date_input("", value=default_deadline,
                                      key=f"deadline_{i}", label_visibility="collapsed")

            group_note = st.text_area("📝 Ghi chú chung", key="group_note")

            if st.button("✅ Giao việc", key="assign_group_btn", disabled=not parent_options):
                for i in range(len(st.session_state.task_rows)):
                    parent_choice = st.session_state.get(f"parent_{i}")
                    child_choice = st.session_state.get(f"child_{i}")
                    task = child_choice if child_choice else parent_choice
                    if not task:
                        continue

                    unit = jobs.loc[jobs["name"] == task, "unit"].iloc[0] if task in jobs["name"].values else ""
                    if unit.strip().lower() == "công":
                        start_time = st.session_state.get(f"start_{i}")
                        end_time = st.session_state.get(f"end_{i}")
                        time_txt = f"⏰ {start_time} - {end_time}" if start_time and end_time else ""
                        merged_note = (group_note + ("\n" if group_note and time_txt else "") + time_txt).strip()
                        
                        supabase.table("tasks").insert({
                            "project": project,
                            "task": task,
                            "assignee": assignee,
                            "note": merged_note,  # hoặc group_note
                            "progress": 0
                        }).execute()
                    else:
                        qty = float(st.session_state.get(f"khoi_luong_{i}", 0) or 0)
                        dl_val = st.session_state.get(f"deadline_{i}")
                        dl = pd.to_datetime(dl_val, errors="coerce")
                        dl_str = dl.strftime("%Y-%m-%d") if pd.notna(dl) else None
                        
                        supabase.table("tasks").insert({
                            "project": project,
                            "task": task,
                            "assignee": assignee,
                            "deadline": dl_str,
                            "khoi_luong": qty,
                            "note": group_note,
                            "progress": 0
                        }).execute()
                
                st.success("✅ Đã giao việc")
                st.session_state.task_rows = [0]
                st.rerun()

        # ---------------- Danh sách công việc ----------------
        # ---------------- Danh sách công việc ----------------
        st.subheader("📋 Danh sách công việc trong dự án")
        @st.cache_data(ttl=50)
        def load_tasks_by_project(project_name):
            supabase = get_supabase_client()
            data = supabase.table("tasks").select("*").eq("project", project_name).execute()
            return pd.DataFrame(data.data)

        df_tasks = load_tasks_by_project(project)

        if df_tasks.empty:
            st.info("Chưa có công việc nào trong dự án này.")
        else:
            # Hàm lấy unit của job
            @st.cache_data(ttl=30)
            def load_job_units():
                supabase = get_supabase_client()
                data2 = supabase.table("job_catalog").select("name, unit").execute()
                return pd.DataFrame(data2.data)

            # ✅ Lưu lại start_date gốc để dùng lọc công nhật
            df_tasks["start_date_raw"] = df_tasks["start_date"]

            jobs_units = load_job_units()

            # Merge 1 lần duy nhất
            df_tasks = df_tasks.merge(jobs_units, left_on="task", right_on="name", how="left")
            df_tasks["assignee_display"] = df_tasks["assignee"].map(user_map).fillna(df_tasks["assignee"])

            # ============================
            #  PHẦN CÔNG NHẬT – LỌC THEO THỜI GIAN
            # ============================

            df_cong_all = df_tasks.copy()

            # ============================
            # 1. LẤY NGÀY LÀM VIỆC
            # ============================

            # Nếu start_date null → dùng note
            # Dùng trực tiếp start_date từ database, không đọc từ note
            df_cong_all["Ngày_dt"] = pd.to_datetime(df_cong_all["start_date"], errors="coerce").dt.date

            # Bỏ hết dòng không có start_date
            df_cong_all = df_cong_all[df_cong_all["Ngày_dt"].notna()].reset_index(drop=True)



            if df_cong_all.empty:
                st.warning("⛔ Không có công nhật nào trong dự án này.")
            else:

                # ============================
                # 2. UI CHỌN NĂM / QUÝ
                # ============================

                st.markdown("### ⏱️ Công nhật – Lọc theo thời gian")

                today = dt.date.today()
                year_now = today.year

                colY, colQ = st.columns([1, 1])
                year_filter = colY.selectbox("Năm", [year_now - 1, year_now, year_now + 1], index=1)

                quarters = {
                    "Q1": (dt.date(year_filter, 1, 1), dt.date(year_filter, 3, 31)),
                    "Q2": (dt.date(year_filter, 4, 1), dt.date(year_filter, 6, 30)),
                    "Q3": (dt.date(year_filter, 7, 1), dt.date(year_filter, 9, 30)),
                    "Q4": (dt.date(year_filter, 10, 1), dt.date(year_filter, 12, 31)),
                }

                q_now = (today.month - 1) // 3
                q_name = colQ.selectbox("Quý", list(quarters.keys()), index=q_now)
                d_from, d_to = quarters[q_name]

                # ============================
                # 3. LỌC THEO QUÝ
                # ============================

                df_cong_all = df_cong_all[
                    (df_cong_all["Ngày_dt"] >= d_from) &
                    (df_cong_all["Ngày_dt"] <= d_to)
                ].reset_index(drop=True)

                if df_cong_all.empty:
                    st.warning("⛔ Không có công nhật trong quý đã chọn.")
                else:

                    # ============================
                    # 4. TÁCH GIỜ TRONG NOTE
                    # ============================

                    def split_times(note_text):
                        if not isinstance(note_text, str):
                            return "", "", "", ""

                        # Tách giờ "⏰ 09:30 - 11:30"
                        time_re = r"⏰\s*(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})"
                        m1 = re.search(time_re, note_text)
                        stime = m1.group(1) if m1 else ""
                        etime = m1.group(2) if m1 else ""

                        # Tách ngày trong ngoặc
                        date_re = r"\((\d{4}-\d{2}-\d{2})\s*[→\-]\s*(\d{4}-\d{2}-\d{2})\)"
                        m2 = re.search(date_re, note_text)
                        date_part = m2.group(0) if m2 else ""

                        # Phần ghi chú còn lại
                        note_rest = re.sub(time_re, "", note_text)
                        note_rest = re.sub(date_re, "", note_rest).strip()

                        return stime, etime, date_part, note_rest

                    # ============================
                    # ============================
                    # 5. HIỂN THỊ THEO USER (PUBLIC)
                    # ============================

                    # Đảm bảo có cột assignee_display: username -> display_name
                    df_cong_all["assignee_display"] = (
                        df_cong_all["assignee"].map(user_map).fillna(df_cong_all["assignee"])
                    )

                    # Nếu sau khi lọc quý mà không còn dòng nào
                    if df_cong_all.empty:
                        st.info("Không có công nhật nào trong khoảng thời gian đã chọn.")
                    else:
                        # Lặp theo từng user hiển thị
                        for user_name in df_cong_all["assignee_display"].unique():

                            # Lọc đúng các dòng của user này
                            df_user = df_cong_all[df_cong_all["assignee_display"] == user_name].copy()

                            with st.expander(f"👤 {user_name}", expanded=False):

                                if df_user.empty:
                                    st.info("Không có công nhật trong quý này.")
                                    continue

                                # Chuẩn hóa ngày và bỏ dòng thiếu start_date
                                df_user["Ngày_dt"] = pd.to_datetime(
                                    df_user["start_date"], errors="coerce"
                                ).dt.date
                                df_user = df_user[df_user["Ngày_dt"].notna()].copy()

                                if df_user.empty:
                                    st.info("User này không có công nhật hợp lệ (thiếu ngày bắt đầu).")
                                    continue

                                # ---------------- TẠO DỮ LIỆU ĐẦU VÀO AG-GRID ----------------
                                rows = []
                                for _, r in df_user.iterrows():
                                    # Hàm split_times bạn đã có sẵn từ file cũ
                                    stime, etime, date_part, note_rest = split_times(r.get("note", ""))

                                    if stime and etime:
                                        full_note_display = f"⏰ {stime} - {etime} {date_part} {note_rest}".strip()
                                    else:
                                        full_note_display = note_rest.strip()

                                    rows.append({
                                        "ID": r["id"],
                                        "Ngày": r["Ngày_dt"].strftime("%Y-%m-%d"),
                                        "Công việc": r["task"],
                                        "Giờ bắt đầu": stime,
                                        "Giờ kết thúc": etime,
                                        "Khối lượng (giờ)": float(r.get("khoi_luong") or 0),
                                        "Ghi chú": full_note_display,
                                        "approved": bool(r.get("approved", False)),
                                        "Chọn?": False,
                                    })

                                if not rows:
                                    st.info("Không có công nhật để hiển thị.")
                                    continue

                                df_display = pd.DataFrame(rows).sort_values("Ngày")

                                # Lấy username thật để dùng cho key (ổn định hơn, không dấu)
                                username_real = df_users.loc[
                                    df_users["display_name"] == user_name, "username"
                                ].iloc[0]

                                grid_key = f"cong_grid_{project}_{username_real}".replace(" ", "_")

                                # ---------------- CẤU HÌNH AG-GRID ----------------
                                gb = GridOptionsBuilder.from_dataframe(df_display)
                                gb.configure_default_column(editable=True)
                                gb.configure_column("approved", hide=True)
                                gb.configure_column("Chọn?", editable=True)

                                gridOptions = gb.build()

                                # Tô màu dòng đã duyệt
                                row_style = JsCode("""
                                    function(params) {
                                        if (params.data.approved === true) {
                                            return {'backgroundColor': '#fff7cc'};
                                        }
                                        return null;
                                    }
                                """)
                                gridOptions["getRowStyle"] = row_style

                                grid = AgGrid(
                                    df_display,
                                    gridOptions=gridOptions,
                                    update_mode=GridUpdateMode.NO_UPDATE,
                                    data_return_mode=DataReturnMode.AS_INPUT,
                                    allow_unsafe_jscode=True,
                                    fit_columns_on_grid_load=True,
                                    height=400,
                                    key=grid_key,
                                )

                                edited = pd.DataFrame(grid["data"])
                                selected = edited[edited["Chọn?"] == True]

                                colA, colB, colC = st.columns([1, 1, 1])

                                # ---------- XÓA ----------
                                if colA.button("🗑 Xóa dòng đã chọn", key=f"del_{username_real}"):
                                    for _, row in selected.iterrows():
                                        supabase.table("tasks").delete().eq("id", row["ID"]).execute()
                                    st.success("Đã xoá.")
                                    st.rerun()

                                # ---------- DUYỆT / BỎ DUYỆT ----------
                                any_approved = bool(len(selected) and selected["approved"].any())
                                label = "❌ Bỏ duyệt" if any_approved else "✔ Duyệt"

                                if colB.button(label, key=f"approve_{username_real}"):
                                    new_val = not any_approved
                                    for _, row in selected.iterrows():
                                        supabase.table("tasks").update(
                                            {"approved": new_val}
                                        ).eq("id", row["ID"]).execute()
                                    st.success("Đã cập nhật.")
                                    st.rerun()

                                # ---------- LƯU CÔNG NHẬT ----------
                                if colC.button("💾 Lưu công nhật", key=f"save_{username_real}"):
                                    for _, row in edited.iterrows():
                                        supabase.table("tasks").update({
                                            "start_date": row["Ngày"],
                                            "khoi_luong": row["Khối lượng (giờ)"],
                                            "note": row["Ghi chú"],
                                        }).eq("id", row["ID"]).execute()
                                    st.success("Đã lưu.")
                                    st.rerun()




    elif choice == "Chấm công – Nghỉ phép":
 
        st.subheader("🕒 Quản lý chấm công & nghỉ phép")

        supabase = get_connection()
        df_users = load_users_cached()

        # ==== CHỌN THÁNG ====
        today_ts = pd.Timestamp(dt.date.today())
        today_date = dt.date.today()
        selected_month = st.date_input("📅 Chọn tháng", dt.date(today_date.year, today_date.month, 1))
        month_str = selected_month.strftime("%Y-%m")

        # Reset buffer khi đổi tháng
        if "selected_month_prev" not in st.session_state or st.session_state["selected_month_prev"] != month_str:
            st.session_state.pop("attendance_buffer", None)
            st.session_state["selected_month_prev"] = month_str

        st.subheader(f"🗓️ Bảng chấm công – Tháng {selected_month.strftime('%m/%Y')}")

        # ==== DANH SÁCH NGÀY ====
        first_day = selected_month.replace(day=1)
        next_month = (first_day + dt.timedelta(days=32)).replace(day=1)
        days = pd.date_range(first_day, next_month - dt.timedelta(days=1))

        # ==== KÝ HIỆU ====
        code_options = [
            "", "K", "K:2", "P", "H", "TQ", "BD", "L", "O", "VR",
            "NM", "TS", "VS", "TV",
            "K/P", "P/K", "K/H", "H/K", "K/TQ", "TQ/K", "K/NM", "NM/K",
            "K/TS", "TS/K", "K/VR", "VR/K", "K/O", "O/K",
            "K/ĐT", "ĐT/K", "K/L", "L/K"
        ]

        # ==== ĐỌC DỮ LIỆU ====
        res = supabase.table("attendance_new").select("*").execute()
        df_att = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["username", "data", "months"])

        # ==== KHỞI TẠO BUFFER ====
        if "attendance_buffer" not in st.session_state:
            rows = []
            for _, u in df_users.iterrows():
                uname = u["username"]
                display_name = u["display_name"]
                record = df_att[df_att["username"] == uname]
                user_data = {}
                if len(record) > 0:
                    rec = record.iloc[0]
                    user_data = rec.get("data", {}) or {}
                    if isinstance(user_data, str):
                        try:
                            user_data = json.loads(user_data)
                        except:
                            user_data = {}
                month_data = user_data.get(month_str, {})
                row = {"username": uname, "User": display_name}
                for d in days:
                    weekday = d.weekday()
                    key = d.strftime("%d")
                    col = f"{key}/{d.strftime('%m')} ({['T2','T3','T4','T5','T6','T7','CN'][weekday]})"
                    if d.date() <= today_date:
                        val = month_data.get(key, "K" if weekday < 5 else "")
                    else:
                        val = month_data.get(key, "")
                    row[col] = val
                rows.append(row)
            st.session_state["attendance_buffer"] = pd.DataFrame(rows)

        df_display = st.session_state["attendance_buffer"].copy()
        day_cols = [c for c in df_display.columns if "/" in c]
        df_display_clean = df_display.drop(columns=["username"]).copy()

        # =============================
        # =============================
        #     TẠO GRID OPTIONS (FIX UI)
        # =============================

        # 1) Làm header ngày 2 dòng: "01/11\n(T7)" (không dùng HTML)
        day_cols_multiline = {}
        for col in day_cols:                      # col dạng "01/11 (T7)"
            if " (" in col:
                d, w = col.split(" (", 1)         # d="01/11", w="T7)"
                day_cols_multiline[col] = f"{d}\n({w.rstrip(')')})"
            else:
                day_cols_multiline[col] = col

        # 2) Ẩn username khi hiển thị
        df_display_clean = df_display.drop(columns=["username"]).copy()

        # 3) CSS hỗ trợ header xuống dòng + màu ô (ổn định với !important)
        st.markdown("""
        <style>
        /* Header đa dòng */
        .ag-theme-streamlit .multiline-header .ag-header-cell-label {
          white-space: pre-line !important;
          line-height: 14px !important;
        }

        /* Màu ô theo class (backup nếu cellStyle không áp) */
        .ag-theme-streamlit .bg-k    { background-color:#C8E6C9 !important; }
        .ag-theme-streamlit .bg-k2   { background-color:#FFE0B2 !important; }
        .ag-theme-streamlit .bg-p    { background-color:#FFCDD2 !important; }
        .ag-theme-streamlit .bg-h    { background-color:#BBDEFB !important; }
        .ag-theme-streamlit .bg-tq   { background-color:#FFF9C4 !important; }
        .ag-theme-streamlit .bg-bd   { background-color:#FFE0B2 !important; }
        .ag-theme-streamlit .bg-l    { background-color:#D7CCC8 !important; }
        .ag-theme-streamlit .bg-o    { background-color:#C8E6C9 !important; }
        .ag-theme-streamlit .bg-vr   { background-color:#E0E0E0 !important; }
        .ag-theme-streamlit .bg-nm   { background-color:#E1BEE7 !important; }
        .ag-theme-streamlit .bg-ts   { background-color:#E1BEE7 !important; }
        .ag-theme-streamlit .bg-vs   { background-color:#BBDEFB !important; }
        .ag-theme-streamlit .bg-tv   { background-color:#FFF9C4 !important; }
        .ag-theme-streamlit .bg-mix  { background-color:#FFECB3 !important; } /* K/P, P/K,... */
        .ag-theme-streamlit .bg-none { background-color:#FFFFFF !important; }
        </style>
        """, unsafe_allow_html=True)

        # 4) Build grid
        gb = GridOptionsBuilder.from_dataframe(df_display_clean)
        gb.configure_default_column(
            editable=True,
            resizable=True,
            sortable=False,
            filter=False,
            wrapHeaderText=True,      # cho phép xuống dòng
            autoHeaderHeight=True,    # header tự tăng chiều cao
            autoSize=False
        )

        # Cột User: ghim trái, rộng hơn để không cụt chữ
        gb.configure_column(
            "User",
            pinned="left",
            editable=False,
            width=150,                # rộng ra
            wrapText=True,
            autoHeight=True
        )

        # JS: tô màu theo giá trị (đảm bảo ăn màu)
        color_style_js = JsCode("""
        function(params) {
          const map = {
            'K':'#C8E6C9','K:2':'#FFE0B2','P':'#FFCDD2','H':'#BBDEFB',
            'TQ':'#FFF9C4','BD':'#FFE0B2','L':'#D7CCC8','O':'#C8E6C9',
            'VR':'#E0E0E0','NM':'#E1BEE7','TS':'#E1BEE7','VS':'#BBDEFB',
            'TV':'#FFF9C4','K/P':'#FFECB3','P/K':'#FFECB3','K/H':'#BBDEFB',
            'H/K':'#BBDEFB','K/TQ':'#FFF9C4','TQ/K':'#FFF9C4','K/NM':'#E1BEE7',
            'NM/K':'#E1BEE7','K/TS':'#E1BEE7','TS/K':'#E1BEE7','K/VR':'#E0E0E0',
            'VR/K':'#E0E0E0','K/O':'#C8E6C9','O/K':'#C8E6C9','K/ĐT':'#FFE0B2',
            'ĐT/K':'#FFE0B2','K/L':'#D7CCC8','L/K':'#D7CCC8','':'#FFFFFF'
          };
          const v = (params.value || '').trim();
          return {'backgroundColor': map[v] || '#FFFFFF', 'textAlign':'center'};
        }
        """)

        # Class rules: lớp CSS tương ứng (backup)
        def class_rules():
            return {
                "bg-k":  "value == 'K'",
                "bg-k2": "value == 'K:2'",
                "bg-p":  "value == 'P'",
                "bg-h":  "value == 'H'",
                "bg-tq": "value == 'TQ'",
                "bg-bd": "value == 'BD'",
                "bg-l":  "value == 'L'",
                "bg-o":  "value == 'O'",
                "bg-vr": "value == 'VR'",
                "bg-nm": "value == 'NM'",
                "bg-ts": "value == 'TS'",
                "bg-vs": "value == 'VS'",
                "bg-tv": "value == 'TV'",
                "bg-mix": "value == 'K/P' || value == 'P/K' || value == 'K/H' || value == 'H/K' || \
                           value == 'K/TQ' || value == 'TQ/K' || value == 'K/NM' || value == 'NM/K' || \
                           value == 'K/TS' || value == 'TS/K' || value == 'K/VR' || value == 'VR/K' || \
                           value == 'K/O' || value == 'O/K' || value == 'K/ĐT' || value == 'ĐT/K' || \
                           value == 'K/L' || value == 'L/K'",
                "bg-none": "!value"
            }

        # Cấu hình từng cột ngày
        for col in day_cols:
            gb.configure_column(
                col,
                headerName=day_cols_multiline[col],        # "01/11\n(T7)"
                headerClass="multiline-header",            # ép header render xuống dòng
                cellEditor="agSelectCellEditor",
                cellEditorParams={"values": [
                    "", "K","K:2","P","H","TQ","BD","L","O","VR",
                    "NM","TS","VS","TV",
                    "K/P","P/K","K/H","H/K","K/TQ","TQ/K","K/NM","NM/K",
                    "K/TS","TS/K","K/VR","VR/K","K/O","O/K",
                    "K/ĐT","ĐT/K","K/L","L/K"
                ]},
                cellClassRules=class_rules(),              # tô màu qua class
                cellStyle=color_style_js,                  # và tô màu trực tiếp (đảm bảo)
                width=50,                                  # tăng chút để "01/11" không cụt
                autoSize=False
            )

        gridOptions = gb.build()
        gridOptions["headerHeight"] = 56                  # header cao thêm
        gridOptions["ensureDomOrder"] = True
        gridOptions["suppressHorizontalScroll"] = False

        # =============================
        #   HIỂN THỊ AG-GRID
        # =============================
        with st.form("attendance_form", clear_on_submit=False):
            grid_response = AgGrid(
                df_display_clean,
                gridOptions=gridOptions,
                height=650,
                theme="streamlit",                        # ép theme để CSS ăn
                allow_unsafe_jscode=True,
                update_mode=GridUpdateMode.MANUAL,
                data_return_mode=DataReturnMode.AS_INPUT,
                reload_data=False,
                fit_columns_on_grid_load=False,
                key=f"grid_{month_str}"
            )

            # Đưa scroll về đầu
            st.markdown("<script>window.scrollTo({top:0,left:0,behavior:'auto'});</script>", unsafe_allow_html=True)

            edited_df_clean = pd.DataFrame(grid_response["data"]).reset_index(drop=True)
            edited_df = edited_df_clean.copy()
            edited_df["username"] = df_display["username"].reset_index(drop=True)
            edited_df = edited_df[["username", "User"] + day_cols]
            st.session_state["attendance_buffer"] = edited_df.copy()

            # (phần Ghi chú + nút Lưu giữ nguyên phía dưới)


            # ==== GHI CHÚ THÁNG ====
            st.markdown("### 📝 Ghi chú tháng")
            note_rec = df_att[df_att["username"] == "NoteData"]
            existing_note = ""
            if not note_rec.empty:
                note_data = note_rec.iloc[0].get("data", {}) or {}
                if isinstance(note_data, str):
                    try:
                        note_data = json.loads(note_data)
                    except:
                        note_data = {}
                existing_note = note_data.get(month_str, "")
            monthly_note = st.text_area(
                f"Ghi chú cho tháng {month_str}:",
                value=existing_note,
                height=120
            )

            save_clicked = st.form_submit_button("💾 Lưu bảng chấm công & ghi chú")

        # ==== LƯU DỮ LIỆU ====
        if save_clicked:
            today_date = dt.date.today()
            edited_df = st.session_state["attendance_buffer"].copy()
            updated_users, inserted_users, skipped_users, errors = [], [], [], []

            with st.spinner("💾 Đang lưu dữ liệu lên Supabase..."):
                for _, row in edited_df.iterrows():
                    uname = row["username"]

                    def remove_emoji(txt):
                        if not txt:
                            return ""
                        txt = re.sub(r"[\U0001F300-\U0001FAFF]", "", str(txt))
                        for sym in ["🟩","🟥","🟦","🟧","🟨","🟫","🟪","⬛"]:
                            txt = txt.replace(sym,"")
                        return txt.strip()

                    codes = {}
                    for col in day_cols:
                        try:
                            day = int(col.split("/")[0])
                            date_in_month = selected_month.replace(day=day)
                            if date_in_month <= today_date:
                                val = remove_emoji(row.get(col))
                                codes[f"{day:02d}"] = val
                        except:
                            pass

                    record = df_att[df_att["username"].astype(str).str.strip() == str(uname).strip()]
                    try:
                        if len(record) == 0:
                            payload = {"username": uname, "months": [month_str], "data": {month_str: codes}}
                            supabase.table("attendance_new").insert(payload).execute()
                            inserted_users.append(uname)
                            continue

                        rec = record.iloc[0]
                        months = rec.get("months", []) or []
                        data_all = rec.get("data", {}) or {}
                        if isinstance(data_all, str):
                            try:
                                data_all = json.loads(data_all)
                            except:
                                data_all = {}

                        old_month_data = data_all.get(month_str, {})
                        if isinstance(old_month_data, str):
                            try:
                                old_month_data = json.loads(old_month_data)
                            except:
                                old_month_data = {}

                        if old_month_data != codes:
                            data_all[month_str] = codes
                            if month_str not in months:
                                months.append(month_str)
                            supabase.table("attendance_new").update({
                                "data": data_all,
                                "months": months
                            }).eq("username", uname).execute()
                            updated_users.append(uname)
                        else:
                            skipped_users.append(uname)
                    except Exception as e:
                        errors.append(f"{uname}: {e}")

                # ==== GHI CHÚ ====
                note_rec = df_att[df_att["username"] == "NoteData"]
                if not note_rec.empty:
                    rec = note_rec.iloc[0]
                    data_all = rec.get("data", {}) or {}
                    if isinstance(data_all, str):
                        data_all = json.loads(data_all)
                    data_all[month_str] = monthly_note
                    supabase.table("attendance_new").update(
                        {"data": data_all, "months": [month_str]}
                    ).eq("username","NoteData").execute()
                else:
                    supabase.table("attendance_new").insert({
                        "username": "NoteData",
                        "data": {month_str: monthly_note},
                        "months": [month_str]
                    }).execute()

            msg = f"✅ Lưu thành công!\n- Cập nhật: {len(updated_users)} user\n- Thêm mới: {len(inserted_users)} user\n- Bỏ qua: {len(skipped_users)} user"
            if errors:
                msg += f"\n⚠️ Lỗi {len(errors)} user: {', '.join(errors)}"
            st.success(msg)

        # ==============================
        # 📊 THỐNG KÊ CÔNG THEO THÁNG
        # ==============================
        st.divider()
        st.markdown("## 📊 Thống kê tổng hợp theo tháng")

        df_stat = st.session_state["attendance_buffer"].copy()
        day_cols = [c for c in df_stat.columns if "/" in c]

        def count_type(row, code):
            return sum(1 for c in day_cols if str(row[c]).strip().upper() == code)

        df_stat["Tổng K"] = df_stat.apply(lambda r: count_type(r, "K"), axis=1)
        df_stat["Tổng P"] = df_stat.apply(lambda r: count_type(r, "P"), axis=1)
        df_stat["Tổng L"] = df_stat.apply(lambda r: count_type(r, "L"), axis=1)
        df_stat["Tổng H"] = df_stat.apply(lambda r: count_type(r, "H"), axis=1)
        df_stat["Tổng Công"] = df_stat["Tổng K"] + df_stat["Tổng H"] + df_stat["Tổng P"]

        st.dataframe(
            df_stat[["User", "Tổng K", "Tổng P", "Tổng L", "Tổng H", "Tổng Công"]],
            hide_index=True,
            use_container_width=True
        )

    elif choice == "Thống kê công việc":
        st.subheader("📊 Thống kê công việc")

        # Lấy danh sách dự án
        projects = df_projects["name"].dropna().tolist()


        # Bộ lọc dự án
        filter_mode = st.radio("Chế độ thống kê", 
                               ["Chỉ dự án chưa hoàn thành", "Chọn dự án", "Tất cả"])

        selected_projects = []
        if filter_mode == "Chọn dự án":
            selected_projects = st.multiselect("Chọn dự án cần thống kê", projects)
        elif filter_mode == "Tất cả":
            selected_projects = projects
        elif filter_mode == "Chỉ dự án chưa hoàn thành":
            data = supabase.table("tasks").select("project").lt("progress", 100).execute()
            unfinished = list({r["project"] for r in data.data})
            selected_projects = unfinished

        # Lấy dữ liệu công việc
        if selected_projects:
            placeholders = ",".join(["%s"] * len(selected_projects))
            data = supabase.table("tasks").select("*").in_("project", selected_projects).execute()
            df = pd.DataFrame(data.data)

        else:
            df = pd.DataFrame()

        if df.empty:
            st.info("⚠️ Không có dữ liệu công việc cho lựa chọn này.")
        else:
            # Chọn kiểu thống kê
            df["assignee"] = df["assignee"].map(user_map).fillna(df["assignee"])

            stat_mode = st.radio("Xem thống kê theo", ["Dự án", "Người dùng"])

            # ==================== THEO DỰ ÁN ====================
            if stat_mode == "Dự án":
                # Tổng quan theo dự án
                proj_summary = df.groupby("project").agg(
                    **{
                        "Tổng công việc": ("id", "count"),
                        "Hoàn thành": ("progress", lambda x: (x == 100).sum()),
                        "Chưa hoàn thành": ("progress", lambda x: (x < 100).sum()),
                        "Tiến độ trung bình (%)": ("progress", "mean")
                    }
                ).reset_index().rename(columns={"project": "Dự án"})

                styled_proj = proj_summary.style.format(
                    {"Tiến độ trung bình (%)": "{:.0f} %"}
                ).bar(subset=["Tiến độ trung bình (%)"], color="#4CAF50")

                st.markdown("### 📂 Tiến độ theo dự án")
                st.dataframe(styled_proj, width="stretch")


                # Chi tiết theo đầu mục công việc (cha)
                # Map task -> cha
                job_map = df_jobs[["id", "name", "parent_id"]].copy()

                parent_lookup = {}
                for _, row in job_map.iterrows():
                    if pd.isna(row["parent_id"]):
                        parent_lookup[row["name"]] = row["name"]
                    else:
                        pid = int(row["parent_id"])
                        parent_name = job_map.loc[job_map["id"] == pid, "name"].values[0]
                        parent_lookup[row["name"]] = parent_name

                df["Đầu mục công việc"] = df["task"].map(parent_lookup).fillna(df["task"])

                job_summary = df.groupby(["project", "Đầu mục công việc"]).agg(
                    **{
                        "Tổng công việc": ("id", "count"),
                        "Hoàn thành": ("progress", lambda x: (x == 100).sum()),
                        "Chưa hoàn thành": ("progress", lambda x: (x < 100).sum()),
                        "Tiến độ trung bình (%)": ("progress", "mean")
                    }
                ).reset_index().rename(columns={"project": "Dự án"})

                styled_job = job_summary.style.format(
                    {"Tiến độ trung bình (%)": "{:.0f} %"}
                ).bar(subset=["Tiến độ trung bình (%)"], color="#2196F3")
                
                # ---- Thống kê theo đầu mục công việc (dạng cây, bỏ dự án public) ----
                st.markdown("### 🌳 Thống kê Đầu mục công việc Của dự án")

                # Bỏ các dự án Public nếu có cột project_type
                if "project_type" in df.columns:
                    df_non_public = df[df["project_type"] != "public"].copy()
                else:
                    df_non_public = df.copy()

                if df_non_public.empty:
                    st.info("⚠️ Không có dữ liệu công việc cho các dự án không Public.")
                else:
                    # Map task -> đầu mục cha
                    job_map = df_jobs[["id", "name", "parent_id"]].copy()

                    parent_lookup = {}
                    for _, row in job_map.iterrows():
                        if pd.isna(row["parent_id"]):
                            parent_lookup[row["name"]] = row["name"]
                        else:
                            pid = int(row["parent_id"])
                            parent_name = job_map.loc[job_map["id"] == pid, "name"].values[0]
                            parent_lookup[row["name"]] = parent_name

                    df_non_public["Đầu mục"] = df_non_public["task"].map(parent_lookup).fillna(df_non_public["task"])

                    # Gom nhóm theo Dự án + Đầu mục
                    grouped = df_non_public.groupby(["project", "Đầu mục"]).agg(
                        Tổng_công_việc=("id", "count"),
                        Hoàn_thành=("progress", lambda x: (x == 100).sum()),
                        Chưa_hoàn_thành=("progress", lambda x: (x < 100).sum()),
                        Tiến_độ_TB=("progress", "mean")
                    ).reset_index()

                    # Tạo bảng hiển thị: dự án chỉ ghi ở dòng đầu tiên
                    rows = []
                    for proj in grouped["project"].unique():
                        df_proj = grouped[grouped["project"] == proj]
                        first = True
                        for _, r in df_proj.iterrows():
                            rows.append({
                                "Dự án": proj if first else "",
                                "Đầu mục": r["Đầu mục"],
                                "Tổng công việc": int(r["Tổng_công_việc"]),
                                "Hoàn thành": int(r["Hoàn_thành"]),
                                "Chưa hoàn thành": int(r["Chưa_hoàn_thành"]),
                                "Tiến độ TB (%)": round(r["Tiến_độ_TB"], 1)
                            })
                            first = False
                    display_df = pd.DataFrame(rows)

                    st.dataframe(
                        display_df.style.format({"Tiến độ TB (%)": "{:.0f} %"}),
                        width="stretch"
                    )

                    # ---- Biểu đồ tiến độ dự án (trừ public) ----


                    # ---- BIỂU ĐỒ 1: TIẾN ĐỘ THEO ĐẦU MỤC CỦA TỪNG DỰ ÁN (KHÔNG PUBLIC) ----
                    st.markdown("### 📈 Tiến độ các Đầu mục trong từng Dự án")

                    proj_detail = df.copy()

                    # Loại bỏ các dự án public hoặc "Công việc gián tiếp"
                    if "project" in proj_detail.columns:
                        proj_detail = proj_detail[~proj_detail["project"].str.contains("public", case=False, na=False)]
                        proj_detail = proj_detail[~proj_detail["project"].str.contains("gián tiếp", case=False, na=False)]

                    # Xác định tên cột đầu mục
                    col_daumuc = "Đầu mục công việc" if "Đầu mục công việc" in proj_detail.columns else (
                        "Đầu mục" if "Đầu mục" in proj_detail.columns else "task_category"
                    )

                    proj_detail = proj_detail.groupby(["project", col_daumuc]).agg(
                        Số_CV=("id", "count"),
                        Tiến_độ_TB=("progress", "mean")
                    ).reset_index()

                    proj_detail.rename(columns={col_daumuc: "Đầu mục"}, inplace=True)
                    proj_detail["Hiển thị"] = proj_detail.apply(
                        lambda x: f"<b>{x['project']}</b><br>{x['Đầu mục']}", axis=1
                    )

                    import plotly.express as px
                    fig = px.bar(
                        proj_detail,
                        x="Tiến_độ_TB",
                        y="Hiển thị",
                        orientation="h",
                        text="Số_CV",
                        labels={
                            "Tiến_độ_TB": "Tiến độ TB (%)",
                            "Hiển thị": "Dự án / Đầu mục",
                            "Số_CV": "Số CV"
                        },
                        title="Tiến độ các đầu mục công việc trong từng dự án (không Public)"
                    )
                    fig.update_traces(texttemplate='Tiến độ %{x:.0f}% | %{text} CV', textposition='outside')
                    fig.update_layout(yaxis=dict(autorange="reversed"), showlegend=False)
                    st.plotly_chart(fig, width="stretch")
                    st.markdown(
                        """
                        <style>
                        .page-break { 
                            page-break-before: always; 
                        }
                        </style>
                        """,
                        unsafe_allow_html=True
                    )
                    st.markdown('<div class="page-break"></div>', unsafe_allow_html=True)

                    # ---- BIỂU ĐỒ 2: TIẾN ĐỘ TỔNG THỂ CỦA MỖI DỰ ÁN ----
                    st.markdown("### 📊 Biểu đồ hoàn thành dự án")

                    proj_progress = df.copy()

                    # Loại bỏ các dự án Public hoặc "Công việc gián tiếp"
                    if "project" in proj_progress.columns:
                        proj_progress = proj_progress[~proj_progress["project"].str.contains("public", case=False, na=False)]
                        proj_progress = proj_progress[~proj_progress["project"].str.contains("gián tiếp", case=False, na=False)]

                    # Ép tên dự án thành chuỗi để Plotly không coi là số
                    proj_progress["project"] = proj_progress["project"].astype(str)

                    # Gom tiến độ trung bình cho mỗi dự án
                    proj_progress = proj_progress.groupby("project", dropna=False).agg(
                        Tổng_CV=("id", "count"),
                        Tiến_độ_TB=("progress", "mean")
                    ).reset_index()

                    import plotly.express as px

                    fig_proj = px.bar(
                        proj_progress,
                        x="project",          # Trục X = tên dự án
                        y="Tiến_độ_TB",       # Trục Y = % tiến độ TB
                        text=proj_progress.apply(lambda x: f"{x['Tiến_độ_TB']:.0f}% | {x['Tổng_CV']} CV", axis=1),
                        labels={
                            "project": "Dự án",
                            "Tiến_độ_TB": "Tiến độ TB (%)",
                            "Tổng_CV": "Tổng công việc"
                        },
                        title="📊 Biểu đồ hoàn thành dự án (không Public)"
                    )

                    fig_proj.update_traces(textposition='outside')
                    fig_proj.update_layout(
                        xaxis=dict(type='category'),  # Giữ nguyên tên dự án dạng text
                        yaxis=dict(range=[0, 100]),   # Giới hạn 0–100%
                        showlegend=False,
                        xaxis_title="Dự án",
                        yaxis_title="Tiến độ TB (%)"
                    )

                    st.plotly_chart(fig_proj, width="stretch")






            # ==================== THEO NGƯỜI DÙNG ====================
            else:
                # Lấy toàn bộ user
                all_users = df_users["display_name"].tolist()


                # Map task -> cha
                job_map = df_jobs[["id", "name", "parent_id"]].copy()

                parent_lookup = {}
                for _, row in job_map.iterrows():
                    if pd.isna(row["parent_id"]):
                        parent_lookup[row["name"]] = row["name"]
                    else:
                        pid = int(row["parent_id"])
                        parent_name = job_map.loc[job_map["id"] == pid, "name"].values[0]
                        parent_lookup[row["name"]] = parent_name

                df["Đầu mục công việc"] = df["task"].map(parent_lookup).fillna(df["task"])

                # Gom nhóm user + dự án + đầu mục
                grouped = df.groupby(["assignee", "project", "Đầu mục công việc"]).agg(
                    Tổng_công_việc=("id", "count"),
                    Hoàn_thành=("progress", lambda x: (x == 100).sum()),
                    Chưa_hoàn_thành=("progress", lambda x: (x < 100).sum()),
                    Tiến_độ_TB=("progress", "mean")
                ).reset_index().rename(columns={"assignee": "Người dùng", "project": "Dự án"})

                # Outer join để tất cả user đều có mặt
                users_df = pd.DataFrame({"Người dùng": all_users})
                user_detail = users_df.merge(grouped, on="Người dùng", how="left")

                # Điền giá trị mặc định nếu user không có task
                user_detail[["Dự án","Đầu mục công việc"]] = user_detail[["Dự án","Đầu mục công việc"]].fillna("—")
                user_detail[["Tổng_công_việc","Hoàn_thành","Chưa_hoàn_thành","Tiến_độ_TB"]] = \
                    user_detail[["Tổng_công_việc","Hoàn_thành","Chưa_hoàn_thành","Tiến_độ_TB"]].fillna(0)

                styled_user = user_detail.style.format(
                    {"Tiến_độ_TB": "{:.0f} %"}
                ).bar(subset=["Tiến_độ_TB"], color="#FF9800")

                st.markdown("### 👤 Thống kê chi tiết theo người dùng")
                st.dataframe(styled_user, width="stretch")
        

    # 🔁 Nếu vừa lưu xong, đợi 0.5s rồi reload lại một lần
    if st.session_state.get("just_saved"):
        time.sleep(0.5)
        st.session_state.just_saved = False
        st.rerun()
