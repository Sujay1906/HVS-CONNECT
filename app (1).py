"""
app.py — HVS Connect
Entry point. Run with: streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime

import database as db
import auth

st.set_page_config(page_title="HVS Connect", page_icon="🏫", layout="wide")

db.init_db()
db.seed_demo_data()

# ----------------------------------------------------------------------
# Global style
# ----------------------------------------------------------------------
st.markdown("""
<style>
:root { --hvs-navy: #0b2545; --hvs-blue: #1b4b91; --hvs-light: #eaf1fb; }
.hvs-header { background: var(--hvs-navy); padding: 18px 24px; border-radius: 10px;
  color: white; margin-bottom: 18px; }
.hvs-header h1 { margin: 0; font-size: 1.5rem; }
.hvs-header p { margin: 0; opacity: 0.8; font-size: 0.85rem; }
.badge { display:inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.75rem; font-weight:600;}
.badge-pending { background:#fff3cd; color:#856404; }
.badge-approved { background:#d4edda; color:#155724; }
.badge-rejected { background:#f8d7da; color:#721c24; }
.badge-paid { background:#d4edda; color:#155724; }
.stMetric { background: var(--hvs-light); padding: 10px; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)


def badge(status):
    cls = {"PENDING": "badge-pending", "APPROVED": "badge-approved", "PAID": "badge-paid",
           "REJECTED": "badge-rejected", "RECOMMENDED": "badge-pending"}.get(status, "badge-pending")
    return f'<span class="badge {cls}">{status}</span>'


# ----------------------------------------------------------------------
# Login screen
# ----------------------------------------------------------------------
def login_screen():
    st.markdown("""
    <div class="hvs-header">
        <h1>🏫 HVS Connect</h1>
        <p>Dr. KKR's Happy Valley School — centralized digital platform</p>
    </div>
    """, unsafe_allow_html=True)

    if db.get_setting("system_paused") == "1":
        st.error("HVS Connect is temporarily unavailable. Please contact administration.")
        with st.expander("Dean administrative access"):
            dean_only_login()
        return

    tab1, tab2 = st.tabs(["👨‍👩‍👧 Parent Login", "🧑‍🏫 Faculty / Staff Login"])
    with tab1:
        login_form("parent")
    with tab2:
        login_form("staff")

    st.divider()
    st.caption("Staff without an account: use the QR code / registration link provided by administration.")
    with st.expander("New staff — request an account"):
        registration_form()


def dean_only_login():
    login_form("dean_override")


def login_form(key_prefix):
    stage = st.session_state.get(f"{key_prefix}_stage", "credentials")

    if stage == "credentials":
        with st.form(f"{key_prefix}_form"):
            hvs_id = st.text_input("HVS ID", placeholder="e.g. HVS-P001")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Continue")
        if submitted:
            user, error = auth.verify_password(hvs_id.strip(), password)
            if error:
                st.error(error)
            else:
                auth.start_otp_flow(user)
                st.session_state[f"{key_prefix}_stage"] = "otp"
                st.session_state[f"{key_prefix}_hvs_id"] = user["hvs_id"]
                st.rerun()

    elif stage == "otp":
        st.info(f"An OTP has been sent to the mobile number registered for "
                f"{st.session_state[f'{key_prefix}_hvs_id']}.")
        if st.session_state.get("otp_dev_display"):
            st.warning(f"🔧 DEV MODE (no SMS provider configured) — your OTP is: "
                       f"**{st.session_state['otp_dev_display']}**")
        with st.form(f"{key_prefix}_otp_form"):
            otp_input = st.text_input("Enter 6-digit OTP", max_chars=6)
            c1, c2 = st.columns(2)
            verify_clicked = c1.form_submit_button("Verify & Login")
            resend_clicked = c2.form_submit_button("Resend OTP")
        if resend_clicked:
            conn = db.get_conn()
            row = conn.execute("SELECT * FROM users WHERE hvs_id=?",
                                (st.session_state[f"{key_prefix}_hvs_id"],)).fetchone()
            conn.close()
            auth.start_otp_flow(row)
            st.success("A new OTP has been generated.")
            st.rerun()
        if verify_clicked:
            ok, error = auth.verify_otp(otp_input)
            if ok:
                auth.complete_login(st.session_state[f"{key_prefix}_hvs_id"])
                st.session_state[f"{key_prefix}_stage"] = "credentials"
                st.rerun()
            else:
                st.error(error)
        if st.button("Back", key=f"{key_prefix}_back"):
            st.session_state[f"{key_prefix}_stage"] = "credentials"
            st.rerun()


def registration_form():
    with st.form("registration_form"):
        name = st.text_input("Full Name")
        mobile = st.text_input("Mobile Number")
        role = st.selectbox("Role Applying For", ["FACULTY", "ACCOUNTS", "WARDEN", "MESS", "DTP"])
        submitted = st.form_submit_button("Submit Request")
    if submitted:
        if not name or not mobile:
            st.error("Please fill all fields.")
        else:
            req_id = db.new_id("HVS-REG")
            conn = db.get_conn()
            conn.execute(
                "INSERT INTO registration_requests (request_id, full_name, mobile, requested_role, "
                "status, created_at) VALUES (?,?,?,?, 'PENDING', ?)",
                (req_id, name, mobile, role, db.now()),
            )
            conn.commit()
            conn.close()
            db.log_audit(name, "ACCOUNT_REQUEST", f"Requested role {role}")
            st.success(f"Request submitted ({req_id}). The Dean will review your request.")


# ----------------------------------------------------------------------
# Shared shell
# ----------------------------------------------------------------------
def app_shell():
    user = auth.current_user()
    st.markdown(f"""
    <div class="hvs-header">
        <h1>🏫 HVS Connect</h1>
        <p>{user['full_name']} · {user['hvs_id']} · {user['role']}</p>
    </div>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(f"**{user['full_name']}**")
        st.caption(f"{user['hvs_id']} — {user['role']}")
        if st.button("Log out"):
            auth.logout()
            st.rerun()

    if db.get_setting("system_paused") == "1" and user["role"] != "DEAN":
        st.error("HVS Connect is temporarily unavailable. Please contact administration.")
        return

    role = user["role"]
    if role == "DEAN":
        dean_dashboard(user)
    elif role == "PARENT":
        parent_dashboard(user)
    elif role == "FACULTY":
        faculty_dashboard(user)
    elif role == "ACCOUNTS":
        accounts_dashboard(user)
    elif role == "WARDEN":
        warden_dashboard(user)
    elif role == "MESS":
        mess_dashboard(user)
    elif role == "DTP":
        dtp_dashboard(user)


# ----------------------------------------------------------------------
# DEAN
# ----------------------------------------------------------------------
def dean_dashboard(user):
    tabs = st.tabs(["Overview", "Leave Requests", "Fee Extensions", "Attendance", "Examinations",
                    "Users & Approvals", "Notices", "System Control", "Audit Logs"])
    conn = db.get_conn()

    with tabs[0]:
        c1, c2, c3, c4 = st.columns(4)
        total_students = conn.execute("SELECT COUNT(*) n FROM students").fetchone()["n"]
        pending_leave = conn.execute("SELECT COUNT(*) n FROM leave_requests WHERE status='PENDING'").fetchone()["n"]
        pending_fee = conn.execute("SELECT COUNT(*) n FROM fee_extension_requests WHERE dean_decision='PENDING'").fetchone()["n"]
        pending_users = conn.execute("SELECT COUNT(*) n FROM registration_requests WHERE status='PENDING'").fetchone()["n"]
        c1.metric("Total Students", total_students)
        c2.metric("Pending Leave Requests", pending_leave)
        c3.metric("Pending Fee Extensions", pending_fee)
        c4.metric("Pending Account Approvals", pending_users)

        st.subheader("Recent Notices")
        notices = conn.execute("SELECT * FROM notices ORDER BY id DESC LIMIT 5").fetchall()
        for n in notices:
            st.info(f"**{n['title']}** — {n['message']}  \n*{n['created_at']} by {n['posted_by']}*")

        st.subheader("Recent Activity")
        logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 8").fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in logs]), use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Leave Requests")
        rows = conn.execute("""
            SELECT lr.*, s.name as student_name FROM leave_requests lr
            JOIN students s ON s.student_id = lr.student_id
            ORDER BY lr.created_at DESC
        """).fetchall()
        for r in rows:
            with st.container(border=True):
                col1, col2 = st.columns([4, 1])
                col1.markdown(f"**{r['leave_id']}** — {r['student_name']} · {r['leave_type']}  \n"
                              f"{r['from_date']} to {r['to_date']}  \n*{r['reason']}*")
                col1.markdown(badge(r['status']), unsafe_allow_html=True)
                if r["status"] == "PENDING":
                    a1, a2 = col2.columns(2)
                    if a1.button("Approve", key=f"appr_{r['leave_id']}"):
                        conn.execute("UPDATE leave_requests SET status='APPROVED', decided_by=?, decided_at=? "
                                     "WHERE leave_id=?", (user["hvs_id"], db.now(), r["leave_id"]))
                        conn.commit()
                        db.add_notification(r["parent_hvs_id"], f"Leave request {r['leave_id']} approved.")
                        db.log_audit(user["hvs_id"], "LEAVE_APPROVED", r["leave_id"])
                        st.rerun()
                    if a2.button("Reject", key=f"rej_{r['leave_id']}"):
                        conn.execute("UPDATE leave_requests SET status='REJECTED', decided_by=?, decided_at=? "
                                     "WHERE leave_id=?", (user["hvs_id"], db.now(), r["leave_id"]))
                        conn.commit()
                        db.add_notification(r["parent_hvs_id"], f"Leave request {r['leave_id']} rejected.")
                        db.log_audit(user["hvs_id"], "LEAVE_REJECTED", r["leave_id"])
                        st.rerun()

    with tabs[2]:
        st.subheader("Fee Extension Requests (final Dean approval)")
        rows = conn.execute("""
            SELECT fx.*, s.name as student_name FROM fee_extension_requests fx
            JOIN students s ON s.student_id = fx.student_id
            ORDER BY fx.created_at DESC
        """).fetchall()
        for r in rows:
            with st.container(border=True):
                st.markdown(f"**{r['request_id']}** — {r['student_name']}  \n"
                            f"Requested date: {r['requested_date']}  \n*{r['reason']}*")
                st.markdown(f"Accounts review: {badge(r['accounts_decision'])} &nbsp; "
                           f"Dean decision: {badge(r['dean_decision'])}", unsafe_allow_html=True)
                if r["dean_decision"] == "PENDING":
                    a1, a2 = st.columns(2)
                    if a1.button("Approve", key=f"fxappr_{r['request_id']}"):
                        conn.execute("UPDATE fee_extension_requests SET dean_decision='APPROVED' WHERE request_id=?",
                                     (r["request_id"],))
                        conn.commit()
                        db.add_notification(r["parent_hvs_id"], f"Fee extension {r['request_id']} approved.")
                        db.log_audit(user["hvs_id"], "FEE_EXT_APPROVED", r["request_id"])
                        st.rerun()
                    if a2.button("Reject", key=f"fxrej_{r['request_id']}"):
                        conn.execute("UPDATE fee_extension_requests SET dean_decision='REJECTED' WHERE request_id=?",
                                     (r["request_id"],))
                        conn.commit()
                        db.add_notification(r["parent_hvs_id"], f"Fee extension {r['request_id']} rejected.")
                        db.log_audit(user["hvs_id"], "FEE_EXT_REJECTED", r["request_id"])
                        st.rerun()

    with tabs[3]:
        st.subheader("School-wide Attendance")
        att = conn.execute("""
            SELECT s.name, s.class_name, a.date, a.status FROM attendance a
            JOIN students s ON s.student_id = a.student_id
            ORDER BY a.date DESC LIMIT 100
        """).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in att]), use_container_width=True, hide_index=True)

    with tabs[4]:
        st.subheader("Examinations")
        exams = conn.execute("SELECT * FROM examinations").fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in exams]), use_container_width=True, hide_index=True)

    with tabs[5]:
        st.subheader("Pending Account Requests")
        reqs = conn.execute("SELECT * FROM registration_requests WHERE status='PENDING'").fetchall()
        for r in reqs:
            with st.container(border=True):
                st.markdown(f"**{r['full_name']}** · {r['mobile']} · applying as **{r['requested_role']}**")
                a1, a2 = st.columns(2)
                if a1.button("Approve & Create Account", key=f"uappr_{r['request_id']}"):
                    prefix = {"FACULTY": "F", "ACCOUNTS": "A", "WARDEN": "W", "MESS": "M", "DTP": "DTP"}[r["requested_role"]]
                    new_hvs_id = f"HVS-{prefix}{conn.execute('SELECT COUNT(*) n FROM users').fetchone()['n']+1:03d}"
                    default_pw = db.hash_password("Welcome@123")
                    conn.execute("INSERT INTO users (hvs_id, password_hash, role, full_name, mobile, status, "
                                 "created_at) VALUES (?,?,?,?,?, 'ACTIVE', ?)",
                                 (new_hvs_id, default_pw, r["requested_role"], r["full_name"], r["mobile"], db.now()))
                    conn.execute("UPDATE registration_requests SET status='APPROVED' WHERE request_id=?",
                                 (r["request_id"],))
                    conn.commit()
                    db.log_audit(user["hvs_id"], "ACCOUNT_APPROVED", f"{new_hvs_id} ({r['full_name']})")
                    st.success(f"Account created: {new_hvs_id} / default password Welcome@123")
                    st.rerun()
                if a2.button("Reject", key=f"urej_{r['request_id']}"):
                    conn.execute("UPDATE registration_requests SET status='REJECTED' WHERE request_id=?",
                                 (r["request_id"],))
                    conn.commit()
                    db.log_audit(user["hvs_id"], "ACCOUNT_REJECTED", r["full_name"])
                    st.rerun()

        st.divider()
        st.subheader("All Users")
        users = conn.execute("SELECT hvs_id, full_name, role, status FROM users").fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in users]), use_container_width=True, hide_index=True)
        with st.form("disable_enable"):
            target = st.text_input("HVS ID to enable/disable")
            action = st.radio("Action", ["DISABLE", "ENABLE"], horizontal=True)
            go = st.form_submit_button("Apply")
        if go and target:
            new_status = "DISABLED" if action == "DISABLE" else "ACTIVE"
            conn.execute("UPDATE users SET status=? WHERE hvs_id=?", (new_status, target))
            conn.commit()
            db.log_audit(user["hvs_id"], f"ACCOUNT_{action}D", target)
            st.success(f"{target} set to {new_status}.")
            st.rerun()

    with tabs[6]:
        st.subheader("Post a Notice")
        with st.form("post_notice"):
            title = st.text_input("Title")
            message = st.text_area("Message")
            audience = st.selectbox("Audience", ["ALL", "PARENT", "FACULTY", "STAFF"])
            post = st.form_submit_button("Post Notice")
        if post and title and message:
            conn.execute("INSERT INTO notices (title, message, posted_by, audience, created_at) VALUES (?,?,?,?,?)",
                         (title, message, user["hvs_id"], audience, db.now()))
            conn.commit()
            db.log_audit(user["hvs_id"], "NOTICE_POSTED", title)
            st.success("Notice posted.")
            st.rerun()

    with tabs[7]:
        st.subheader("System Control")
        paused = db.get_setting("system_paused") == "1"
        st.write(f"Current status: {'🔴 PAUSED' if paused else '🟢 RUNNING'}")
        c1, c2 = st.columns(2)
        if c1.button("Pause HVS Connect", disabled=paused):
            db.set_setting("system_paused", "1")
            db.log_audit(user["hvs_id"], "SYSTEM_PAUSED", "")
            st.rerun()
        if c2.button("Resume HVS Connect", disabled=not paused):
            db.set_setting("system_paused", "0")
            db.log_audit(user["hvs_id"], "SYSTEM_RESUMED", "")
            st.rerun()

        st.divider()
        st.subheader("Fee & Attendance Policy")
        lock = db.get_setting("attendance_fee_lock") == "1"
        new_lock = st.toggle("Restrict attendance visibility when fees are pending", value=lock)
        if new_lock != lock:
            db.set_setting("attendance_fee_lock", "1" if new_lock else "0")
            db.log_audit(user["hvs_id"], "POLICY_CHANGED", f"attendance_fee_lock={new_lock}")
            st.rerun()

    with tabs[8]:
        st.subheader("Audit Log")
        logs = conn.execute("SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200").fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in logs]), use_container_width=True, hide_index=True)

    conn.close()


# ----------------------------------------------------------------------
# PARENT
# ----------------------------------------------------------------------
def parent_dashboard(user):
    conn = db.get_conn()
    children = conn.execute("SELECT * FROM students WHERE parent_hvs_id=?", (user["hvs_id"],)).fetchall()
    if not children:
        st.warning("No student records are linked to your account yet.")
        conn.close()
        return

    names = {c["student_id"]: f"{c['name']} ({c['class_name']})" for c in children}
    selected_id = st.selectbox("Select Child", list(names.keys()), format_func=lambda x: names[x])
    child = next(c for c in children if c["student_id"] == selected_id)

    tabs = st.tabs(["Profile", "Attendance", "Results", "Leave", "Fees", "Notices"])

    with tabs[0]:
        st.subheader(child["name"])
        st.write(f"Class: {child['class_name']} — Section {child['section']}")
        st.write(f"Hostel Student: {'Yes' if child['is_hostel'] else 'No'}")

    with tabs[1]:
        fee = conn.execute("SELECT * FROM fee_records WHERE student_id=?", (selected_id,)).fetchone()
        locked = db.get_setting("attendance_fee_lock") == "1" and fee and fee["status"] == "PENDING"
        if locked:
            st.error("Attendance is currently restricted due to pending fees. Please clear fees or request an "
                      "extension in the Fees tab.")
        else:
            att = conn.execute("SELECT date, subject, status FROM attendance WHERE student_id=? "
                               "ORDER BY date DESC", (selected_id,)).fetchall()
            df = pd.DataFrame([dict(r) for r in att])
            if not df.empty:
                present = (df["status"] == "PRESENT").sum()
                pct = round(100 * present / len(df), 1)
                c1, c2, c3 = st.columns(3)
                c1.metric("Attendance %", f"{pct}%")
                c2.metric("Present Days", int(present))
                c3.metric("Absent Days", len(df) - int(present))
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[2]:
        marks = conn.execute("""
            SELECT e.exam_name, m.subject, m.marks_obtained, m.max_marks
            FROM marks m JOIN examinations e ON e.exam_id = m.exam_id
            WHERE m.student_id=? AND e.published=1
        """, (selected_id,)).fetchall()
        if marks:
            df = pd.DataFrame([dict(r) for r in marks])
            st.dataframe(df, use_container_width=True, hide_index=True)
            total_pct = round(100 * df["marks_obtained"].sum() / df["max_marks"].sum(), 1)
            st.metric("Overall Percentage (published exams)", f"{total_pct}%")
        else:
            st.info("No published results yet.")

    with tabs[3]:
        st.subheader("My Leave Requests")
        leaves = conn.execute("SELECT * FROM leave_requests WHERE student_id=? ORDER BY created_at DESC",
                              (selected_id,)).fetchall()
        for l in leaves:
            st.markdown(f"**{l['leave_id']}** — {l['leave_type']} · {l['from_date']} to {l['to_date']} "
                       f"{badge(l['status'])}", unsafe_allow_html=True)

        st.divider()
        st.subheader("New Leave Request")
        with st.form("new_leave"):
            leave_type = st.selectbox("Leave Type", ["Medical", "Personal", "Family Function", "Other"])
            c1, c2 = st.columns(2)
            from_date = c1.date_input("From Date")
            to_date = c2.date_input("To Date")
            reason = st.text_area("Reason")
            doc = st.file_uploader("Supporting document (optional)")
            submit = st.form_submit_button("Submit Leave Request")
        if submit:
            leave_id = db.new_id("HVS-LV")
            conn.execute("INSERT INTO leave_requests (leave_id, student_id, parent_hvs_id, leave_type, "
                        "from_date, to_date, reason, status, created_at) VALUES (?,?,?,?,?,?,?, 'PENDING', ?)",
                        (leave_id, selected_id, user["hvs_id"], leave_type, str(from_date), str(to_date),
                         reason, db.now()))
            conn.commit()
            db.log_audit(user["hvs_id"], "LEAVE_SUBMITTED", leave_id)
            st.success(f"Leave request submitted: {leave_id}")
            st.rerun()

    with tabs[4]:
        fee = conn.execute("SELECT * FROM fee_records WHERE student_id=?", (selected_id,)).fetchone()
        if fee:
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Fees", f"₹{fee['total_fees']:,.0f}")
            c2.metric("Paid", f"₹{fee['paid_amount']:,.0f}")
            c3.metric("Pending", f"₹{fee['total_fees']-fee['paid_amount']:,.0f}")
            st.markdown(f"Status: {badge(fee['status'])} &nbsp; Due date: {fee['due_date']}", unsafe_allow_html=True)

            if fee["status"] == "PENDING":
                st.divider()
                st.subheader("Request Fee Extension")
                with st.form("fee_ext"):
                    reason = st.text_area("Reason")
                    requested_date = st.date_input("Requested Extension Date")
                    doc = st.file_uploader("Supporting document (optional)", key="fee_doc")
                    submit = st.form_submit_button("Submit Request")
                if submit:
                    req_id = db.new_id("HVS-FX")
                    conn.execute("INSERT INTO fee_extension_requests (request_id, student_id, parent_hvs_id, "
                                "reason, requested_date, created_at) VALUES (?,?,?,?,?,?)",
                                (req_id, selected_id, user["hvs_id"], reason, str(requested_date), db.now()))
                    conn.commit()
                    db.log_audit(user["hvs_id"], "FEE_EXT_SUBMITTED", req_id)
                    st.success(f"Fee extension request submitted: {req_id}")
                    st.rerun()

    with tabs[5]:
        notices = conn.execute("SELECT * FROM notices WHERE audience IN ('ALL','PARENT') ORDER BY id DESC").fetchall()
        for n in notices:
            st.info(f"**{n['title']}**  \n{n['message']}  \n*{n['created_at']}*")

    conn.close()


# ----------------------------------------------------------------------
# FACULTY
# ----------------------------------------------------------------------
def faculty_dashboard(user):
    conn = db.get_conn()
    tabs = st.tabs(["My Classes", "Mark Attendance", "Attendance History", "Notices"])

    students = conn.execute("SELECT * FROM students").fetchall()

    with tabs[0]:
        st.dataframe(pd.DataFrame([dict(r) for r in students]), use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Mark Attendance")
        classes = sorted(set(s["class_name"] for s in students))
        selected_class = st.selectbox("Class", classes)
        subject = st.text_input("Subject", value="General")
        date = st.date_input("Date", value=datetime.now())
        class_students = [s for s in students if s["class_name"] == selected_class]
        statuses = {}
        for s in class_students:
            statuses[s["student_id"]] = st.radio(s["name"], ["PRESENT", "ABSENT"], horizontal=True,
                                                 key=f"att_{s['student_id']}_{date}")
        if st.button("Submit Attendance"):
            for sid, status in statuses.items():
                conn.execute("INSERT INTO attendance (student_id, date, subject, status, marked_by) "
                           "VALUES (?,?,?,?,?)", (sid, str(date), subject, status, user["hvs_id"]))
            conn.commit()
            db.log_audit(user["hvs_id"], "ATTENDANCE_MARKED", f"{selected_class} / {subject} / {date}")
            st.success("Attendance submitted.")

    with tabs[2]:
        att = conn.execute("""
            SELECT s.name, a.date, a.subject, a.status FROM attendance a
            JOIN students s ON s.student_id = a.student_id
            ORDER BY a.date DESC LIMIT 100
        """).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in att]), use_container_width=True, hide_index=True)

    with tabs[3]:
        notices = conn.execute("SELECT * FROM notices WHERE audience IN ('ALL','FACULTY','STAFF') "
                               "ORDER BY id DESC").fetchall()
        for n in notices:
            st.info(f"**{n['title']}**  \n{n['message']}")

    conn.close()


# ----------------------------------------------------------------------
# ACCOUNTS
# ----------------------------------------------------------------------
def accounts_dashboard(user):
    conn = db.get_conn()
    tabs = st.tabs(["Fee Records", "Fee Extension Requests", "Reports"])

    with tabs[0]:
        fees = conn.execute("""
            SELECT f.*, s.name FROM fee_records f JOIN students s ON s.student_id = f.student_id
        """).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in fees]), use_container_width=True, hide_index=True)

    with tabs[1]:
        rows = conn.execute("""
            SELECT fx.*, s.name as student_name FROM fee_extension_requests fx
            JOIN students s ON s.student_id = fx.student_id
            WHERE fx.accounts_decision='PENDING'
        """).fetchall()
        for r in rows:
            with st.container(border=True):
                st.markdown(f"**{r['request_id']}** — {r['student_name']}  \n*{r['reason']}*")
                c1, c2 = st.columns(2)
                if c1.button("Recommend Approval", key=f"rec_{r['request_id']}"):
                    conn.execute("UPDATE fee_extension_requests SET accounts_decision='RECOMMENDED' "
                               "WHERE request_id=?", (r["request_id"],))
                    conn.commit()
                    db.log_audit(user["hvs_id"], "FEE_EXT_RECOMMENDED", r["request_id"])
                    st.rerun()
                if c2.button("Reject", key=f"rejacc_{r['request_id']}"):
                    conn.execute("UPDATE fee_extension_requests SET accounts_decision='REJECTED' "
                               "WHERE request_id=?", (r["request_id"],))
                    conn.commit()
                    db.log_audit(user["hvs_id"], "FEE_EXT_REJECTED_ACCOUNTS", r["request_id"])
                    st.rerun()

    with tabs[2]:
        total = conn.execute("SELECT SUM(total_fees) t, SUM(paid_amount) p FROM fee_records").fetchone()
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Fees Billed", f"₹{total['t'] or 0:,.0f}")
        c2.metric("Total Collected", f"₹{total['p'] or 0:,.0f}")
        c3.metric("Outstanding", f"₹{(total['t'] or 0) - (total['p'] or 0):,.0f}")

    conn.close()


# ----------------------------------------------------------------------
# WARDEN
# ----------------------------------------------------------------------
def warden_dashboard(user):
    conn = db.get_conn()
    tabs = st.tabs(["Hostel Students", "Mark Hostel Attendance", "Attendance History"])
    hostel_students = conn.execute("SELECT * FROM students WHERE is_hostel=1").fetchall()

    with tabs[0]:
        st.dataframe(pd.DataFrame([dict(r) for r in hostel_students]), use_container_width=True, hide_index=True)

    with tabs[1]:
        date = st.date_input("Date", value=datetime.now())
        statuses = {}
        for s in hostel_students:
            statuses[s["student_id"]] = st.radio(s["name"], ["PRESENT", "ABSENT"], horizontal=True,
                                                 key=f"hos_{s['student_id']}_{date}")
        if st.button("Submit Hostel Attendance"):
            for sid, status in statuses.items():
                conn.execute("INSERT INTO hostel_attendance (student_id, date, status, marked_by) "
                           "VALUES (?,?,?,?)", (sid, str(date), status, user["hvs_id"]))
            conn.commit()
            db.log_audit(user["hvs_id"], "HOSTEL_ATTENDANCE_MARKED", str(date))
            st.success("Hostel attendance submitted.")

    with tabs[2]:
        hist = conn.execute("""
            SELECT s.name, h.date, h.status FROM hostel_attendance h
            JOIN students s ON s.student_id = h.student_id ORDER BY h.date DESC LIMIT 100
        """).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in hist]), use_container_width=True, hide_index=True)

    conn.close()


# ----------------------------------------------------------------------
# MESS
# ----------------------------------------------------------------------
def mess_dashboard(user):
    conn = db.get_conn()
    tabs = st.tabs(["Students", "Mark Mess Attendance", "Reports"])
    hostel_students = conn.execute("SELECT * FROM students WHERE is_hostel=1").fetchall()

    with tabs[0]:
        st.dataframe(pd.DataFrame([dict(r) for r in hostel_students]), use_container_width=True, hide_index=True)

    with tabs[1]:
        date = st.date_input("Date", value=datetime.now())
        meal = st.selectbox("Meal", ["Breakfast", "Lunch", "Dinner"])
        statuses = {}
        for s in hostel_students:
            statuses[s["student_id"]] = st.radio(s["name"], ["PRESENT", "ABSENT"], horizontal=True,
                                                 key=f"mess_{s['student_id']}_{date}_{meal}")
        if st.button("Submit Mess Attendance"):
            for sid, status in statuses.items():
                conn.execute("INSERT INTO mess_attendance (student_id, date, meal, status, marked_by) "
                           "VALUES (?,?,?,?,?)", (sid, str(date), meal, status, user["hvs_id"]))
            conn.commit()
            db.log_audit(user["hvs_id"], "MESS_ATTENDANCE_MARKED", f"{date} {meal}")
            st.success("Mess attendance submitted.")

    with tabs[2]:
        hist = conn.execute("""
            SELECT s.name, m.date, m.meal, m.status FROM mess_attendance m
            JOIN students s ON s.student_id = m.student_id ORDER BY m.date DESC LIMIT 100
        """).fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in hist]), use_container_width=True, hide_index=True)

    conn.close()


# ----------------------------------------------------------------------
# DTP / OMR
# ----------------------------------------------------------------------
def dtp_dashboard(user):
    conn = db.get_conn()
    tabs = st.tabs(["Examinations", "Enter / Import Marks", "Rank Lists", "Publish Results"])

    with tabs[0]:
        with st.form("new_exam"):
            exam_name = st.text_input("Exam Name")
            exam_date = st.date_input("Exam Date")
            create = st.form_submit_button("Create Examination")
        if create and exam_name:
            exam_id = db.new_id("HVS-EX")
            conn.execute("INSERT INTO examinations (exam_id, exam_name, exam_date, published) VALUES (?,?,?,0)",
                        (exam_id, exam_name, str(exam_date)))
            conn.commit()
            db.log_audit(user["hvs_id"], "EXAM_CREATED", exam_id)
            st.success(f"Examination created: {exam_id}")
            st.rerun()
        exams = conn.execute("SELECT * FROM examinations").fetchall()
        st.dataframe(pd.DataFrame([dict(r) for r in exams]), use_container_width=True, hide_index=True)

    with tabs[1]:
        exams = conn.execute("SELECT * FROM examinations").fetchall()
        students = conn.execute("SELECT * FROM students").fetchall()
        if exams:
            exam_map = {e["exam_id"]: e["exam_name"] for e in exams}
            exam_id = st.selectbox("Exam", list(exam_map.keys()), format_func=lambda x: exam_map[x])
            student_map = {s["student_id"]: s["name"] for s in students}
            student_id = st.selectbox("Student", list(student_map.keys()), format_func=lambda x: student_map[x])
            with st.form("add_marks"):
                subject = st.text_input("Subject")
                marks_obtained = st.number_input("Marks Obtained", min_value=0.0)
                max_marks = st.number_input("Max Marks", min_value=1.0, value=50.0)
                add = st.form_submit_button("Add Marks")
            if add:
                conn.execute("INSERT INTO marks (exam_id, student_id, subject, marks_obtained, max_marks) "
                           "VALUES (?,?,?,?,?)", (exam_id, student_id, subject, marks_obtained, max_marks))
                conn.commit()
                db.log_audit(user["hvs_id"], "MARKS_ADDED", f"{exam_id}/{student_id}/{subject}")
                st.success("Marks added.")
        else:
            st.info("Create an examination first.")

    with tabs[2]:
        exams = conn.execute("SELECT * FROM examinations").fetchall()
        if exams:
            exam_map = {e["exam_id"]: e["exam_name"] for e in exams}
            exam_id = st.selectbox("Exam for Rank List", list(exam_map.keys()), format_func=lambda x: exam_map[x],
                                   key="rank_exam")
            rows = conn.execute("""
                SELECT s.name, SUM(m.marks_obtained) total, SUM(m.max_marks) max_total
                FROM marks m JOIN students s ON s.student_id = m.student_id
                WHERE m.exam_id=? GROUP BY m.student_id ORDER BY total DESC
            """, (exam_id,)).fetchall()
            df = pd.DataFrame([dict(r) for r in rows])
            if not df.empty:
                df["rank"] = range(1, len(df) + 1)
                df["percentage"] = round(100 * df["total"] / df["max_total"], 1)
                st.dataframe(df, use_container_width=True, hide_index=True)

    with tabs[3]:
        exams = conn.execute("SELECT * FROM examinations WHERE published=0").fetchall()
        for e in exams:
            with st.container(border=True):
                st.markdown(f"**{e['exam_name']}** ({e['exam_id']}) — not yet published")
                if st.button("Publish Results", key=f"pub_{e['exam_id']}"):
                    conn.execute("UPDATE examinations SET published=1 WHERE exam_id=?", (e["exam_id"],))
                    conn.commit()
                    db.log_audit(user["hvs_id"], "RESULTS_PUBLISHED", e["exam_id"])
                    st.success("Results published — visible to parents now.")
                    st.rerun()
        if not exams:
            st.info("All examinations are published, or none exist yet.")

    conn.close()


# ----------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------
if auth.current_user():
    app_shell()
else:
    login_screen()
