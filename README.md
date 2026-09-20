# HVS Connect

A working prototype of the centralized digital platform for Dr. KKR's Happy Valley School, built with Python + Streamlit + SQLite.

## What's implemented

- HVS ID + password + OTP login, with automatic role detection (no role picker)
- Dean, Parent, Faculty, Accounts, Warden, Mess, and DTP/OMR dashboards
- Leave request workflow (Parent → Dean, with statuses and audit trail)
- Fee status + fee-extension workflow (Parent → Accounts → Dean)
- Digital attendance (class, hostel, mess) replacing paper registers
- Exam creation, marks entry, auto-generated rank lists, and a publish gate so parents can't see results early
- Notices, notifications, staff account registration/approval, user management, system pause/resume, and a full audit log
- Configurable fee-vs-attendance policy toggle (Dean-controlled, not hard-coded)

All data lives in a local SQLite file (`hvs_connect.db`), which is created and seeded with demo data automatically on first run.

## Demo accounts

Every seeded account uses the same demo password below. **Change these before showing this to anyone outside your team**, and definitely before any real deployment — see "Going to production" below.

| HVS ID | Role | Password |
|---|---|---|
| HVS-D001 | Dean | `Welcome@123` |
| HVS-P001 | Parent (children: Aarav Sharma, Diya Sharma) | `Welcome@123` |
| HVS-P002 | Parent (child: Kabir Verma) | `Welcome@123` |
| HVS-F001 | Faculty | `Welcome@123` |
| HVS-A001 | Accounts | `Welcome@123` |
| HVS-W001 | Warden | `Welcome@123` |
| HVS-M001 | Mess In-charge | `Welcome@123` |
| HVS-DTP001 | DTP/OMR | `Welcome@123` |

**OTP in dev mode:** since no SMS provider is configured by default, the app runs in development mode — after entering the password, the OTP is shown directly on screen in a yellow box instead of being texted. This is clearly labeled "DEV MODE" in the UI so it's never mistaken for production behavior.

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`).

## Push to GitHub

```bash
cd hvs-connect
git init
git add .
git commit -m "Initial HVS Connect prototype"
git branch -M main
git remote add origin https://github.com/<your-username>/hvs-connect.git
git push -u origin main
```

(Create the empty `hvs-connect` repository on GitHub first, via github.com → New repository — don't initialize it with a README so there's no merge conflict.)

## Deploy on Streamlit Community Cloud

1. Go to **share.streamlit.io** and sign in with your GitHub account.
2. Click **"New app"**, pick your `hvs-connect` repo, branch `main`, and set the main file path to `app.py`.
3. Click **Deploy**. Streamlit installs `requirements.txt` and starts the app automatically.
4. (Optional, for real SMS OTP) In the app's **Settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example` with your real Twilio credentials filled in, and set `HVS_ENV = "production"`. Without this, the app keeps working fine in dev mode with on-screen OTPs.

Every time you `git push` to `main`, Streamlit Cloud redeploys automatically.

## Going to production (do this before real school use)

The spec this was built from calls for real security hardening — this prototype gets you a working demo, not a production system. Before using it with real student/parent data:

- Replace the SHA-256 + static-salt hashing in `database.py` with `bcrypt` or `argon2` and a per-user random salt.
- Add the Twilio secrets above and set `HVS_ENV = "production"` so OTPs are actually texted, not shown on screen.
- Move from SQLite to a managed Postgres/MySQL database (SQLite is fine for a demo but isn't built for concurrent writes at scale).
- Add rate limiting on login/OTP attempts at the network layer, not just in-app counters.
- Put the whole thing behind HTTPS with a real domain (Streamlit Cloud gives you HTTPS by default).
- Review the parent-data isolation logic in `app.py` (`parent_dashboard`) — it currently filters by `parent_hvs_id` at the database query level, which is the right approach, but any additional pages you add must follow the same pattern so a parent can never query another child's data.

## File structure

```
hvs-connect/
├── app.py              # Streamlit UI + routing for all 7 roles
├── auth.py             # password check, OTP generation/verification, dev/prod SMS split
├── database.py         # SQLite schema, seed data, all CRUD helpers
├── requirements.txt
├── .gitignore
└── .streamlit/
    └── secrets.toml.example
```
