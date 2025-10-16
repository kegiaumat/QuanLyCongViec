# user_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from auth import get_connection, calc_hours
from auth import show_indirect_task_form, show_indirect_task_table
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
    # st.set_page_config(layout="wide")  # Chỉ nên gọi 1 lần trong app.py
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
        is_public = proj_type == "public"

        # ======= Danh sách task của user =======
        data = supabase.table("tasks").select("id, task, khoi_luong, progress, deadline, note").eq("project", project).eq("assignee", username).execute()
        df_tasks = pd.DataFrame(data.data)
        

        from auth import show_indirect_task_form, show_indirect_task_table

        # 👇 Hiển thị công việc gián tiếp (user)
        show_indirect_task_table("user", supabase, username, df_tasks)

        # 👇 Form thêm công việc gián tiếp
        show_indirect_task_form("user", supabase, username)



            with col2:
                if st.button("🗑️ Xóa các dòng đã chọn", key="delete_my_tasks_btn"):
                    ids_to_delete = [
                        int(df_tasks.iloc[i]["id"])
                        for i, row in edited.iterrows()
                        if row.get("Chọn")
                    ]
                    if ids_to_delete:
                        for tid in ids_to_delete:
                            supabase.table("tasks").delete().eq("id", tid).execute()
                        
                        st.success(f"✅ Đã xóa {len(ids_to_delete)} dòng")
                        st.rerun()
                    else:
                        st.warning("⚠️ Chưa chọn dòng nào để xóa")

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
                        "progress": 0
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