# project_manager_app.py
import streamlit as st
import pandas as pd
import plotly.express as px
from auth import get_connection

import re

from datetime import datetime, date, time, timedelta
from auth import calc_hours



# -----------------------------
# Helpers
# -----------------------------
def _load_managed_projects(supabase, username: str) -> list[str]:
    """Tên các dự án user là Chủ nhiệm/Chủ trì (từ bảng users)."""
    data = supabase.table("users").select("project_manager_of, project_leader_of").eq("username", username).execute()
    info = pd.DataFrame(data.data)
    managed = []
    if not info.empty:
        for col in ["project_manager_of", "project_leader_of"]:
            val = info.at[0, col]
            if pd.notna(val) and str(val).strip():
                # ✅ Ưu tiên tách theo dấu |
                parts = [p.strip() for p in str(val).split("|") if p.strip()]
                managed += parts

    return sorted(set(managed))



def _load_visible_projects(supabase, managed: list[str], username: str) -> pd.DataFrame:
    """Dự án user có thể thấy: managed + public + dự án có task của user."""
    try:
        # Dự án public
        data = supabase.table("projects").select("id, name, deadline, project_type")\
            .eq("project_type", "public").execute()
        public_df = pd.DataFrame(data.data)
    except Exception:
        # 🔁 Nếu lỗi, tạo lại kết nối Supabase
        from auth import get_connection
        supabase = get_connection()
        data = supabase.table("projects").select("id, name, deadline, project_type")\
            .eq("project_type", "public").execute()
        public_df = pd.DataFrame(data.data)

    # Dự án do user quản lý
    managed_df = pd.DataFrame(columns=["id", "name", "deadline", "project_type"])
    if managed and len(managed) > 0:
        try:
            data = supabase.table("projects").select("id, name, deadline, project_type")\
                .in_("name", managed).execute()
            managed_df = pd.DataFrame(data.data)
        except Exception as e:
            st.warning(f"⚠️ Không tải được danh sách dự án do bạn quản lý: {e}")


    # Dự án user được giao task
    data = supabase.table("tasks").select("project").eq("assignee", username).execute()
    assigned_names = list({r["project"] for r in data.data})
    if assigned_names:
        data = supabase.table("projects").select("id, name, deadline, project_type")\
            .in_("name", assigned_names).execute()
        assigned_df = pd.DataFrame(data.data)
    else:
        assigned_df = pd.DataFrame(columns=["id", "name", "deadline", "project_type"])

    # Gộp kết quả
    all_df = pd.concat([public_df, managed_df, assigned_df], ignore_index=True) \
               .drop_duplicates(subset=["name"]) \
               .sort_values("name") \
               .reset_index(drop=True)
    return all_df



