# user_app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from auth import get_connection, calc_hours
import re
from auth import show_public_task_form
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
        

        # === Tách giờ bắt đầu và kết thúc từ note nếu có dạng "⏰ 08:00 - 17:00 (...)" ===
        def extract_times(note):
            match = re.search(r"(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})", str(note))
            if match:
                return match.group(1), match.group(2)
            return "", ""

        df_tasks["Giờ bắt đầu"], df_tasks["Giờ kết thúc"] = zip(*df_tasks["note"].map(extract_times))
        # Chuyển "HH:MM" -> datetime.time để dùng được với TimeColumn
        def _to_time(x):
            if x is None or str(x).strip() == "":
                return None
            try:
                # đúng định dạng HH:MM
                return pd.to_datetime(str(x), format="%H:%M").time()
            except Exception:
                try:
                    # fallback nếu về sau dữ liệu có giây HH:MM:SS
                    return pd.to_datetime(str(x)).time()
                except Exception:
                    return None

        df_tasks["Giờ bắt đầu"] = df_tasks["Giờ bắt đầu"].map(_to_time)
        df_tasks["Giờ kết thúc"] = df_tasks["Giờ kết thúc"].map(_to_time)

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
            df_show = df_tasks.rename(columns=rename_map).drop(columns=["id"])
            df_show["Chọn"] = False
            # Thêm 2 cột giờ bắt đầu/kết thúc nếu chưa có
            if "Giờ bắt đầu" in df_tasks.columns and "Giờ bắt đầu" not in df_show.columns:
                df_show.insert(1, "Giờ bắt đầu", df_tasks["Giờ bắt đầu"])

            if "Giờ kết thúc" in df_tasks.columns and "Giờ kết thúc" not in df_show.columns:
                df_show.insert(2, "Giờ kết thúc", df_tasks["Giờ kết thúc"])


            # Nếu public -> bỏ Tiến độ, Deadline
            if is_public:
                drop_cols = [
                    c for c in ["Deadline", "Tiến độ (%)"] if c in df_show.columns
                ]
                df_show = df_show.drop(columns=drop_cols, errors="ignore")

            edited = st.data_editor(
                df_show,
                key="user_tasks_editor",
                width="stretch",
                hide_index=True,
                column_config={
                    "Công việc": st.column_config.TextColumn(disabled=True),
                    "Giờ bắt đầu": st.column_config.TimeColumn("Giờ bắt đầu", format="HH:mm"),
                    "Giờ kết thúc": st.column_config.TimeColumn("Giờ kết thúc", format="HH:mm"),
                    "Ghi chú": st.column_config.TextColumn(),
                    "Chọn": st.column_config.CheckboxColumn("Xóa?", help="Tick để xóa dòng này"),
                },
            )


            col1, col2 = st.columns([2, 1])
            with col1:
                if st.button("💾 Lưu thay đổi"):
                    from datetime import time, date

                    def _fmt_time(t):  # -> "HH:MM"
                        if isinstance(t, time):
                            return t.strftime("%H:%M")
                        s = str(t).strip()
                        for fmt in ("%H:%M", "%H:%M:%S"):
                            try:
                                return datetime.strptime(s, fmt).strftime("%H:%M")
                            except Exception:
                                pass
                        return ""

                    def _parse_time(t):  # -> datetime (today + time) hoặc None
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
                        task_id = int(df_tasks.iloc[i]["id"])
                        update_data = {}

                        # 🕒 Lấy giờ và ghi chú
                        start_time = row.get("Giờ bắt đầu", "")
                        end_time = row.get("Giờ kết thúc", "")
                        note_text = str(row.get("Ghi chú", "")).strip()

                        # 🧹 Giữ lại phần ngày nếu có
                        match_date = re.search(r"\(\d{4}-\d{2}-\d{2}\s*-\s*\d{4}-\d{2}-\d{2}\)", note_text)
                        date_part = match_date.group(0) if match_date else ""

                        # 🧹 Xóa phần giờ cũ + ngày cũ để tránh lặp
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
                        st_dt = _parse_time(start_time)
                        en_dt = _parse_time(end_time)
                        if st_dt and en_dt:
                            if en_dt < st_dt:
                                en_dt = en_dt.replace(day=st_dt.day + 1)
                            hours = (en_dt - st_dt).total_seconds() / 3600
                            if hours > 0:
                                update_data["khoi_luong"] = round(hours, 2)
                                df_show.at[i, "Khối lượng (giờ)"] = round(hours, 2)

                        # 📊 Tiến độ
                        if "Tiến độ (%)" in row and not pd.isna(row["Tiến độ (%)"]):
                            update_data["progress"] = float(row["Tiến độ (%)"])

                        # 💾 Ghi xuống database
                        if update_data:
                            supabase.table("tasks").update(update_data).eq("id", task_id).execute()

                    st.success("✅ Đã cập nhật giờ, ghi chú và khối lượng!")
                    st.rerun()



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
        show_public_task_form("user", supabase, username)
    finally:        
        pass