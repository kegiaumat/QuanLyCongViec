# user_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from auth import get_connection
from auth import commit_and_sync
from auth import calc_hours

def _load_visible_projects(conn, username: str) -> pd.DataFrame:
    """
    Lấy danh sách dự án user đang có nhiệm vụ hoặc là public
    """
    public_df = pd.read_sql(
        "SELECT id, name, deadline, project_type FROM projects WHERE project_type='public'", conn
    )
    assigned_names = pd.read_sql(
        "SELECT DISTINCT project FROM tasks WHERE assignee=?", conn, params=(username,)
    )["project"].tolist()
    assigned_df = (
        pd.read_sql(
            f"SELECT id, name, deadline, project_type FROM projects "
            f"WHERE name IN ({','.join(['?']*len(assigned_names))})",
            conn, params=assigned_names
        )
        if assigned_names else pd.DataFrame(columns=["id", "name", "deadline", "project_type"])
    )
    all_df = pd.concat([public_df, assigned_df], ignore_index=True).drop_duplicates(
        subset=["name"]
    )
    return all_df.sort_values("name").reset_index(drop=True)


def user_app(user):
    """
    Giao diện cho user thường:
    - Xem & sửa công việc của mình (khối lượng, tiến độ)
    - Có thể tự thêm công việc trong các dự án Public
    """
    st.set_page_config(layout="wide")
    conn, c = get_connection()
    username = user[1]

    st.subheader("🧑‍💻 Công việc của tôi")

    projects_df = _load_visible_projects(conn, username)
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
    is_public = proj_type == "public"

    # ======= Danh sách task của user =======
    df_tasks = pd.read_sql(
        "SELECT id, task, khoi_luong, progress, deadline, note FROM tasks WHERE project=? AND assignee=?",
        conn, params=(project, username)
    )

    if df_tasks.empty:
        st.warning("⚠️ Bạn chưa có công việc nào trong dự án này.")
    else:
        # ---- Đổi tên cột tuỳ theo public hay không ----
        rename_map = {
            "task": "Công việc",
            "khoi_luong": "Khối lượng (giờ)" if is_public else "Khối lượng",
            "progress": "Tiến độ (%)",
            "deadline": "Deadline",
            "note": "Ghi chú"
        }
        df_show = df_tasks.rename(columns=rename_map).drop(columns=["id"])

        # Thêm cột chọn để xóa
        df_show["Chọn"] = False

        # Nếu dự án Public -> bỏ Tiến độ, Deadline
        if is_public:
            drop_cols = [c for c in ["Deadline", "Tiến độ (%)"] if c in df_show.columns]
            df_show = df_show.drop(columns=drop_cols, errors="ignore")

        edited = st.data_editor(
            df_show,
            key="user_tasks_editor",
            width="stretch",
            hide_index=True,
            column_config={
                "Công việc": st.column_config.TextColumn(disabled=True),
                "Ghi chú": st.column_config.TextColumn(disabled=True),
                "Chọn": st.column_config.CheckboxColumn("Xóa?", help="Tick để xóa dòng này")
            }
        )

        col1, col2 = st.columns([2,1])
        with col1:
            if st.button("💾 Lưu thay đổi", key="save_my_task_btn"):
                for i, row in edited.iterrows():
                    tid = int(df_tasks.iloc[i]["id"])
                    new_qty = float(
                        row.get("Khối lượng (giờ)" if is_public else "Khối lượng") or 0
                    )
                    if is_public:
                        c.execute("UPDATE tasks SET khoi_luong=? WHERE id=?", (new_qty, tid))
                    else:
                        new_prog = int(row.get("Tiến độ (%)") or 0)
                        c.execute(
                            "UPDATE tasks SET khoi_luong=?, progress=? WHERE id=?",
                            (new_qty, new_prog, tid)
                        )
                commit_and_sync(conn)
                st.success("✅ Đã cập nhật công việc")
                st.rerun()
        with col2:
            if st.button("🗑️ Xóa các dòng đã chọn", key="delete_my_tasks_btn"):
                ids_to_delete = []
                for i, row in edited.iterrows():
                    if row.get("Chọn"):
                        ids_to_delete.append(int(df_tasks.iloc[i]["id"]))
                if ids_to_delete:
                    for tid in ids_to_delete:
                        c.execute("DELETE FROM tasks WHERE id=?", (tid,))
                    commit_and_sync(conn)
                    st.success(f"✅ Đã xóa {len(ids_to_delete)} dòng")
                    st.rerun()
                else:
                    st.warning("⚠️ Chưa chọn dòng nào để xóa")


    # ======= Tự thêm công việc (nếu dự án public) =======
    if is_public:
        st.markdown("---")
        st.subheader("➕ Thêm công việc / công nhật cho bản thân (Public)")

        # Lấy job_catalog
        c.execute("UPDATE job_catalog SET project_type='group' WHERE project_type IS NULL")
        commit_and_sync(conn)
        jobs = pd.read_sql(
            "SELECT id, name, unit, parent_id FROM job_catalog WHERE project_type = ?",
            conn, params=(proj_type,)
        )

        parent_jobs = jobs[jobs["parent_id"].isnull()].sort_values("name")
        col_a, col_b = st.columns([3,3])
        with col_a:
            parent_choice = st.selectbox("Đầu mục công việc", parent_jobs["name"].tolist(), key="user_self_parent")
        pid = None
        if not parent_jobs.empty:
            pid = int(parent_jobs.loc[parent_jobs["name"] == parent_choice, "id"].iloc[0])
        childs = jobs[jobs["parent_id"] == pid].sort_values("name")
        with col_b:
            child_choice = st.selectbox("Công việc chi tiết", childs["name"].tolist(), key="user_self_child")

        task_name = child_choice or parent_choice
        unit = ""
        if task_name in jobs["name"].values:
            unit = jobs.loc[jobs["name"] == task_name, "unit"].iloc[0] or ""

        # Nếu công nhật
        if str(unit).strip().lower() == "công":
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                start_date = st.date_input("Ngày bắt đầu", key="user_self_start_date")
            with col2:
                start_time = st.time_input("Giờ bắt đầu", pd.to_datetime("08:00").time(), key="user_self_start_time")
            with col3:
                end_date = st.date_input("Ngày kết thúc", key="user_self_end_date", value=start_date)
            with col4:
                end_time = st.time_input("Giờ kết thúc", pd.to_datetime("17:00").time(), key="user_self_end_time")

            note = st.text_area("📝 Ghi chú (tuỳ chọn)", key="user_self_note")

            if st.button("➕ Thêm công nhật cho tôi", key="add_self_cong_btn"):
                from auth import calc_hours
                hours = calc_hours(start_date, end_date, start_time, end_time)
                note_txt = f"⏰ {start_time} - {end_time} ({start_date}→{end_date})"
                if note:
                    note_txt += f"\n{note}"
                c.execute(
                    "INSERT INTO tasks (project, task, assignee, khoi_luong, note, progress) VALUES (?, ?, ?, ?, ?, ?)",
                    (project, task_name, username, hours, note_txt, 0)
                )
                commit_and_sync(conn)
                st.success(f"✅ Đã thêm {hours} giờ công cho công việc '{task_name}'")
                st.rerun()
        else:
            qty = st.number_input("Khối lượng", min_value=0.0, step=0.1, key="user_self_qty")
            if st.button("➕ Thêm công việc cho tôi", key="add_self_qty_btn"):
                c.execute(
                    "INSERT INTO tasks (project, task, assignee, khoi_luong, note, progress) VALUES (?, ?, ?, ?, ?, ?)",
                    (project, task_name, username, float(qty or 0), "", 0)
                )
                commit_and_sync(conn)
                st.success("✅ Đã thêm công việc cho bạn")
                st.rerun()