# -----------------------------
# Main app
# -----------------------------
def project_manager_app(user):
    """
    Giao diện cho Chủ nhiệm/Chủ trì và người dùng có nhiệm vụ trong dự án:
    - Quản lý giao việc (nếu là quản lý dự án)
    - Xem/sửa khối lượng của chính mình (chỉ mình), thêm việc ở dự án public
    - Thống kê công việc (chỉ các dự án mình quản lý)
    """
    # st.set_page_config(layout="wide")
    supabase = get_connection()
    try:
        # 🕒 Cập nhật thời điểm truy cập cuối cùng của user
        supabase.table("users").update(
            {"last_seen": datetime.utcnow().isoformat()}
        ).eq("username", user[1]).execute()
    except Exception as e:
        st.warning(f"⚠️ Không thể cập nhật thời gian truy cập: {e}")

    # 🧭 Tải danh sách người dùng
    try:
        data = supabase.table("users").select("username, display_name").execute()
        df_users = pd.DataFrame(data.data)
    except Exception as e:
        st.error(f"❌ Lỗi khi tải danh sách người dùng: {e}")
        df_users = pd.DataFrame(columns=["username", "display_name"])

    # ✅ Kiểm tra dữ liệu tránh KeyError
    if df_users.empty or "username" not in df_users.columns:
        st.error("⚠️ Không tải được danh sách người dùng. Vui lòng kiểm tra kết nối Supabase hoặc bảng 'users'.")
        return

    # 🧩 Tạo map username → display_name (nếu thiếu display_name thì fallback bằng username)
    user_map = dict(zip(df_users["username"], df_users.get("display_name", df_users["username"])))

    username = user[1]

    managed = _load_managed_projects(supabase, username)
    projects_df = _load_visible_projects(supabase, managed, username)

    if projects_df.empty:
        st.warning("⚠️ Chưa có dự án nào bạn có quyền xem hoặc quản lý.")
        return

    choice = st.sidebar.radio("Chức năng", ["Quản lý Giao Việc", "Thống kê Công Việc"])

        # ===========================================================
        # 1) QUẢN LÝ GIAO VIỆC / NHIỆM VỤ CỦA TÔI
        # ===========================================================
    if choice == "Quản lý Giao Việc":
        st.subheader("📝 Quản lý & Nhiệm vụ")

        # Chọn dự án
        project = st.selectbox("Chọn dự án", projects_df["name"].tolist(), key="pm_proj_select")
        prow = projects_df.loc[projects_df["name"] == project].iloc[0]
        proj_deadline = prow["deadline"]
        proj_type = (prow["project_type"] or "group").strip().lower()
        is_public = (proj_type == "public")
        is_manager = project in managed

        # Chuẩn hoá job_catalog: NULL -> 'group'
        # ✅ An toàn hơn: Chuẩn hoá job_catalog để tránh lỗi NULL / mất kết nối
        try:
            supabase.table("job_catalog").update({"project_type": "group"}).is_("project_type", None).execute()
        except Exception:
            st.warning("⚠️ Không thể chuẩn hoá dữ liệu job_catalog, thử lại sau.")

        # ✅ Lấy danh mục công việc an toàn
        try:
            data = supabase.table("job_catalog").select("id, name, unit, parent_id") \
                .eq("project_type", proj_type).execute()
            jobs = pd.DataFrame(data.data)
        except Exception as e:
            st.error(f"❌ Lỗi khi tải danh mục công việc: {e}")
            st.stop()

        parent_jobs = jobs[jobs["parent_id"].isnull()].sort_values("name")

        # =======================================================
        # A. QUẢN LÝ DỰ ÁN: giao việc + xem/sửa toàn bộ công việc
        # =======================================================
        if is_manager:
            st.info("🔐 Bạn là **Quản lý dự án** này — có quyền giao việc cho mọi người.")

            # ---- Giao nhiều việc cùng lúc ----
            all_users_display = df_users["display_name"].tolist()
            assignee_display = st.selectbox("Giao việc cho", all_users_display, key="pm_assignee")
            assignee = df_users.loc[df_users["display_name"] == assignee_display, "username"].iloc[0]


            if "pm_rows" not in st.session_state:
                st.session_state.pm_rows = [0]

            st.markdown("**Nhập các dòng giao việc**")
            h1, h2, h3, h4, h5 = st.columns([2, 2, 2, 2, 2])
            h1.markdown("**Đầu mục**")
            h2.markdown("**Công việc**")

            if is_public:
                h3.markdown("**Giờ bắt đầu**")
                h4.markdown("**Giờ kết thúc**")
            else:
                h3.markdown("**Khối lượng**")
                h4.markdown("**Đơn vị**")

            h5.markdown("**Deadline**")


            for i, _ in enumerate(st.session_state.pm_rows):
                c1, c2, c3, c4, c5 = st.columns([2, 2, 2, 2, 2])
                with c1:
                    p_choice = st.selectbox(
                        "", parent_jobs["name"].tolist(),
                        key=f"pm_parent_{i}", label_visibility="collapsed"
                    )
                pid = int(parent_jobs.loc[parent_jobs["name"] == p_choice, "id"].iloc[0])
                childs = jobs[jobs["parent_id"] == pid].sort_values("name")
                with c2:
                    child_choice = st.selectbox(
                        "", childs["name"].tolist(),
                        key=f"pm_child_{i}", label_visibility="collapsed"
                    )

                task_name = child_choice or p_choice
                unit = jobs.loc[jobs["name"] == task_name, "unit"].iloc[0] if task_name in jobs["name"].values else ""

                if str(unit).strip().lower() == "công":
                    with c3:
                        st.time_input("", pd.to_datetime("08:00").time(), key=f"pm_start_{i}", label_visibility="collapsed")
                    with c4:
                        st.time_input("", pd.to_datetime("17:00").time(), key=f"pm_end_{i}", label_visibility="collapsed")
                    with c5:
                        st.empty()  # không dùng deadline cho công nhật
                else:
                    with c3:
                        st.number_input("", min_value=0.0, step=0.1, key=f"pm_qty_{i}", label_visibility="collapsed")
                    with c4:
                        st.text_input("", value=unit, key=f"pm_unit_{i}", disabled=True, label_visibility="collapsed")
                    with c5:
                        default_dl = pd.to_datetime(proj_deadline) if proj_deadline else None
                        st.date_input("", value=default_dl, key=f"pm_deadline_{i}", label_visibility="collapsed")

            st.button("➕ Thêm dòng", key="pm_add_row", on_click=lambda: st.session_state.pm_rows.append(len(st.session_state.pm_rows)))

            note_common = st.text_area("📝 Ghi chú chung", key="pm_note_common")

            if st.button("✅ Giao việc", key="pm_assign_btn"):
                for i in range(len(st.session_state.pm_rows)):
                    p_choice = st.session_state.get(f"pm_parent_{i}")
                    child_choice = st.session_state.get(f"pm_child_{i}")
                    task_name = child_choice or p_choice
                    if not task_name:
                        continue
                    unit = jobs.loc[jobs["name"] == task_name, "unit"].iloc[0] if task_name in jobs["name"].values else ""

                    if str(unit).strip().lower() == "công":
                        stime = st.session_state.get(f"pm_start_{i}")
                        etime = st.session_state.get(f"pm_end_{i}")
                        time_txt = f"⏰ {stime} - {etime}" if stime and etime else ""
                        note = (note_common + ("\n" if note_common and time_txt else "") + time_txt).strip()
                        supabase.table("tasks").insert({
                            "project": project,
                            "task": task_name,
                            "assignee": assignee,
                            "note": note,
                            "progress": 0
                        }).execute()
                    else:
                        qty = float(st.session_state.get(f"pm_qty_{i}", 0) or 0)
                        dl_val = st.session_state.get(f"pm_deadline_{i}")
                        dl = pd.to_datetime(dl_val, errors="coerce")
                        dl_str = dl.strftime("%Y-%m-%d") if pd.notna(dl) else None
                        supabase.table("tasks").insert({
                            "project": project,
                            "task": task_name,
                            "assignee": assignee,
                            "deadline": dl_str,
                            "khoi_luong": qty,
                            "note": note_common,
                            "progress": 0
                        }).execute()
                
                st.success("✅ Đã giao việc")
                st.rerun()

            # ---- Bảng tất cả công việc: sửa & lưu tiến độ ----
            # ---- Bảng tất cả công việc: sửa & lưu tiến độ ----
            st.subheader("📋 Tất cả công việc trong dự án")

            
            data = supabase.table("tasks").select("id, assignee, task, khoi_luong, deadline, note, progress").eq("project", project).execute()
            df_all = pd.DataFrame(data.data)
            df_all["assignee"] = df_all["assignee"].map(user_map).fillna(df_all["assignee"])

            if df_all.empty:
                st.info("⚠️ Chưa có công việc nào trong dự án này.")
            else:
                # Đổi tên cột sang tiếng Việt
                df_all = df_all.rename(columns={
                    "id": "ID",
                    "assignee": "Người thực hiện",
                    "task": "Công việc",
                    "khoi_luong": "Khối lượng",
                    "deadline": "Deadline",
                    "note": "Ghi chú",
                    "progress": "Tiến độ (%)",
                })

                # Ép kiểu Deadline về datetime nếu có giá trị
                if "Deadline" in df_all.columns:
                    df_all["Deadline"] = pd.to_datetime(df_all["Deadline"], errors="coerce")

                # 👉 Tạo bản hiển thị: ẩn cột ID và thêm cột Xóa?
                df_display = df_all.drop(columns=["ID"], errors="ignore").copy()
                df_display["Xóa?"] = False

                edited_df = st.data_editor(
                    df_display,
                    width="stretch",
                    key=f"editor_all_{project}",
                    hide_index=True,
                    column_config={
                        "Người thực hiện": st.column_config.TextColumn(disabled=True),
                        "Công việc": st.column_config.TextColumn(disabled=True),
                        "Khối lượng": st.column_config.NumberColumn("Khối lượng", min_value=0, step=0.25),
                        "Deadline": st.column_config.DateColumn("Deadline", format="YYYY-MM-DD"),
                        "Ghi chú": st.column_config.TextColumn(),
                        "Tiến độ (%)": st.column_config.NumberColumn("Tiến độ (%)", min_value=0, max_value=100, step=1),
                        "Xóa?": st.column_config.CheckboxColumn("Xóa?", help="Tick để xóa dòng này")
                    }
                )

                col1, col2 = st.columns([1, 1])

                # Nút lưu cập nhật công việc
                with col1:                        
                    if st.button("💾 Lưu cập nhật công việc", key=f"save_all_{project}"):
                        supabase = get_connection()  # ✅ Tạo lại kết nối Supabase ngay trước khi update
                    
                        for i, row in edited_df.iterrows():
                            task_id = int(df_all.iloc[i]["ID"])
                            update_data = {}

                            # --- Khối lượng ---
                            if "Khối lượng" in row and not pd.isna(row["Khối lượng"]):
                                try:
                                    val = float(row["Khối lượng"])
                                    update_data["khoi_luong"] = int(val) if val.is_integer() else round(val, 2)
                                except Exception:
                                    update_data["khoi_luong"] = 0

                            # --- Tiến độ ---
                            if "Tiến độ (%)" in row and not pd.isna(row["Tiến độ (%)"]):
                                try:
                                    val = float(row["Tiến độ (%)"])
                                    update_data["progress"] = int(val) if val.is_integer() else round(val, 2)
                                except Exception:
                                    update_data["progress"] = 0

                            # --- Deadline ---
                            if "Deadline" in row and pd.notna(row["Deadline"]):
                                update_data["deadline"] = pd.to_datetime(row["Deadline"]).strftime("%Y-%m-%d")

                            # --- Ghi chú ---
                            if "Ghi chú" in row:
                                val = row["Ghi chú"]
                                if val is None or (isinstance(val, float) and pd.isna(val)):
                                    val = ""
                                else:
                                    val = str(val).strip()
                                update_data["note"] = val

                            # --- Nếu có dữ liệu để cập nhật ---
                            if update_data:
                                try:
                                    supabase.table("tasks").update(update_data).eq("id", task_id).execute()
                                except Exception as e:
                                    st.error(f"❌ Lỗi khi cập nhật task {task_id}: {e}")

                    
                        st.success("✅ Đã lưu cập nhật công việc vào cơ sở dữ liệu!")
                        st.rerun()





                # Nút xóa các dòng đã chọn
                with col2:
                    if st.button("🗑️ Xóa các dòng đã chọn", key=f"delete_all_{project}"):
                        ids_to_delete = []
                        for i, row in edited_df.iterrows():
                            if row.get("Xóa?"):
                                ids_to_delete.append(int(df_all.iloc[i]["ID"]))
                        if ids_to_delete:
                            for tid in ids_to_delete:
                                supabase.table("tasks").delete().eq("id", tid).execute()
                            
                            st.success(f"✅ Đã xóa {len(ids_to_delete)} công việc")
                            st.rerun()
                        else:
                            st.warning("⚠️ Chưa chọn dòng nào để xóa")



        # =======================================================
        # B. KHÔNG phải quản lý: chỉ sửa việc của mình + thêm ở Public
        # =======================================================
        # =======================================================
        # B. KHÔNG phải quản lý: chỉ sửa việc của mình + thêm ở Public
        # =======================================================
        else:
            st.info(
                "👤 Bạn **không phải quản lý** dự án này. "
                "Bạn có thể chỉnh **khối lượng** các việc của mình."
                + (" Bạn cũng có thể **thêm khối lượng mới** vì đây là dự án **public**." if is_public else "")
            )

            # ====== Danh sách công việc của chính user ======
            data = supabase.table("tasks").select("id, task, khoi_luong, deadline, note, progress")\
                .eq("project", project).eq("assignee", username).execute()
            my_tasks = pd.DataFrame(data.data)
            # === Tách giờ bắt đầu và kết thúc từ note nếu có dạng "⏰ 08:00 - 17:00 (...)" ===
            def extract_times(note):
                match = re.search(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", str(note))
                if match:
                    return match.group(1), match.group(2)
                return "", ""

            if not my_tasks.empty:
                my_tasks["Giờ bắt đầu"], my_tasks["Giờ kết thúc"] = zip(*my_tasks["note"].map(extract_times))

                def _to_time(x):
                    if x is None or str(x).strip() == "":
                        return None
                    try:
                        return pd.to_datetime(str(x), format="%H:%M").time()
                    except Exception:
                        try:
                            return pd.to_datetime(str(x)).time()
                        except Exception:
                            return None

                my_tasks["Giờ bắt đầu"] = my_tasks["Giờ bắt đầu"].map(_to_time)
                my_tasks["Giờ kết thúc"] = my_tasks["Giờ kết thúc"].map(_to_time)
            
                        
            # 🧹 Làm sạch ghi chú: loại bỏ trùng lặp giờ/ngày nếu có
            if not my_tasks.empty and "note" in my_tasks.columns:
                def clean_note(n: str):
                    if not isinstance(n, str) or not n.strip():
                        return ""
                    # Giữ lại duy nhất phần đầu chứa "⏰ HH:MM - HH:MM (...)" nếu xuất hiện nhiều
                    matches = re.findall(r"⏰\s*\d{2}:\d{2}\s*-\s*\d{2}:\d{2}.*?\)", n)
                    if len(matches) > 1:
                        rest = n.split(matches[-1])[-1].strip()
                        return f"{matches[0]} {rest}".strip()
                    return n.strip()

                my_tasks["note"] = my_tasks["note"].map(clean_note)




            if my_tasks.empty:
                st.warning("⚠️ Bạn chưa có công việc nào trong dự án này.")
            else:
                # DataFrame hiển thị (ẩn ID nhưng vẫn giữ dữ liệu ID trong my_tasks)
                df_show = my_tasks.rename(columns={
                    "task": "Công việc",
                    "khoi_luong": "Khối lượng (giờ)" if is_public else "Khối lượng",
                    "deadline": "Deadline",
                    "note": "Ghi chú",
                    "progress": "Tiến độ (%)"
                }).drop(columns=["id"])  # 👈 bỏ ID khỏi hiển thị

                # Thêm cột chọn để xóa
                df_show["Chọn"] = False

                # Nếu dự án Public -> bỏ Deadline và Tiến độ
                if is_public:
                    drop_cols = [c for c in ["Deadline", "Tiến độ (%)"] if c in df_show.columns]
                    df_show = df_show.drop(columns=drop_cols, errors="ignore")

                # Hiển thị bảng cho user chỉnh sửa (không có cột ID)
                edited = st.data_editor(
                    df_show,
                    key="my_tasks_editor",
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "Công việc": st.column_config.TextColumn(disabled=True),
                        "Giờ bắt đầu": st.column_config.TimeColumn("Giờ bắt đầu", format="HH:mm"),
                        "Giờ kết thúc": st.column_config.TimeColumn("Giờ kết thúc", format="HH:mm"),
                        "Ghi chú": st.column_config.TextColumn(),
                        "Chọn": st.column_config.CheckboxColumn("Xóa?", help="Tick để xóa dòng này")
                    }
                )


                col1, col2 = st.columns([2, 1])
                with col1:
                    
                    
                    if st.button("💾 Lưu khối lượng của tôi", key="save_my_qty_btn"):
                        

                        def _fmt_time(t):
                            if isinstance(t, time):
                                return t.strftime("%H:%M")
                            s = str(t).strip()
                            for fmt in ("%H:%M", "%H:%M:%S"):
                                try:
                                    return datetime.strptime(s, fmt).strftime("%H:%M")
                                except Exception:
                                    pass
                            return ""

                        def _parse_time(t):
                            if isinstance(t, time):
                                return datetime.combine(date.today(), t)
                            s = str(t).strip()
                            for fmt in ("%H:%M", "%H:%M:%S"):
                                try:
                                    return datetime.strptime(s, fmt)
                                except Exception:
                                    pass
                            return None

                        for i, row in edited.iterrows():
                            tid = int(my_tasks.iloc[i]["id"])
                            update_data = {}

                            start_time = row.get("Giờ bắt đầu", "")
                            end_time = row.get("Giờ kết thúc", "")
                            note_text = str(row.get("Ghi chú", "")).strip()

                            # 🧹 Giữ lại phần ngày nếu có
                            match_date = re.search(r"\(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}\)", note_text)
                            date_part = match_date.group(0) if match_date else ""

                            # 🧹 Xóa phần giờ cũ để tránh lặp
                            note_text = re.sub(r"^⏰\s*\d{2}:\d{2}(?::\d{2})?\s*-\s*\d{2}:\d{2}(?::\d{2})?", "", note_text)
                            note_text = re.sub(r"\(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}\)", "", note_text).strip()

                            # 🕒 Ghép lại ghi chú mới
                            start_str = _fmt_time(start_time)
                            end_str = _fmt_time(end_time)
                            if start_str and end_str:
                                new_note = f"⏰ {start_str} - {end_str} {date_part} {note_text}".strip()
                            else:
                                new_note = note_text
                            update_data["note"] = new_note

                            # 🧮 Tính lại khối lượng (giờ)
                            try:
                                # Lấy ngày từ note nếu có (dạng "(YYYY-MM-DD - YYYY-MM-DD)")
                                match_date = re.search(r"\((\d{4}-\d{2}-\d{2})\s*-\s*(\d{4}-\d{2}-\d{2})\)", note_text)
                                if match_date:
                                    start_date_str, end_date_str = match_date.groups()
                                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
                                    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
                                else:
                                    # Nếu không có trong note thì mặc định cùng ngày hôm nay
                                    start_date = end_date = date.today()

                                # Dùng hàm chuẩn calc_hours từ auth.py
                                total_hours = calc_hours(start_date, end_date, start_time, end_time)
                                if total_hours > 0:
                                    update_data["khoi_luong"] = round(total_hours, 2)
                            except Exception as e:
                                st.warning(f"⚠️ Lỗi tính khối lượng cho dòng {i+1}: {e}")


                            supabase.table("tasks").update(update_data).eq("id", tid).execute()

                        st.success("✅ Đã cập nhật giờ, ghi chú và khối lượng!")
                        st.rerun()

                with col2:
                    if st.button("🗑️ Xóa các dòng đã chọn", key="delete_my_tasks_btn"):
                        ids_to_delete = []
                        for i, row in edited.iterrows():
                            if row.get("Chọn"):
                                ids_to_delete.append(int(my_tasks.iloc[i]["id"]))
                        if ids_to_delete:
                            for tid in ids_to_delete:
                                supabase.table("tasks").delete().eq("id", tid).execute()
                            
                            st.success(f"✅ Đã xóa {len(ids_to_delete)} dòng")
                            st.rerun()
                        else:
                            st.warning("⚠️ Chưa chọn dòng nào để xóa")

            # ====== Tự thêm công việc cho bản thân (nếu Public) ======
            if is_public:
                st.markdown("---")
                st.subheader("➕ Thêm khối lượng / công nhật cho bản thân")

                task_name = st.selectbox("Công việc", jobs["name"].tolist(), key="self_task")

                # ---- Chọn ngày & giờ (4 cột trên 1 hàng) ----
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    start_date = st.date_input("Ngày bắt đầu", key="my_start_date")
                with col2:
                    start_time = st.time_input("Giờ bắt đầu", time(8, 0), key="my_start_time")
                with col3:
                    end_date = st.date_input("Ngày kết thúc", key="my_end_date", value=start_date)
                with col4:
                    end_time = st.time_input("Giờ kết thúc", time(17, 0), key="my_end_time")

                note = st.text_area("📝 Ghi chú (tuỳ chọn)", key="my_note")

                if st.button("➕ Thêm công nhật cho tôi", key="add_self_cong_btn"):
                    total_hours = calc_hours(start_date, end_date, start_time, end_time)
                    # 📝 Tạo ghi chú gọn, chỉ thêm 1 lần
                    if note.strip():
                        note_txt = f"⏰ {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} ({start_date} - {end_date}) {note.strip()}"
                    else:
                        note_txt = f"⏰ {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} ({start_date} - {end_date})"


                    supabase.table("tasks").insert({
                        "project": project,
                        "task": task_name,
                        "assignee": username,
                        "khoi_luong": total_hours,
                        "note": note_txt,
                        "progress": 0
                    }).execute()
                    
                    st.success(f"✅ Đã thêm {total_hours} giờ công cho công việc '{task_name}'")
                    st.rerun()



    # ===========================================================
    # 2) THỐNG KÊ CÔNG VIỆC (chỉ dự án mình quản lý)
    # ===========================================================
    else:
        st.subheader("📊 Thống kê Công Việc")
        if not managed:
            st.info("⚠️ Bạn không phải Chủ nhiệm/Chủ trì dự án nào nên không có dữ liệu thống kê.")
            return

        all_projects = managed
        selected_projects = st.multiselect(
            "Chọn dự án cần thống kê", all_projects, default=all_projects, key="stat_proj_multi"
        )
        if not selected_projects:
            st.info("⚠️ Không có dữ liệu công việc.")
            return

        qmarks = ",".join(["%s"] * len(selected_projects))
        
        # ✅ Lấy đầy đủ cột bao gồm assignee để tránh KeyError
        data = supabase.table("tasks").select("id, project, task, assignee, khoi_luong, note, progress, created_at, deadline").in_("project", selected_projects).execute()
        df = pd.DataFrame(data.data)

        # 🛡️ Kiểm tra cột assignee để tránh KeyError
        if "assignee" in df.columns:
            df["assignee"] = df["assignee"].map(user_map).fillna(df["assignee"])
        else:
            st.warning("⚠️ Dữ liệu tasks không có cột 'assignee'. Vui lòng kiểm tra bảng 'tasks' trên Supabase.")
            df["assignee"] = "Không xác định"

        if df.empty:
            st.info("⚠️ Không có dữ liệu công việc.")
            return

        stat_mode = st.radio("Xem theo", ["Dự án", "Người dùng"], key="stat_mode")

        if stat_mode == "Dự án":
            proj_summary = df.groupby("project").agg(
                Tổng_công_việc=("id", "count"),
                Hoàn_thành=("progress", lambda x: (x == 100).sum()),
                Chưa_hoàn_thành=("progress", lambda x: (x < 100).sum()),
                Tiến_độ_TB=("progress", "mean"),
            ).reset_index().rename(columns={"project": "Dự án"})

            st.dataframe(
                proj_summary.style.format({"Tiến_độ_TB": "{:.0f}%"}).bar(subset=["Tiến_độ_TB"], color="#4CAF50"),
                use_container_width=True
            )

            fig = px.bar(
                proj_summary, x="Dự án", y="Tiến_độ_TB", color="Dự án", text="Tiến_độ_TB",
                title="Tiến độ các dự án"
            )
            fig.update_traces(texttemplate='%{text:.0f}%', textposition="outside")
            fig.update_layout(yaxis=dict(title="Tiến độ (%)", range=[0, 100]), showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        else:
            grouped = df.groupby(["assignee", "project"]).agg(
                Tổng_công_việc=("id", "count"),
                Hoàn_thành=("progress", lambda x: (x == 100).sum()),
                Chưa_hoàn_thành=("progress", lambda x: (x < 100).sum()),
                Tiến_độ_TB=("progress", "mean"),
            ).reset_index().rename(columns={"assignee": "Người dùng", "project": "Dự án"})

            st.dataframe(
                grouped.style.format({"Tiến_độ_TB": "{:.0f}%"}).bar(subset=["Tiến_độ_TB"], color="#FF9800"),
                use_container_width=True
            )






