"""
database.py — HVS Connect
SQLite schema + seed data + all CRUD helper functions.
Single-file "backend" so the whole app can run on Streamlit Community Cloud
with zero external services (Postgres/MySQL can be swapped in later by
rewriting this module only — the rest of the app talks to these functions).
"""

import sqlite3
import hashlib
import secrets
import string
from datetime import datetime, timedelta

DB_PATH = "hvs_connect.db"


# ----------------------------------------------------------------------
# Connection helpers
# ----------------------------------------------------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def hash_password(password: str) -> str:
    salt = "hvs_static_salt_v1"  # demo only — use per-user random salt + bcrypt in production
    return hashlib.sha256((salt + password).encode()).hexdigest()


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    hvs_id TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,           -- DEAN, PARENT, FACULTY, ACCOUNTS, WARDEN, MESS, DTP
    full_name TEXT NOT NULL,
    mobile TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',   -- ACTIVE, DISABLED, PENDING_APPROVAL
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    class_name TEXT,
    section TEXT,
    parent_hvs_id TEXT,
    is_hostel INTEGER DEFAULT 0,
    FOREIGN KEY (parent_hvs_id) REFERENCES users(hvs_id)
);

CREATE TABLE IF NOT EXISTS attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
    date TEXT,
    subject TEXT,
    status TEXT,          -- PRESENT / ABSENT
    marked_by TEXT,
    FOREIGN KEY (student_id) REFERENCES students(student_id)
);

CREATE TABLE IF NOT EXISTS hostel_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
    date TEXT,
    status TEXT,
    marked_by TEXT
);

CREATE TABLE IF NOT EXISTS mess_attendance (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id TEXT,
    date TEXT,
    meal TEXT,
    status TEXT,
    marked_by TEXT
);

CREATE TABLE IF NOT EXISTS leave_requests (
    leave_id TEXT PRIMARY KEY,
    student_id TEXT,
    parent_hvs_id TEXT,
    leave_type TEXT,
    from_date TEXT,
    to_date TEXT,
    reason TEXT,
    status TEXT DEFAULT 'PENDING',   -- PENDING, APPROVED, REJECTED, CANCELLED
    created_at TEXT,
    decided_by TEXT,
    decided_at TEXT
);

CREATE TABLE IF NOT EXISTS fee_records (
    student_id TEXT PRIMARY KEY,
    total_fees REAL,
    paid_amount REAL,
    due_date TEXT,
    status TEXT   -- PAID, PENDING, PARTIAL
);

