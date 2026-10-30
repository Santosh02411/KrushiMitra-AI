"""
auth.py
-------
Session-based authentication with real password hashing (werkzeug's
scrypt-based hasher — no plaintext or reversible storage) and role-based
access (farmer/admin).

Email (welcome message, password reset codes) is sent for real, via
either of two real providers, tried in this order:

  1. Brevo's HTTP email API, if BREVO_API_KEY + BREVO_SENDER_EMAIL are
     set in .env. This is the one that actually works on Render's free
     tier — Render blocks all outbound SMTP ports (25/465/587) on free
     web services as an anti-spam measure (confirmed via their own
     changelog), which silently breaks option 2 below on that specific
     host. Brevo's API runs over plain HTTPS (port 443), which isn't
     blocked, and its free tier covers 300 emails/day.
  2. Plain SMTP, if SMTP_HOST/PORT/USER/PASSWORD are set instead — still
     the simpler option for local development or any host that doesn't
     block outbound SMTP. See .env.example for Gmail App Password setup,
     and scripts/test_email.py to verify either configuration
     independent of the web app.

Without either configured, there is no way to actually deliver an email,
so the reset code is returned directly in the API response instead,
clearly labeled as the dev-mode fallback.
"""

import os
import secrets
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from functools import wraps

import requests
from flask import g, jsonify, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db_compat

DB_PATH = os.getenv("DATABASE_PATH") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "krushi.db")
RESET_TOKEN_TTL_MINUTES = 30
BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"


def email_config_status():
    """Safe to expose publicly — reports WHETHER email is configured and
    which provider/host, never any secret. Lets the login page show a
    real, live status instead of the user having to guess whether their
    .env edits actually took effect (a common gotcha: env vars are only
    read once, at server startup — editing .env while the server is
    running does nothing until it's restarted)."""
    brevo_key = os.getenv("BREVO_API_KEY")
    brevo_sender = os.getenv("BREVO_SENDER_EMAIL")
    if brevo_key and brevo_sender:
        return {"configured": True, "provider": "Brevo API", "host": "api.brevo.com", "user": brevo_sender}

    host = os.getenv("SMTP_HOST")
    user = os.getenv("SMTP_USER")
    configured = bool(host and os.getenv("SMTP_PORT") and user and os.getenv("SMTP_PASSWORD"))
    return {"configured": configured, "provider": "SMTP" if configured else None,
            "host": host if configured else None, "user": user if configured else None}


def _send_via_brevo(to_email, subject, body):
    api_key = os.getenv("BREVO_API_KEY")
    sender_email = os.getenv("BREVO_SENDER_EMAIL")
    sender_name = os.getenv("BREVO_SENDER_NAME") or "Krushi"
    try:
        resp = requests.post(
            BREVO_API_URL,
            headers={"accept": "application/json", "api-key": api_key, "content-type": "application/json"},
            json={
                "sender": {"name": sender_name, "email": sender_email},
                "to": [{"email": to_email}],
                "subject": subject,
                "textContent": body,
            },
            timeout=15,
        )
        if resp.status_code in (200, 201):
            return {"sent": True}
        # Brevo returns a JSON body describing exactly what went wrong
        # (unverified sender, bad key, over the daily quota, etc.) —
        # surface that real detail rather than just the status code.
        try:
            detail = resp.json().get("message", resp.text)
        except ValueError:
            detail = resp.text
        print(f"[auth] Brevo send failed ({resp.status_code}): {detail}")
        return {"sent": False, "reason": "error", "detail": detail}
    except requests.exceptions.RequestException as e:
        print(f"[auth] Brevo request failed: {e}")
        return {"sent": False, "reason": "error", "detail": str(e)}


def _send_via_smtp(to_email, subject, body):
    host = os.getenv("SMTP_HOST")
    port = os.getenv("SMTP_PORT")
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")
    from_addr = os.getenv("SMTP_FROM") or user

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email

        with smtplib.SMTP(host, int(port), timeout=15) as server:
            server.starttls()
            server.login(user, password)
            server.sendmail(from_addr, [to_email], msg.as_string())
        return {"sent": True}
    except Exception as e:
        print(f"[auth] SMTP send failed: {e}")
        return {"sent": False, "reason": "error", "detail": str(e)}


