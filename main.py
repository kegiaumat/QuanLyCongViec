import streamlit as st
import pandas as pd
from auth import get_connection, init_db, DB_FILE

st.set_page_config(page_title="Quản Lý Công Việc", layout="wide")

def load_tasks():
    conn, cursor = get_connection()
    df = pd.read_sql_query("SELECT * FROM tasks", conn)
    conn.close()
    return df

def add_task(name, description, status, start_time, end_time, hours):
    conn, cursor = get_connection()
    cursor.execute("INSERT INTO tasks (name, description, status, start_time, end_time, hours) VALUES (?, ?, ?, ?, ?, ?)",
                   (name, description, status, start_time, end_time, hours))
    conn.commit()
    conn.close()

def main():
    st.title("📋 Ứng dụng Quản Lý Công Việc")

    init_db()

    menu = ["Xem công việc", "Thêm công việc"]
    choice = st.sidebar.selectbox("Menu", menu)

    if choice == "Xem công việc":
        st.subheader("Danh sách công việc")
        df = load_tasks()
        st.dataframe(df)

    elif choice == "Thêm công việc":
        st.subheader("Thêm công việc mới")
        with st.form(key="task_form"):
            name = st.text_input("Tên công việc")
            description = st.text_area("Mô tả")
            status = st.selectbox("Trạng thái", ["Chưa bắt đầu", "Đang làm", "Hoàn thành"])
            start_time = st.date_input("Ngày bắt đầu")
            end_time = st.date_input("Ngày kết thúc")
            hours = st.number_input("Số giờ dự kiến", min_value=0.0, step=0.5)
            submit = st.form_submit_button("Thêm")

        if submit:
            add_task(name, description, status, str(start_time), str(end_time), hours)
            st.success("✅ Đã thêm công việc mới!")

if __name__ == "__main__":
    main()
