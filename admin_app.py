import streamlit as st
import pandas as pd
import plotly.express as px
import datetime
import datetime as dt

from auth import get_connection, calc_hours, get_projects, add_user, hash_password, add_project
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, JsCode


# ====== CACHE DỮ LIỆU TỪ SUPABASE ======
@st.cache_data(ttl=15)
def load_users_cached():
    supabase = get_connection()
    data = supabase.table("users").select("id, username, display_name, dob, role, project_manager_of, project_leader_of").execute()
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

        # Đọc danh sách user
        df_users = st.session_state["df_users"]

        # Đổi tên cột
        df_users = df_users.rename(columns={
            "username": "Tên đăng nhập",
            "display_name": "Tên hiển thị",
            "dob": "Ngày sinh",
            "role": "Vai trò",
            "project_manager_of": "Chủ nhiệm dự án",
            "project_leader_of": "Chủ trì dự án"
        })

        # 👉 Ẩn cột ID khi hiển thị
        st.dataframe(df_users.drop(columns=["id"], errors="ignore"), width="stretch")

        # 👉 Selectbox hiển thị theo Tên hiển thị
        selected_display = st.selectbox("Chọn user", df_users["Tên hiển thị"].tolist())

        # Map ngược để lấy username thực khi cần update/xóa
        if df_users.empty:
            st.error("⚠️ Không có người dùng nào trong cơ sở dữ liệu.")
            return  # Dừng lại nếu không có người dùng

        # Kiểm tra xem selected_display có trong danh sách tên hiển thị hay không
        if selected_display not in df_users["Tên hiển thị"].values:
            st.error("⚠️ Tên hiển thị không tồn tại trong cơ sở dữ liệu.")
            return  # Dừng lại nếu tên hiển thị không hợp lệ

        # Tiến hành lấy selected_user nếu có dữ liệu hợp lệ
        selected_user = df_users.loc[df_users["Tên hiển thị"] == selected_display, "Tên đăng nhập"].iloc[0]

        # Các quyền (vai trò)
        roles = st.multiselect(
            "Cập nhật vai trò",
            ["user", "Chủ nhiệm dự án", "Chủ trì dự án", "admin"]
        )

        # Lấy danh sách dự án
        projects_list = df_projects["name"].dropna().tolist()


        project_manager = None
        project_leader = None

        if "Chủ nhiệm dự án" in roles:
            selected_projects_manager = st.multiselect("Chọn các dự án chủ nhiệm", projects_list)
            project_manager = ",".join(selected_projects_manager) if selected_projects_manager else None

        if "Chủ trì dự án" in roles:
            selected_projects_leader = st.multiselect("Chọn các dự án chủ trì", projects_list)
            project_leader = ",".join(selected_projects_leader) if selected_projects_leader else None

        col1, col2 = st.columns(2)

        with col1:
            if st.button("💾 Cập nhật quyền"):
                roles_str = ",".join(roles) if roles else "user"
                supabase.table("users").update({
                    "role": roles_str,
                    "project_manager_of": project_manager,
                    "project_leader_of": project_leader
                }).eq("username", selected_user).execute()
                
                st.success("✅ Đã cập nhật quyền")
                refresh_all_cache()  # refresh lại danh sách

        with col2:
            if st.button("❌ Xóa user"):
                supabase.table("users").delete().eq("username", selected_user).execute()
                st.success("🗑️ Đã xóa user")
                refresh_all_cache()


        # === Thêm chức năng đổi mật khẩu cho người dùng ===
        st.subheader("🔑 Đổi mật khẩu cho người dùng")

        new_password = st.text_input("Mật khẩu mới", type="password")
        confirm_password = st.text_input("Xác nhận mật khẩu mới", type="password")



        if st.button("✅ Đổi mật khẩu"):
            if new_password != confirm_password:
                st.error("⚠️ Mật khẩu mới và xác nhận không khớp.")
            else:
                try:
                    supabase.table("users").update({
                        "password": hash_password(new_password)
                    }).eq("username", selected_user).execute()
                    
                    st.success("✅ Đã đổi mật khẩu cho người dùng.")
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
        # 2) HIỂN THỊ & CHỈNH SỬA CHA–CON–ĐƠN VỊ–NHÓM DỰ ÁN
        # ======================================
        jobs = df_jobs.copy()


        if jobs.empty:
            st.info("⚠️ Chưa có công việc nào trong mục lục")
        else:
            # rows = []
            # ===== Chuẩn bị hiển thị cha–con =====
            rows = []
            for _, p in jobs[jobs["parent_id"].isnull()].iterrows():
                # luôn thêm dòng cha
                rows.append({
                    "Cha": p["name"],
                    "Con": "",
                    "Đơn vị": p["unit"] if pd.notna(p["unit"]) else "",
                    "Nhóm dự án": p["project_type"] if pd.notna(p["project_type"]) else "group",
                    "Xóa?": False,
                    "_id": p["id"],
                    "_is_parent": True,
                    "_orig_name": p["name"]
                })
                # sau đó thêm các con
                children = jobs[jobs["parent_id"] == p["id"]]
                for _, cjob in children.iterrows():
                    rows.append({
                        "Cha": "",
                        "Con": cjob["name"],
                        "Đơn vị": cjob["unit"] if pd.notna(cjob["unit"]) else "",
                        "Nhóm dự án": cjob["project_type"] if pd.notna(cjob["project_type"]) else "group",
                        "Xóa?": False,
                        "_id": cjob["id"],
                        "_is_parent": False,
                        "_orig_name": cjob["name"]
                    })

            df_display = pd.DataFrame(rows)
            meta_cols = [c for c in df_display.columns if c.startswith("_")]

            st.markdown("### ✏️ Danh sách công việc (sửa trực tiếp)")
            edited = st.data_editor(
                df_display.drop(columns=meta_cols),
                width="stretch",
                key="job_editor",
                column_config={
                    "Cha": st.column_config.TextColumn("Đầu mục công việc"),
                    "Con": st.column_config.TextColumn("Công việc chi tiết"),
                    "Đơn vị": st.column_config.TextColumn("Đơn vị"),
                    "Nhóm dự án": st.column_config.SelectboxColumn("Nhóm dự án", options=["public", "group"]),
                    "Xóa?": st.column_config.CheckboxColumn("Xóa?", help="Tick để xoá công việc"),
                }
            )

            # ===== CẬP NHẬT =====
            # ===== Hai nút song song =====
            col1, col2 = st.columns([1,1])

            with col1:
                if st.button("💾 Cập nhật"):
                    full = edited.copy()
                    for col in meta_cols:
                        full[col] = df_display[col].values
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
                                "unit": new_unit if new_unit else None,
                                "project_type": new_project_type
                            }).eq("id", job_id).execute()

                            # nếu đổi tên thì đồng bộ sang tasks
                            if new_name != old_name:
                                supabase.table("tasks").update({"task": new_name}).eq("task", old_name).execute()
                        except Exception as e:
                            st.error(f"⚠️ Lỗi khi cập nhật {old_name}: {e}")

                    
                    st.success("✅ Đã cập nhật mục lục công việc")
                    refresh_all_cache()

            with col2:
                if st.button("❌ Xóa"):
                    full = edited.copy()
                    for col in meta_cols:
                        full[col] = df_display[col].values

                    to_delete = full[full["Xóa?"] == True]
                    if to_delete.empty:
                        st.warning("⚠️ Bạn chưa tick công việc nào để xoá")
                    else:
                        st.session_state["confirm_delete_jobs"] = to_delete



            if "confirm_delete_jobs" in st.session_state:
                to_delete = st.session_state["confirm_delete_jobs"]
                st.error(f"⚠️ Bạn có chắc muốn xoá {len(to_delete)} công việc: "
                         f"{', '.join(to_delete['Cha'] + to_delete['Con'])}?")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Yes, xoá ngay"):
                        for _, row in to_delete.iterrows():
                            job_id = int(row["_id"])
                            job_name = row["_orig_name"]

                            # Xoá trong tasks
                            supabase.table("tasks").delete().eq("task", job_name).execute()
                            # Xoá trong job_catalog
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
                                    parts = [p.strip() for p in csv_vals.split(",") if p.strip()]
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

            # ===== Xóa =====
            with col2:
                if st.button("❌ Xóa dự án", key="delete_project_btn"):
                    to_delete = edited_proj[edited_proj["Xóa?"] == True]
                    if to_delete.empty:
                        st.warning("⚠️ Bạn chưa tick dự án nào để xoá")
                    else:
                        st.session_state["confirm_delete"] = to_delete["name"].tolist()

            # ===== Hộp xác nhận xoá =====
            if "confirm_delete" in st.session_state:
                proj_list = st.session_state["confirm_delete"]
                st.error(f"⚠️ Bạn có chắc muốn xoá {len(proj_list)} dự án sau: {', '.join(proj_list)} ?")

                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ Yes, xoá ngay", key="confirm_delete_yes"):
                        for proj_name in proj_list:
                            supabase.table("tasks").delete().eq("project", proj_name).execute()
                            supabase.table("projects").delete().eq("name", proj_name).execute()
                            for colu in ("project_manager_of", "project_leader_of"):
                                
                                data_users = supabase.table("users").select(f"username, {colu}").not_.is_(colu, None).execute()
                                for user in data_users.data:
                                    username = user["username"]
                                    csv_vals = user.get(colu) or ""
                                    parts = [p.strip() for p in csv_vals.split(",") if p.strip()]
                                    parts = [p for p in parts if p != proj_name]
                                    new_csv = ",".join(parts) if parts else None
                                    supabase.table("users").update({colu: new_csv}).eq("username", username).execute()

                        
                        st.success("🗑️ Đã xoá các dự án được chọn")
                        del st.session_state["confirm_delete"]
                        refresh_all_cache()

                with c2:
                    if st.button("❌ No, huỷ", key="confirm_delete_no"):
                        st.info("Đã huỷ thao tác xoá")
                        del st.session_state["confirm_delete"]
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
                        "khoi_luong": total_hours,
                        "note": note_txt,
                        "progress": 0
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
        @st.cache_data(ttl=10)
        def load_tasks_by_project(project_name):
            supabase = get_supabase_client()
            data = supabase.table("tasks").select("*").eq("project", project_name).execute()
            return pd.DataFrame(data.data)

        df_tasks = load_tasks_by_project(project)

        if df_tasks.empty:
            st.info("Chưa có công việc nào trong dự án này.")
        else:
            @st.cache_data(ttl=30)
            def load_job_units():
                supabase = get_supabase_client()
                data2 = supabase.table("job_catalog").select("name, unit").execute()
                return pd.DataFrame(data2.data)

            jobs_units = load_job_units()

            df_tasks = df_tasks.merge(jobs_units, left_on="task", right_on="name", how="left")
            df_tasks["assignee"] = df_tasks["assignee"].map(user_map).fillna(df_tasks["assignee"])

            for u in df_tasks["assignee"].unique():
                with st.expander(f"👤 {u}"):
                    df_user = df_tasks[df_tasks["assignee"] == u]

                    df_cong = df_user[df_user["unit"].str.lower() == "công"]
                    df_other = df_user[df_user["unit"].str.lower() != "công"]

                    # ====== Công nhật ======
                    if not df_cong.empty:
                        import re
                        def split_times(note_text: str):
                            if not isinstance(note_text, str):
                                return "", "", ""
                            m = re.search(r'(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})', note_text)
                            if not m:
                                return "", "", note_text
                            start, end = m.group(1), m.group(2)
                            note_rest = re.sub(r'⏰\s*' + re.escape(m.group(0)), "", note_text).strip()
                            return start, end, note_rest

                        rows = []
                        for _, r in df_cong.iterrows():
                            stime, etime, note_rest = split_times(r.get("note", ""))
                            rows.append({
                                "ID": r["id"],
                                "Công việc": r["task"],
                                "Giờ bắt đầu": stime,
                                "Giờ kết thúc": etime,
                                "Ghi chú": note_rest,
                                "Tiến độ (%)": int(pd.to_numeric(r.get("progress", 0), errors="coerce") or 0),
                            })
                        df_cong_show = pd.DataFrame(rows)

                        config = {
                            "Tiến độ (%)": st.column_config.NumberColumn(
                                "Tiến độ (%)", min_value=0, max_value=100, step=1, format="%d%%"
                            ),
                        }

                        
                        

                        

                        st.markdown("**⏱️ Công việc (Công nhật)**")

                        # Tạo bảng hiển thị: thêm cột Khối lượng, ẩn ID, thêm cột Xóa
                        df_cong_show["Khối lượng (giờ)"] = df_cong["khoi_luong"].values if "khoi_luong" in df_cong.columns else 0
                        df_cong_show = df_cong_show.drop(columns=["Tiến độ (%)"], errors="ignore")
                        df_cong_show_display = df_cong_show.drop(columns=["ID"], errors="ignore")
                        df_cong_show_display["Xóa?"] = False

                        # ✅ Chuyển chuỗi "HH:MM" sang kiểu datetime.time để tương thích với TimeColumn
                        def to_time(x):
                            if isinstance(x, datetime.time):
                                return x
                            if isinstance(x, str) and x.strip():
                                try:
                                    h, m = map(int, x.split(":"))
                                    return datetime.time(h, m)
                                except Exception:
                                    return None
                            return None

                        df_cong_show_display["Giờ bắt đầu"] = df_cong_show_display["Giờ bắt đầu"].apply(to_time)
                        df_cong_show_display["Giờ kết thúc"] = df_cong_show_display["Giờ kết thúc"].apply(to_time)

                        # 👉 Sắp xếp thứ tự cột: Công việc | Giờ bắt đầu | Giờ kết thúc | Khối lượng (giờ) | Ghi chú | Xóa?
                        cols_order = [c for c in ["Công việc","Giờ bắt đầu","Giờ kết thúc","Khối lượng (giờ)","Ghi chú","Xóa?"] if c in df_cong_show_display.columns]
                        df_cong_show_display = df_cong_show_display[cols_order]

                        edited_cong = st.data_editor(
                            df_cong_show_display,
                            width="stretch",
                            key=f"editor_cong_{u}",
                            hide_index=True,
                            column_config={
                                "Công việc": st.column_config.TextColumn(disabled=True),
                                "Giờ bắt đầu": st.column_config.TimeColumn("Giờ bắt đầu", format="HH:mm", step=300),
                                "Giờ kết thúc": st.column_config.TimeColumn("Giờ kết thúc", format="HH:mm", step=300),                                "Khối lượng (giờ)": st.column_config.NumberColumn("Khối lượng (giờ)", min_value=0, step=0.25),
                                "Ghi chú": st.column_config.TextColumn("Ghi chú"),
                                "Xóa?": st.column_config.CheckboxColumn("Xóa?", help="Tick để xóa dòng này")
                            }
                        )


                        col1, col2 = st.columns([1,1])

                        with col1:
                            
                            
                            
                            
                            if st.button(f"💾 Lưu cập nhật công nhật của {u}", key=f"save_cong_{u}"):
                                for i, row in edited_cong.iterrows():
                                    tid = int(df_cong.iloc[i]["id"])

                                    # Lấy dữ liệu từ bảng
                                    start_val = row.get("Giờ bắt đầu")
                                    end_val = row.get("Giờ kết thúc")
                                    note_txt = str(row.get("Ghi chú") or "").strip()
                                    new_qty = float(row.get("Khối lượng (giờ)") or 0)

                                    # Nếu là datetime.time thì format sang HH:MM
                                    time_part = ""
                                    if isinstance(start_val, datetime.time) and isinstance(end_val, datetime.time):
                                        s_str = start_val.strftime("%H:%M")
                                        e_str = end_val.strftime("%H:%M")
                                        time_part = f"⏰ {s_str} - {e_str}"
                                    elif isinstance(start_val, str) and isinstance(end_val, str):
                                        # fallback nếu TimeColumn trả về string (trường hợp hiếm)
                                        time_part = f"⏰ {start_val} - {end_val}"

                                    # Gộp giờ + ghi chú
                                    full_note = (time_part + (" " if time_part and note_txt else "") + note_txt).strip()

                                    # Update Supabase
                                    supabase.table("tasks").update({
                                        "khoi_luong": new_qty,
                                        "note": full_note
                                    }).eq("id", tid).execute()

                                st.success(f"✅ Đã cập nhật công nhật của {u}")
                                st.rerun()





                        with col2:
                            if st.button(f"🗑️ Xóa dòng đã chọn của {u}", key=f"delete_cong_{u}"):
                                ids_to_delete = []
                                for i, row in edited_cong.iterrows():
                                    if row.get("Xóa?"):
                                        ids_to_delete.append(int(df_cong.iloc[i]["id"]))


                                if ids_to_delete:
                                    for tid in ids_to_delete:
                                        supabase.table("tasks").delete().eq("id", tid).execute()
                                    
                                    st.success(f"✅ Đã xóa {len(ids_to_delete)} dòng công nhật của {u}")
                                    st.rerun()

                                else:
                                    st.warning("⚠️ Chưa chọn dòng nào để xóa")



                    # ====== Khối lượng ======
                    if not df_other.empty:
                        df_other_show = df_other[[
                            "id", "task", "khoi_luong", "unit", "deadline", "note", "progress"
                        ]].rename(columns={
                            "id": "ID", "task": "Công việc", "khoi_luong": "Khối lượng",
                            "unit": "Đơn vị", "deadline": "Deadline", "note": "Ghi chú",
                            "progress": "Tiến độ (%)"
                        })

                        df_other_show["Deadline"] = pd.to_datetime(df_other_show["Deadline"], errors="coerce").dt.date
                        df_other_show["Khối lượng"] = pd.to_numeric(df_other_show["Khối lượng"], errors="coerce")
                        df_other_show["Tiến độ (%)"] = pd.to_numeric(df_other_show["Tiến độ (%)"], errors="coerce").fillna(0).astype(int)

                        config = {
                            "Đơn vị": st.column_config.TextColumn(disabled=True),
                            "Deadline": st.column_config.DateColumn("Deadline", format="YYYY-MM-DD"),
                            "Tiến độ (%)": st.column_config.NumberColumn(
                                "Tiến độ (%)", min_value=0, max_value=100, step=1, format="%d%%"
                            ),
                        }

                        
                        st.markdown("**📦 Công việc theo khối lượng**")

                       
                        # ✅ Thêm ID vào dữ liệu hiển thị (ẩn cột khi render)
                        df_other_show["Xóa?"] = False
                        df_other_display = df_other_show.copy()
                        df_other_display["Xóa?"] = False  # thêm cột xóa mặc định False

                        # Hiển thị DataEditor
                        edited_other = st.data_editor(
                            df_other_display,
                            width="stretch",
                            key=f"editor_other_{u}",
                            # hide_index=True,
                            column_config={
                                "ID": st.column_config.NumberColumn("ID", disabled=True),
                                "Đơn vị": st.column_config.TextColumn(disabled=True),
                                "Deadline": st.column_config.DateColumn("Deadline", format="YYYY-MM-DD"),
                                "Tiến độ (%)": st.column_config.NumberColumn(
                                    "Tiến độ (%)", min_value=0, max_value=100, step=1, format="%d%%"
                                ),
                                "Xóa?": st.column_config.CheckboxColumn("Xóa?", help="Tick để xoá dòng này"),
                            }
                        )

                        # Hai nút song song (Cập nhật & Xoá)
                        col1, col2 = st.columns([1, 1])

                        # ===== Nút cập nhật =====
                        with col1:                            
                            if st.button(f"💾 Cập nhật khối lượng của {u}", key=f"save_other_{u}"):
                                for i, row in edited_other.iterrows():
                                    try:
                                        # Lấy id thật từ bản hiển thị
                                        tid = int(row.get("ID", 0))
                                        if not tid:
                                            continue

                                        # Lấy giá trị đã chỉnh sửa
                                        new_qty = float(row.get("Khối lượng") or 0)
                                        note_val = str(row.get("Ghi chú") or "").strip()
                                        progress_val = int(float(row.get("Tiến độ (%)") or 0))  # ✅ ép kiểu int để không bị lỗi "0.0"

                                        # Chuẩn hóa Deadline
                                        dl = row.get("Deadline")
                                        if isinstance(dl, (datetime.date, pd.Timestamp)):
                                            dl_str = pd.to_datetime(dl).strftime("%Y-%m-%d")
                                        elif isinstance(dl, str) and dl.strip():
                                            parsed = pd.to_datetime(dl, errors="coerce")
                                            dl_str = parsed.strftime("%Y-%m-%d") if pd.notna(parsed) else None
                                        else:
                                            dl_str = None

                                        # Cập nhật thật vào Supabase
                                        supabase.table("tasks").update({
                                            "khoi_luong": new_qty,
                                            "note": note_val,
                                            "progress": progress_val,
                                            "deadline": dl_str
                                        }).eq("id", tid).execute()

                                    except Exception as e:
                                        st.warning(f"⚠️ Lỗi cập nhật dòng {i+1}: {e}")

                                st.success(f"✅ Đã cập nhật công việc khối lượng của {u}")
                                st.rerun()


                        # ===== Nút xóa =====
                        with col2:
                            if st.button(f"🗑️ Xoá dòng đã chọn của {u}", key=f"delete_other_{u}"):
                                selected_ids = df_other_display.loc[edited_other["Xóa?"] == True, "ID"].tolist()
                                if selected_ids:
                                    for tid in selected_ids:
                                        supabase.table("tasks").delete().eq("id", tid).execute()
                                    st.success(f"🗑️ Đã xoá {len(selected_ids)} công việc.")
                                    st.rerun()

                                else:
                                    st.info("⚠️ Bạn chưa tick dòng nào để xoá.")

    elif choice == "Chấm công – Nghỉ phép":
        st.subheader("🕒 Quản lý chấm công và nghỉ phép")

        import datetime as dt
        import json
        from st_aggrid import GridOptionsBuilder, AgGrid, GridUpdateMode, JsCode
        from auth import get_connection

        supabase = get_connection()
        df_users = load_users_cached()

        # ====== Xác định tháng hiện tại ======
        today = pd.Timestamp(dt.date.today())
        selected_month = st.date_input("📅 Chọn tháng", dt.date(today.year, today.month, 1))
        first_day = selected_month.replace(day=1)
        next_month = (first_day + dt.timedelta(days=32)).replace(day=1)
        days = pd.date_range(first_day, next_month - dt.timedelta(days=1))

        month_str = selected_month.strftime("%Y-%m")

        # ====== Lấy dữ liệu chấm công ======
        res = supabase.table("attendance_monthly").select("*").eq("month", month_str).execute()
        df_att = pd.DataFrame(res.data) if res.data else pd.DataFrame(columns=["user_id", "month", "work_days", "half_days", "off_days"])

        # Chuyển JSON string → list
        for c in ["work_days", "half_days", "off_days"]:
            if c in df_att.columns:
                df_att[c] = df_att[c].apply(lambda x: json.loads(x) if isinstance(x, str) else (x or []))
            else:
                df_att[c] = [[] for _ in range(len(df_att))]

        # ====== Khởi tạo dữ liệu hiển thị ======
        rows = []
        for _, u in df_users.iterrows():
            uid = u["id"]
            uname = u["display_name"]
            record = df_att[df_att["user_id"] == uid]

            if not record.empty:
                work_days = record["work_days"].iloc[0]
                half_days = record["half_days"].iloc[0]
                off_days = record["off_days"].iloc[0]
            else:
                # Tạo mặc định (T2-6: work, T7-CN: off, tương lai: trống)
                work_days, half_days, off_days = [], [], []
                for d in days:
                    if d.date() > today.date():
                        continue
                    if d.weekday() < 5:
                        work_days.append(d.day)
                    else:
                        off_days.append(d.day)

            row = {"user_id": uid, "User": uname}
            total = 0
            for d in days:
                col = d.strftime("%d/%m")
                if d.date() > today.date():
                    row[col] = ""
                    continue
                if d.day in work_days:
                    row[col] = "work"
                    total += 1
                elif d.day in half_days:
                    row[col] = "half"
                    total += 0.5
                elif d.day in off_days:
                    row[col] = "off"
                else:
                    row[col] = ""
            row["Số ngày đi làm"] = total
            rows.append(row)

        df_display = pd.DataFrame(rows)
        df_display = df_display[["User", "Số ngày đi làm"] + [d.strftime("%d/%m") for d in days]]

        # ====== Lưu bản gốc trong session ======
        session_key = f"attendance_{month_str}"
        if session_key not in st.session_state:
            st.session_state[session_key] = df_display.copy()
            st.session_state[f"{session_key}_changes"] = set()

        # ====== Hiển thị AgGrid ======
        color_js = JsCode("""
            function(params) {
                if (params.value === 'work') return {'backgroundColor': '#b6f5b6', 'textAlign': 'center'};
                else if (params.value === 'half') return {'backgroundColor': '#ffe97f', 'textAlign': 'center'};
                else if (params.value === 'off') return {'backgroundColor': '#ff9999', 'textAlign': 'center'};
                return {'textAlign': 'center'};
            }
        """)

        gb = GridOptionsBuilder.from_dataframe(df_display)
        gb.configure_default_column(editable=True, resizable=True)
        gb.configure_column("User", editable=False, width=160)
        gb.configure_column("Số ngày đi làm", editable=False, width=140)

        for d in days:
            editable = d.date() <= today.date()
            gb.configure_column(
                d.strftime("%d/%m"),
                cellEditor='agSelectCellEditor',
                cellEditorParams={'values': ['work', 'half', 'off', '']},
                editable=editable,
                cellStyle=color_js,
                width=80
            )

        grid_response = AgGrid(
            st.session_state[session_key],
            gridOptions=gb.build(),
            update_mode=GridUpdateMode.VALUE_CHANGED,
            allow_unsafe_jscode=True,
            fit_columns_on_grid_load=True,
            height=600
        )

        updated_df = pd.DataFrame(grid_response["data"])

        # ====== Ghi nhớ ô đã sửa ======
        changed_rows = grid_response.get("data", [])
        if "changedCells" in grid_response:
            for cell in grid_response["changedCells"]:
                row_index = cell.get("rowIndex")
                col_id = cell.get("colId")
                if row_index is not None and col_id and "/" in col_id:
                    st.session_state[f"{session_key}_changes"].add((row_index, col_id))

        # ====== Cập nhật tổng ngày đi làm tạm thời ======
        for i in range(len(updated_df)):
            total = 0
            for col in updated_df.columns:
                if "/" not in col:
                    continue
                v = updated_df.loc[i, col]
                if v == "work": total += 1
                elif v == "half": total += 0.5
            updated_df.loc[i, "Số ngày đi làm"] = total

        st.session_state[session_key] = updated_df.copy()

        # ====== Nút cập nhật ======
        if st.button("💾 Cập nhật thay đổi"):
            with st.spinner("Đang cập nhật vào database..."):
                changes = st.session_state[f"{session_key}_changes"]
                if not changes:
                    st.info("Không có thay đổi nào để cập nhật.")
                else:
                    for idx, row in updated_df.iterrows():
                        if not any(c[0] == idx for c in changes):
                            continue  # chỉ cập nhật những dòng có thay đổi

                        work_days, half_days, off_days = [], [], []
                        for col in updated_df.columns:
                            if "/" not in col:
                                continue
                            val = row[col]
                            day_num = int(col.split("/")[0])
                            if val == "work":
                                work_days.append(day_num)
                            elif val == "half":
                                half_days.append(day_num)
                            elif val == "off":
                                off_days.append(day_num)

                        supabase.table("attendance_monthly").upsert({
                            "user_id": df_users.iloc[idx]["id"],
                            "month": month_str,
                            "work_days": work_days,
                            "half_days": half_days,
                            "off_days": off_days
                        }).execute()

                    st.session_state[f"{session_key}_changes"].clear()
                    st.success("✅ Đã cập nhật dữ liệu chấm công thành công!")

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
        