def send_email(to_email, subject, body):
    """Sends a real email via Brevo's API (preferred — works on hosts
    that block outbound SMTP, like Render's free tier) or SMTP (fallback
    for local dev / hosts that don't block it), whichever is configured.
    Returns a dict:
      {"sent": True} on a real successful send
      {"sent": False, "reason": "not_configured"} if neither is set
      {"sent": False, "reason": "error", "detail": "..."} if a provider
        is configured but the send itself failed (bad credentials,
        unverified sender, blocked port, over quota, etc.)
    Callers use "reason" to decide what to tell the user — a real send
    failure is a different, more actionable message than "not configured"."""
    if os.getenv("BREVO_API_KEY") and os.getenv("BREVO_SENDER_EMAIL"):
        return _send_via_brevo(to_email, subject, body)
    if all([os.getenv("SMTP_HOST"), os.getenv("SMTP_PORT"), os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")]):
        return _send_via_smtp(to_email, subject, body)
    return {"sent": False, "reason": "not_configured"}


def send_welcome_email(user):
    return send_email(
        user["email"], "Welcome to Krushi 🌱",
        f"Hi {user['name']},\n\n"
        f"Congratulations — your Krushi account has been created successfully!\n\n"
        f"You can now sign in and use the crop advisor, soil health check, market prices, "
        f"irrigation planner, and the rest of the tools.\n\n— Krushi",
    )


def get_db():
    return db_compat.get_connection(DB_PATH)


def init_auth_tables():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            location TEXT,
            farm_size_acres REAL,
            soil_type TEXT,
            preferred_language TEXT DEFAULT 'en',
            role TEXT NOT NULL DEFAULT 'farmer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)
    conn.commit()
    conn.close()


def register_user(name, email, password, location=None, farm_size_acres=None,
                   soil_type=None, preferred_language="en", role="farmer"):
    email = email.strip().lower()
    if role not in ("farmer", "admin"):
        role = "farmer"
    conn = get_db()
    try:
        insert_sql = """INSERT INTO users (name, email, password_hash, location, farm_size_acres,
               soil_type, preferred_language, role)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        params = (name.strip(), email, generate_password_hash(password), location,
                  farm_size_acres, soil_type, preferred_language, role)
        if db_compat.USING_POSTGRES:
            # psycopg2 has no cursor.lastrowid equivalent to sqlite3's —
            # ask Postgres to hand the new id straight back instead.
            cur = conn.execute(insert_sql + " RETURNING id", params)
            user_id = cur.fetchone()[0]
        else:
            cur = conn.execute(insert_sql, params)
            user_id = cur.lastrowid
        conn.commit()
        return {"success": True, "user_id": user_id}
    except db_compat.IntegrityError:
        return {"success": False, "error": "An account with this email already exists."}
    finally:
        conn.close()


def authenticate(email, password):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    conn.close()
    if row and check_password_hash(row["password_hash"], password):
        return dict(row)
    return None


def get_user_by_id(user_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def update_profile(user_id, **fields):
    allowed = {"name", "location", "farm_size_acres", "soil_type", "preferred_language"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return False
    conn = get_db()
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE users SET {set_clause} WHERE id = ?", (*updates.values(), user_id))
    conn.commit()
    conn.close()
    return True


# Every table that stores a row per-user, deleted alongside the account so
# "delete account" actually removes the person's real data rather than
# leaving orphaned rows behind under a dangling user_id.
_USER_DATA_TABLES = [
    "expenses", "income", "soil_health_logs", "water_usage_logs", "yield_logs",
    "crop_plans", "disease_checks", "fertilizer_usage_logs", "password_resets",
    "decision_plans", "user_uploads",
]


def delete_user(user_id):
    """Permanently deletes the account and every real record tied to it.
    Recommendations logged to the shared `recommendations` table are kept
    but anonymized (user_id set to NULL) rather than deleted, since that
    table also backs aggregate app-wide stats (e.g. the admin dashboard's
    'recommendations generated' count) that shouldn't silently drop."""
    conn = get_db()
    for table in _USER_DATA_TABLES:
        conn.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
    conn.execute("UPDATE recommendations SET user_id = NULL WHERE user_id = ?", (user_id,))
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()


def create_password_reset(email):
    """Returns (code, user) if the email exists, else (None, None). The
    raw 6-digit code is only ever returned here / to the caller — the DB
    stores only its hash, same principle as a password."""
    conn = get_db()
    row = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not row:
        conn.close()
        return None, None

    code = "".join(secrets.choice("0123456789") for _ in range(6))
    expires_at = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)
    conn.execute(
        "INSERT INTO password_resets (user_id, token_hash, expires_at) VALUES (?, ?, ?)",
        (row["id"], generate_password_hash(code), expires_at.isoformat()),
    )
    conn.commit()
    conn.close()
    return code, dict(row)


def _find_valid_reset(conn, user_id, code):
    """Shared lookup used by both verify (read-only) and reset (consuming).
    Returns the matching, unexpired, unused password_resets row, or None."""
    resets = conn.execute(
        "SELECT * FROM password_resets WHERE user_id = ? AND used = 0 ORDER BY id DESC",
        (user_id,),
    ).fetchall()
    for r in resets:
        # SQLite gives back the TIMESTAMP column as the ISO string it was
        # stored as; Postgres parses it back into a native datetime object
        # for the same column type — accept either rather than assuming.
        expires_at = r["expires_at"]
        if not isinstance(expires_at, datetime):
            expires_at = datetime.fromisoformat(expires_at)
        if check_password_hash(r["token_hash"], code) and expires_at >= datetime.utcnow():
            return r
    return None


def verify_reset_code(email, code):
    """Checks whether a code is valid WITHOUT consuming it — lets the UI
    confirm the code before showing the new-password fields, matching a
    real OTP flow (verify first, only then allow setting a new password)."""
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not user:
        conn.close()
        return False, "No account with this email."
    matched = _find_valid_reset(conn, user["id"], code)
    conn.close()
    if not matched:
        return False, "Incorrect or expired code."
    return True, None


def reset_password(email, token, new_password):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()
    if not user:
        conn.close()
        return False, "No account with this email."

    matched = _find_valid_reset(conn, user["id"], token)
    if not matched:
        conn.close()
        return False, "Incorrect or expired code."

    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                 (generate_password_hash(new_password), user["id"]))
    conn.execute("UPDATE password_resets SET used = 1 WHERE id = ?", (matched["id"],))
    conn.commit()
    conn.close()
    return True, None


