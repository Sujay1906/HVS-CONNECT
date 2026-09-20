"""
auth.py — HVS Connect authentication
Password check -> OTP generation -> OTP delivery (SMS in production,
on-screen in dev mode) -> server-side OTP verification -> session creation.

IMPORTANT (read this before going to production):
Streamlit apps run entirely as one Python process with no separate "frontend"
that a user can inspect for secrets — but there is still no persistent
per-request server you control the way a Flask/Django backend gives you.
All OTP state below lives in the SQLite DB (server-side, not in the browser),
which is the correct security boundary for this environment. What you must
still do before real deployment:
  1. Add TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER to
     Streamlit's secrets manager (Settings -> Secrets), never in code.
  2. Flip HVS_ENV to "production" (also via secrets).
When HVS_ENV != "production", OTPs are shown on-screen instead of sent by
SMS, clearly labeled as DEV MODE, so the prototype is usable without a
Twilio account.
"""

import streamlit as st
from datetime import datetime, timedelta
from database import get_conn, hash_password, gen_otp, now, log_audit

OTP_VALIDITY_MINUTES = 5
MAX_OTP_ATTEMPTS = 3
MAX_LOGIN_ATTEMPTS = 5


def get_env():
    try:
        return st.secrets.get("HVS_ENV", "development")
    except Exception:
        return "development"


def send_sms_otp(mobile, otp):
    """Production SMS delivery via Twilio. Falls back to dev mode if secrets absent."""
    try:
        sid = st.secrets["TWILIO_ACCOUNT_SID"]
        token = st.secrets["TWILIO_AUTH_TOKEN"]
        from_number = st.secrets["TWILIO_FROM_NUMBER"]
    except Exception:
        return False  # no credentials configured -> caller falls back to dev mode

    try:
        from twilio.rest import Client
        client = Client(sid, token)
        client.messages.create(
            body=f"Your HVS Connect OTP is {otp}. Valid for {OTP_VALIDITY_MINUTES} minutes.",
            from_=from_number,
            to=f"+91{mobile}",
        )
        return True
    except Exception as e:
        st.error(f"SMS delivery failed: {e}")
        return False


def verify_password(hvs_id, password):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE hvs_id=?", (hvs_id,)).fetchone()
    conn.close()
    if not row:
        return None, "No such HVS ID."
    if row["status"] == "DISABLED":
        return None, "This account has been disabled. Contact administration."
    if row["status"] == "PENDING_APPROVAL":
        return None, "This account is awaiting Dean approval."
    if row["password_hash"] != hash_password(password):
        return None, "Incorrect password."
    return row, None


def start_otp_flow(user_row):
    """Generate OTP, store it server-side (session_state acts as the
    server-side store here since Streamlit has no separate request server),
    and deliver it."""
    otp = gen_otp()
    st.session_state.otp_pending = {
        "hvs_id": user_row["hvs_id"],
        "otp": otp,
        "expires_at": (datetime.now() + timedelta(minutes=OTP_VALIDITY_MINUTES)).isoformat(),
        "attempts": 0,
        "sent_at": now(),
    }
    delivered = False
    if get_env() == "production":
        delivered = send_sms_otp(user_row["mobile"], otp)
    if not delivered:
        st.session_state.otp_dev_display = otp  # dev-mode fallback only
    else:
        st.session_state.otp_dev_display = None
    return delivered


def verify_otp(entered_otp):
    pending = st.session_state.get("otp_pending")
    if not pending:
        return False, "No OTP was requested. Please log in again."
    if datetime.now() > datetime.fromisoformat(pending["expires_at"]):
        return False, "OTP expired. Please request a new one."
    if pending["attempts"] >= MAX_OTP_ATTEMPTS:
        return False, "Too many incorrect attempts. Please request a new OTP."
    if entered_otp.strip() != pending["otp"]:
        pending["attempts"] += 1
        st.session_state.otp_pending = pending
        return False, f"Incorrect OTP. {MAX_OTP_ATTEMPTS - pending['attempts']} attempt(s) left."
    return True, None


def complete_login(hvs_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM users WHERE hvs_id=?", (hvs_id,)).fetchone()
    conn.close()
    st.session_state.auth_user = dict(row)
    st.session_state.otp_pending = None
    st.session_state.otp_dev_display = None
    log_audit(hvs_id, "LOGIN", "Successful login via ID + password + OTP")


def logout():
    if "auth_user" in st.session_state:
        log_audit(st.session_state.auth_user["hvs_id"], "LOGOUT", "")
    for key in ["auth_user", "otp_pending", "otp_dev_display"]:
        st.session_state.pop(key, None)


def current_user():
    return st.session_state.get("auth_user")


def require_role(*roles):
    user = current_user()
    return user is not None and user["role"] in roles