CREATE TABLE IF NOT EXISTS fee_extension_requests (
    request_id TEXT PRIMARY KEY,
    student_id TEXT,
    parent_hvs_id TEXT,
    reason TEXT,
    requested_date TEXT,
    accounts_decision TEXT DEFAULT 'PENDING',  -- PENDING, RECOMMENDED, REJECTED
    dean_decision TEXT DEFAULT 'PENDING',      -- PENDING, APPROVED, REJECTED
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS examinations (
    exam_id TEXT PRIMARY KEY,
    exam_name TEXT,
    exam_date TEXT,
    published INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS marks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id TEXT,
    student_id TEXT,
    subject TEXT,
    marks_obtained REAL,
    max_marks REAL,
    FOREIGN KEY (exam_id) REFERENCES examinations(exam_id)
);

CREATE TABLE IF NOT EXISTS notices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    message TEXT,
    posted_by TEXT,
    audience TEXT,   -- ALL, PARENT, FACULTY, STAFF
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hvs_id TEXT,
    message TEXT,
    is_read INTEGER DEFAULT 0,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor TEXT,
    action TEXT,
    details TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS system_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS registration_requests (
    request_id TEXT PRIMARY KEY,
    full_name TEXT,
    mobile TEXT,
    requested_role TEXT,
    status TEXT DEFAULT 'PENDING',  -- PENDING, APPROVED, REJECTED
    created_at TEXT
);
"""


def init_db():
    conn = get_conn()
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


# ----------------------------------------------------------------------
# Seed demo data (only runs once — checked by presence of HVS-D001)
# ----------------------------------------------------------------------
def seed_demo_data():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM users WHERE hvs_id = 'HVS-D001'")
    if cur.fetchone():
        conn.close()
        return  # already seeded

    demo_password = "Welcome@123"  # same demo password for every seeded account
    pw_hash = hash_password(demo_password)

    users = [
        ("HVS-D001", "DEAN", "Dr. K.K.R.", "9990000001"),
        ("HVS-P001", "PARENT", "Mr. Rajesh Sharma", "9990000002"),
        ("HVS-P002", "PARENT", "Mrs. Anita Verma", "9990000003"),
        ("HVS-F001", "FACULTY", "Mrs. Sunita Rao", "9990000004"),
        ("HVS-A001", "ACCOUNTS", "Mr. Vikram Joshi", "9990000005"),
        ("HVS-W001", "WARDEN", "Mr. Suresh Nair", "9990000006"),
        ("HVS-M001", "MESS", "Mr. Ramesh Yadav", "9990000007"),
        ("HVS-DTP001", "DTP", "Ms. Priya Menon", "9990000008"),
    ]
    for hvs_id, role, name, mobile in users:
        cur.execute(
            "INSERT INTO users (hvs_id, password_hash, role, full_name, mobile, status, created_at) "
            "VALUES (?,?,?,?,?, 'ACTIVE', ?)",
            (hvs_id, pw_hash, role, name, mobile, now()),
        )

    students = [
        ("HVS-S1001", "Aarav Sharma", "Grade 6", "A", "HVS-P001", 1),
        ("HVS-S1002", "Diya Sharma", "Grade 3", "B", "HVS-P001", 0),
        ("HVS-S1003", "Kabir Verma", "Grade 8", "A", "HVS-P002", 1),
    ]
    for sid, name, cls, sec, parent, hostel in students:
        cur.execute(
            "INSERT INTO students (student_id, name, class_name, section, parent_hvs_id, is_hostel) "
            "VALUES (?,?,?,?,?,?)",
            (sid, name, cls, sec, parent, hostel),
        )

    # attendance — last 10 days, mostly present
    import random
    for sid in ["HVS-S1001", "HVS-S1002", "HVS-S1003"]:
        for i in range(10):
            d = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            status = "ABSENT" if random.random() < 0.1 else "PRESENT"
            cur.execute(
                "INSERT INTO attendance (student_id, date, subject, status, marked_by) VALUES (?,?,?,?,?)",
                (sid, d, "General", status, "HVS-F001"),
            )

    # fee records
    cur.execute("INSERT INTO fee_records VALUES ('HVS-S1001', 120000, 120000, '2026-06-30', 'PAID')")
    cur.execute("INSERT INTO fee_records VALUES ('HVS-S1002', 95000, 50000, '2026-09-30', 'PENDING')")
    cur.execute("INSERT INTO fee_records VALUES ('HVS-S1003', 110000, 110000, '2026-06-30', 'PAID')")

    # a sample pending leave request
    cur.execute(
        "INSERT INTO leave_requests (leave_id, student_id, parent_hvs_id, leave_type, from_date, to_date, "
        "reason, status, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        ("HVS-LV-1001", "HVS-S1001", "HVS-P001", "Medical", "2026-09-22", "2026-09-24",
         "Fever, doctor advised rest.", "PENDING", now()),
    )

    # a sample pending fee extension request
    cur.execute(
        "INSERT INTO fee_extension_requests (request_id, student_id, parent_hvs_id, reason, requested_date, "
        "created_at) VALUES (?,?,?,?,?,?)",
        ("HVS-FX-1001", "HVS-S1002", "HVS-P001", "Salary delayed this month.", "2026-10-15", now()),
    )

    # sample exam + marks
    cur.execute("INSERT INTO examinations VALUES ('HVS-EX-W37', 'Weekly Test - Week 37', '2026-09-15', 1)")
    for sid, s1, s2 in [("HVS-S1001", 42, 38), ("HVS-S1003", 47, 45)]:
        cur.execute("INSERT INTO marks (exam_id, student_id, subject, marks_obtained, max_marks) VALUES "
                    "('HVS-EX-W37', ?, 'Mathematics', ?, 50)", (sid, s1))
        cur.execute("INSERT INTO marks (exam_id, student_id, subject, marks_obtained, max_marks) VALUES "
                    "('HVS-EX-W37', ?, 'Science', ?, 50)", (sid, s2))

    # notice
    cur.execute(
        "INSERT INTO notices (title, message, posted_by, audience, created_at) VALUES (?,?,?,?,?)",
        ("Welcome to HVS Connect", "This platform replaces paper and WhatsApp based processes at HVS.",
         "HVS-D001", "ALL", now()),
    )

    # system settings
    cur.execute("INSERT INTO system_settings VALUES ('system_paused', '0')")
    cur.execute("INSERT INTO system_settings VALUES ('attendance_fee_lock', '1')")

    conn.commit()
    conn.close()


# ----------------------------------------------------------------------
# Generic helpers used across the app
# ----------------------------------------------------------------------
def log_audit(actor, action, details=""):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_logs (actor, action, details, created_at) VALUES (?,?,?,?)",
        (actor, action, details, now()),
    )
    conn.commit()
    conn.close()


def add_notification(hvs_id, message):
    conn = get_conn()
    conn.execute(
        "INSERT INTO notifications (hvs_id, message, created_at) VALUES (?,?,?)",
        (hvs_id, message, now()),
    )
    conn.commit()
    conn.close()


def get_setting(key, default=None):
    conn = get_conn()
    row = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute("INSERT INTO system_settings (key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()
    conn.close()


def new_id(prefix):
    return f"{prefix}-{secrets.token_hex(3).upper()}"


def gen_otp():
    return "".join(secrets.choice(string.digits) for _ in range(6))