# ---------------------------------------------------------------------- #
# Session helpers / decorators
# ---------------------------------------------------------------------- #
def login_user_session(user):
    session["user_id"] = user["id"]
    session["role"] = user["role"]


def logout_user_session():
    session.clear()


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    # Cached for the duration of one request: the nav template, the route and
    # the login check would otherwise each hit the database separately.
    if "_current_user" not in g or g._current_user_id != user_id:
        g._current_user = get_user_by_id(user_id)
        g._current_user_id = user_id
    return g._current_user


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"success": False, "error": "Login required."}), 401
        if current_user() is None:  # account was deleted / demo guest expired
            session.clear()
            return jsonify({"success": False, "error": "Your session has expired - please sign in again."}), 401
        return fn(*args, **kwargs)
    return wrapper


def page_login_required(fn):
    """Like login_required, but for HTML page routes: redirects to /login
    instead of returning a JSON 401, since a browser navigating to a page
    needs a page back, not an API error body."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_page", next=request.path))
        if current_user() is None:
            session.clear()
            return redirect(url_for("login_page", next=request.path))
        return fn(*args, **kwargs)
    return wrapper


def page_admin_required(fn):
    """Page-route version of admin_required: redirects rather than
    returning a JSON error body."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login_page", next=request.path))
        user = current_user()
        if not user or user.get("role") != "admin":
            return redirect(url_for("home_page"))
        return fn(*args, **kwargs)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"success": False, "error": "Login required."}), 401
        user = current_user()
        if not user or user.get("role") != "admin":
            return jsonify({"success": False, "error": "Admin access required."}), 403
        return fn(*args, **kwargs)
    return wrapper


def public_user_dict(user):
    if not user:
        return None
    return {
        "id": user["id"], "name": user["name"], "email": user["email"],
        "location": user["location"], "farm_size_acres": user["farm_size_acres"],
        "soil_type": user["soil_type"], "preferred_language": user["preferred_language"],
        "role": user["role"], "is_demo": is_demo_user(user),
    }


# ---------------------------------------------------------------------- #
# Demo mode - "Try the demo" without registering
# ---------------------------------------------------------------------- #
# Every click creates a fresh, isolated guest account (own data, random
# unrecoverable password) so one visitor never sees another's records. Guests
# are recognisable by their reserved e-mail domain and are purged after a day.
DEMO_EMAIL_DOMAIN = "demo.krushimitra.local"
DEMO_TTL_HOURS = 24


def is_demo_user(user):
    return bool(user) and str(user.get("email", "")).endswith("@" + DEMO_EMAIL_DOMAIN)


def create_demo_user():
    token = secrets.token_hex(6)
    result = register_user(
        name="Demo Farmer", email=f"guest-{token}@{DEMO_EMAIL_DOMAIN}", password=secrets.token_urlsafe(24),
        location="Belagavi, Karnataka", farm_size_acres=2.5, soil_type="Black (Regur)",
        preferred_language="en", role="farmer")
    if not result["success"]:
        return None
    return get_user_by_id(result["user_id"])


def purge_stale_demo_users(extra_cleanup=None):
    """Delete guest accounts (and all their data) older than DEMO_TTL_HOURS."""
    cutoff = datetime.utcnow() - timedelta(hours=DEMO_TTL_HOURS)
    conn = get_db()
    rows = conn.execute("SELECT id, created_at FROM users WHERE email LIKE ?",
                        (f"%@{DEMO_EMAIL_DOMAIN}",)).fetchall()
    conn.close()
    removed = 0
    for r in rows:
        created = r["created_at"]
        if isinstance(created, str):
            try:
                created = datetime.strptime(created[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        if created and created < cutoff:
            if extra_cleanup:
                extra_cleanup(r["id"])
            delete_user(r["id"])
            removed += 1
    return removed
