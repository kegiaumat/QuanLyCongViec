# user_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from auth import get_connection, calc_hours
from supabase import create_client

import re

def _load_visible_projects(supabase, username: str) -> pd.DataFrame:
    """
    Lấy danh sách dự án user đang có nhiệm vụ hoặc là public
    """
    data = supabase.table("projects").select("id, name, deadline, project_type").eq("project_type", "public").execute()
    public_df = pd.DataFrame(data.data)


    data = supabase.table("tasks").select("project").eq("assignee", username).execute()
    assigned_names = list({r["project"] for r in data.data})


    if assigned_names:
        data = supabase.table("projects").select("id, name, deadline, project_type").in_("name", assigned_names).execute()
        assigned_df = pd.DataFrame(data.data)
    else:
        assigned_df = pd.DataFrame(columns=["id", "name", "deadline", "project_type"])


    all_df = (
        pd.concat([public_df, assigned_df], ignore_index=True)
        .drop_duplicates(subset=["name"])
        .sort_values("name")
        .reset_index(drop=True)
    )
    return all_df


def user_app(user):
    """
    Giao diện cho user thường:
    - Xem & sửa công việc của mình (khối lượng, tiến độ)
    - Có thể tự thêm công việc trong các dự án Public
    """
    # dùng service role giống admin (read/write công public)
    # supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
    supabase = get_connection()

    try:
        username = user[1]
        supabase.table("users").update({"last_seen": datetime.utcnow().isoformat(timespec="seconds")}).eq("username", username).execute()

        st.subheader("🧑‍💻 Công việc của tôi")

        projects_df = _load_visible_projects(supabase, username)
        if projects_df.empty:
            st.info("⚠️ Bạn hiện chưa có dự án nào hoặc chưa được giao việc.")
            return

        # ======= Chọn dự án =======
        project = st.selectbox(
            "Chọn dự án", projects_df["name"].tolist(), key="user_proj_select"
        )
        prow = projects_df.loc[projects_df["name"] == project].iloc[0]
        proj_deadline = prow["deadline"]
        proj_type = (prow["project_type"] or "group").strip().lower()
        is_public = True   # ép chạy AG-Grid để test

        # ======= Danh sách task của user =======
        data = supabase.table("tasks").select(
            "id, task, khoi_luong, progress, deadline, note, approved, start_date"
        ).eq("project", project).eq("assignee", username).execute()

        df_tasks = pd.DataFrame(data.data)

        # === HIỂN THỊ NGÀY CÔNG TỪ start_date ===
        if "start_date" in df_tasks.columns:
            df_tasks["Ngày"] = (
                pd.to_datetime(df_tasks["start_date"], errors="coerce")
                .dt.strftime("%Y-%m-%d")
                .fillna("")
            )
        else:
            df_tasks["Ngày"] = ""

        # ✅ Fix: Nếu user chưa có task ⇒ không xử lý tiếp phần tách giờ
        if df_tasks.empty:
            st.warning("⚠️ Bạn chưa có công việc nào trong dự án này.")        
        else:
            # === Tách giờ bắt đầu và kết thúc từ note nếu có dạng ...

            def extract_times(note):
                match = re.search(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", str(note))
                if match:
                    return match.group(1), match.group(2)
                return "", ""

            df_tasks["Giờ bắt đầu"], df_tasks["Giờ kết thúc"] = zip(
                *df_tasks["note"].map(extract_times)
            )

            # ❗ GIỮ NGUYÊN DẠNG STRING HH:MM – KHÔNG CONVERT
            df_tasks["Giờ bắt đầu"] = df_tasks["Giờ bắt đầu"].fillna("").astype(str)
            df_tasks["Giờ kết thúc"] = df_tasks["Giờ kết thúc"].fillna("").astype(str)


            if df_tasks.empty:
                st.warning("⚠️ Bạn chưa có công việc nào trong dự án này.")
            else:
                rename_map = {
                    "task": "Công việc",
                    "khoi_luong": "Khối lượng (giờ)" if is_public else "Khối lượng",
                    "progress": "Tiến độ (%)",
                    "deadline": "Deadline",
                    "note": "Ghi chú",
                }
                df_show = pd.DataFrame({
                    "ID": df_tasks["id"],          # 👈 THÊM DÒNG NÀY
                    "Ngày": df_tasks["Ngày"],
                    "Công việc": df_tasks["task"],
                    "Giờ bắt đầu": df_tasks["Giờ bắt đầu"],
                    "Giờ kết thúc": df_tasks["Giờ kết thúc"],
                    "Khối lượng (giờ)": df_tasks["khoi_luong"],
                    "Ghi chú": df_tasks["note"],
                    # "Chọn?": False,
                })

                # giữ approved để xử lý logic (ẩn sau)
                if "approved" in df_tasks.columns:
                    df_show["approved"] = df_tasks["approved"].fillna(False)



                # Nếu public -> bỏ Tiến độ, Deadline
                if is_public:
                    drop_cols = [
                        c for c in ["Deadline", "Tiến độ (%)"] if c in df_show.columns
                    ]
                    df_show = df_show.drop(columns=drop_cols, errors="ignore")

                from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode, JsCode

                # tạo options giờ 15 phút (đặt ngay trước khi build grid)
                def build_time_options(start="07:00", end="21:00", step=15):
                    times = []
                    t = pd.to_datetime(start)
                    t_end = pd.to_datetime(end)
                    while t <= t_end:
                        times.append(t.strftime("%H:%M"))
                        t += pd.Timedelta(minutes=step)
                    return times

                time_options = build_time_options("07:00", "21:00", 15)

                # thêm cột approved để style/lock (ẩn đi cũng được)
                if "approved" not in df_show.columns and "approved" in df_tasks.columns:
                    df_show["approved"] = df_tasks["approved"].fillna(False)

                # style dòng đã duyệt
                row_style = JsCode("""
                function(params) {
                  if (params.data && params.data.approved === true) {
                    return {'backgroundColor': '#fff3cd'};
                  }
                }
                """)

                # khóa edit/tick khi approved (JS guard)
                editable_guard = JsCode("""
                function(params) {
                  return !(params.data && params.data.approved === true);
                }
                """)
                

                gb = GridOptionsBuilder.from_dataframe(df_show)
                gb.configure_column("ID", hide=True)
                # 🔹 CHỈNH ĐỘ RỘNG TỪNG CỘT
                gb.configure_column(
                    "Ngày",
                    width=150,
                    checkboxSelection=True,
                    headerCheckboxSelection=True
                )
                gb.configure_column("Ngày", editable=editable_guard)
                gb.configure_column("Công việc", flex=4)
                gb.configure_column("Giờ bắt đầu", width=110)
                gb.configure_column("Giờ kết thúc", width=110)
                gb.configure_column("Khối lượng (giờ)", width=120)
                gb.configure_column("Ghi chú", flex=5)
                # gb.configure_column("Chọn?", width=80)
                # gb.configure_column(
                    # "Chọn?",
                    # editable=editable_guard,
                    # cellRenderer="agCheckboxCellRenderer",
                    # cellEditor="agCheckboxCellEditor",
                    # width=80
                # )

                gb.configure_default_column(resizable=True, sortable=True, filter=True)
                

                # cột công việc không cho sửa
                gb.configure_column("Công việc", editable=editable_guard)

                # giờ chọn dropdown
                gb.configure_column("Giờ bắt đầu", editable=editable_guard,
                                    cellEditor="agSelectCellEditor",
                                    cellEditorParams={"values": time_options})
                gb.configure_column("Giờ kết thúc", editable=editable_guard,
                                    cellEditor="agSelectCellEditor",
                                    cellEditorParams={"values": time_options})

                # ghi chú/khối lượng: chỉ sửa khi chưa duyệt
                gb.configure_column("Ghi chú", editable=editable_guard)
                gb.configure_column("Khối lượng (giờ)", editable=editable_guard)

                # checkbox chọn xóa: không cho tick nếu đã duyệt
                # gb.configure_column("Chọn", editable=editable_guard)

                # ẩn cột approved khỏi UI (nhưng giữ trong data)
                gb.configure_column("approved", hide=True)

                grid_options = gb.build()
                grid_options["getRowStyle"] = row_style
                grid_options["rowSelection"] = "multiple"
                grid_options["suppressRowClickSelection"] = False

                with st.form(f"user_public_form_{project}_{username}", clear_on_submit=False):
                    grid = AgGrid(
                        df_show,
                        gridOptions=grid_options,
                        key=f"user_public_grid_{project}_{username}",
                        update_mode=GridUpdateMode.SELECTION_CHANGED,
                        data_return_mode=DataReturnMode.AS_INPUT,
                        allow_unsafe_jscode=True,
                        reload_data=False,
                        fit_columns_on_grid_load=False,
                        width="100%",
                        height=420,
                    )
                    edited = pd.DataFrame(grid["data"])
                    selected_rows = grid.get("selected_rows", [])

                    c1, c2 = st.columns([2, 1])
                    save_click = c1.form_submit_button("💾 Lưu thay đổi")
                    del_click  = c2.form_submit_button("🗑️ Xóa các dòng đã chọn")



                # ===== LƯU =====
                if save_click:
                    updated = 0
                    blocked = 0

                    for row in selected_rows:
                        # chặn đã duyệt
                        if bool(row.get("approved", False)):
                            blocked += 1
                            continue

                        task_id = int(row["ID"])
                        update_data = {}

                        # giờ + note (giữ logic mày đang làm)
                        start_time = row.get("Giờ bắt đầu", "")
                        end_time = row.get("Giờ kết thúc", "")
                        note_text = str(row.get("Ghi chú", "")).strip()

                        match_date = re.search(r"\(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}\)", note_text)
                        date_part = match_date.group(0) if match_date else ""

                        note_text = re.sub(r"^⏰\s*\d{2}:\d{2}(?::\d{2})?\s*-\s*\d{2}:\d{2}(?::\d{2})?", "", note_text)
                        note_text = re.sub(r"\(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}\)", "", note_text).strip()

                        # chuẩn hóa HH:MM
                        def _fmt_hhmm(x):
                            s = str(x).strip()
                            m = re.search(r"(\d{1,2}:\d{2})", s)
                            return m.group(1) if m else ""

                        start_str = _fmt_hhmm(start_time)
                        end_str   = _fmt_hhmm(end_time)

                        if start_str and end_str:
                            new_note = f"⏰ {start_str} - {end_str} {date_part} {note_text}".strip()
                        else:
                            new_note = note_text

                        update_data["note"] = new_note

                        # ✅ start_date: lấy từ start_date trong row nếu có, không thì fallback hôm nay
                        # (khuyến nghị: sau này thêm cột 'Ngày' riêng giống admin để chắc chắn)
                        start_date_str = str(row.get("Ngày", "")).strip()
                        if start_date_str:
                            update_data["start_date"] = start_date_str


                        # nếu có giờ thì tính lại khối lượng
                        try:
                            st_dt = datetime.strptime(start_str, "%H:%M")
                            en_dt = datetime.strptime(end_str, "%H:%M")
                            if en_dt > st_dt:
                                hours = (en_dt - st_dt).total_seconds() / 3600
                                update_data["khoi_luong"] = round(hours, 2)
                        except:
                            pass

                        if update_data:
                            supabase.table("tasks").update(update_data).eq("id", task_id).execute()
                            updated += 1

                    if blocked > 0:
                        st.warning(f"⚠️ Có {blocked} dòng đã duyệt nên không thể sửa.")
                    st.success(f"✅ Đã cập nhật {updated} dòng.")
                    st.rerun()

                # ===== XÓA =====
                if del_click:
                    ids_to_delete = []
                    blocked = 0

                    for row in selected_rows:
                        if bool(row.get("approved", False)):
                            blocked += 1
                            continue

                        ids_to_delete.append(int(row["ID"]))

                    if ids_to_delete:
                        supabase.table("tasks").delete().in_("id", ids_to_delete).execute()
                        st.success(f"✅ Đã xóa {len(ids_to_delete)} dòng.")
                    else:
                        st.warning("⚠️ Chưa chọn dòng nào để xóa.")

                    if blocked > 0:
                        st.warning(f"⚠️ {blocked} dòng đã duyệt nên không thể xóa.")

                    st.rerun()



        # ======= Tự thêm công việc (nếu public) =======
        if is_public:
            st.markdown("---")
            st.subheader("➕ Thêm công việc / công nhật cho bản thân (Public)")

            # Lấy danh mục công việc
            supabase.table("job_catalog").update({"project_type": "group"}).is_("project_type", None).execute()
            
            
            data = supabase.table("job_catalog").select("id, name, unit, parent_id").eq("project_type", proj_type).execute()
            jobs = pd.DataFrame(data.data)

            parent_jobs = jobs[jobs["parent_id"].isnull()].sort_values("name")
            col_a, col_b = st.columns([3, 3])
            with col_a:
                parent_choice = st.selectbox(
                    "Đầu mục công việc",
                    parent_jobs["name"].tolist(),
                    key="user_self_parent",
                )
            pid = None
            if not parent_jobs.empty:
                pid = int(
                    parent_jobs.loc[
                        parent_jobs["name"] == parent_choice, "id"
                    ].iloc[0]
                )
            childs = jobs[jobs["parent_id"] == pid].sort_values("name")
            with col_b:
                child_choice = st.selectbox(
                    "Công việc chi tiết", childs["name"].tolist(), key="user_self_child"
                )

            task_name = child_choice or parent_choice
            unit = (
                jobs.loc[jobs["name"] == task_name, "unit"].iloc[0]
                if task_name in jobs["name"].values
                else ""
            ) or ""

            # Nếu là công nhật
            if str(unit).strip().lower() == "công":
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    start_date = st.date_input(
                        "Ngày bắt đầu", key="user_self_start_date"
                    )
                with col2:
                    start_time = st.time_input(
                        "Giờ bắt đầu", pd.to_datetime("08:00").time(), key="user_self_start_time"
                    )
                with col3:
                    end_date = st.date_input(
                        "Ngày kết thúc", key="user_self_end_date", value=start_date
                    )
                with col4:
                    end_time = st.time_input(
                        "Giờ kết thúc", pd.to_datetime("17:00").time(), key="user_self_end_time"
                    )

                note = st.text_area("📝 Ghi chú (tuỳ chọn)", key="user_self_note")

                if st.button("➕ Thêm công nhật cho tôi", key="add_self_cong_btn"):
                    hours = calc_hours(start_date, end_date, start_time, end_time)
                    note_txt = f"⏰ {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')} ({start_date} - {end_date})"
                    if note:
                        note_txt += f" {note}"

                    
                    supabase.table("tasks").insert({
                        "project": project,
                        "task": task_name,
                        "assignee": username,
                        "khoi_luong": hours,
                        "note": note_txt,
                        "progress": 0,
                        "start_date": str(start_date)   # 👈 BẮT BUỘC
                    }).execute()

                    
                    st.success(
                        f"✅ Đã thêm {hours} giờ công cho công việc '{task_name}'"
                    )
                    st.rerun()
            else:
                qty = st.number_input(
                    "Khối lượng", min_value=0.0, step=0.1, key="user_self_qty"
                )
                if st.button("➕ Thêm công việc cho tôi", key="add_self_qty_btn"):
                    
                    supabase.table("tasks").insert({
                        "project": project,
                        "task": task_name,
                        "assignee": username,
                        "khoi_luong": float(qty or 0),
                        "note": "",
                        "progress": 0
                    }).execute()
                    
                    st.success("✅ Đã thêm công việc cho bạn")
                    st.rerun()
    finally:        
        pass