import json
import logging
import os
import re
import secrets
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

import auth
import db_compat
import farm_records
from admin_tools import (add_custom_disease, add_news, delete_custom_disease, delete_news,
                          get_admin_stats, get_custom_diseases, get_news)
from crop_calendar import get_crop_calendar
from dashboard_service import DashboardService
from decision_engine import DecisionEngine, PlanInputError, fetch_recent_monthly_rainfall
from disease_reference import DISEASE_REFERENCE, list_symptoms_for_crop, match_disease
from fertilizer_recommendation import get_fertilizer_plan
from gemini_client import client_from_env
from knowledge_base import check_eligibility, get_knowledge_base
from location_service import LocationService
from market_service import MarketService
from ml_models import CropRecommendationModel, WaterManagementAdvisor
from notifications import build_notifications
from profit_estimation import estimate_profit
from rag_service import RagError, RagService
from regional_crops import get_common_crops, is_grown_in_state
import vision_service
from soil_health import analyze_soil
from weather_service import WeatherService
from yield_model import YieldModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_env_path = os.path.join(BASE_DIR, ".env")
# Explicit path (not just load_dotenv()'s auto-discovery) so there's no
# ambiguity about which .env gets read regardless of the working directory
# the app happens to be launched from.
load_dotenv(_env_path)

# Startup diagnostic: prints exactly what got picked up from .env, without
# ever printing the password itself. If this doesn't match what you put in
# .env, the file either isn't at BASE_DIR/.env, has a parsing problem
# (stray characters, e.g. an accidentally-pasted markdown code-fence line),
# or you're looking at output from before your last edit — env vars are
# only read once, at process startup, so an edit needs a restart to apply.
if os.path.exists(_env_path):
    _smtp_status = {k: bool(os.getenv(k)) for k in
                     ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD")}
    print(f"[app] Loaded .env from {_env_path}")
    print(f"[app] SMTP env vars detected (True = present, value not shown): {_smtp_status}")
    if not all(_smtp_status.values()):
        _missing = [k for k, present in _smtp_status.items() if not present]
        print(f"[app] SMTP not fully configured — missing/empty: {', '.join(_missing)}. "
              f"Password-reset emails can't be sent until this is fixed "
              f"(run: python scripts/test_email.py you@example.com for a diagnosis).")
else:
    print(f"[app] No .env file found at {_env_path} — the app will run with defaults "
          f"(no SMTP, no Gemini chat, no live market API). Copy .env.example to .env to configure these.")

app = Flask(__name__)
logger = logging.getLogger("krushimitra")

# Largest request body accepted anywhere (the biggest legitimate upload is a
# 12 MB knowledge-base PDF). Flask answers 413 for anything larger.
app.config["MAX_CONTENT_LENGTH"] = 14 * 1024 * 1024

# Every static asset (CSS/JS) is served with a cache-busting ?v=<mtime>
# query string via the asset_url() Jinja helper below — see there for why.
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0


@app.template_global()
def asset_url(path):
    """url_for('static', filename=path) plus a ?v=<mtime> query string, so
    a browser that already cached an old copy of style.css/script.js is
    forced to fetch the new one the moment the file actually changes —
    instead of silently keeping the stale version until a hard refresh.
    Static files don't re-render like Jinja templates do on every request;
    without this, "I applied your fix but the page still looks old" is a
    real, recurring failure mode, not a one-off."""
    full_path = os.path.join(BASE_DIR, "static", path)
    try:
        version = int(os.path.getmtime(full_path))
    except OSError:
        version = 0
    return f"{url_for('static', filename=path)}?v={version}"


# SECRET_KEY: use the env var if set (required for production — without a
# stable key, sessions break on every restart/redeploy and, worse, on a
# multi-process deploy each worker would sign with a different key). If it
# isn't set, generate a random one for this process rather than falling
# back to a fixed, publicly-known default — a hardcoded secret in an
# open-source repo is a real session-forgery hole the moment anyone
# deploys without configuring their own.
_secret_key = os.getenv("SECRET_KEY")
if not _secret_key:
    _secret_key = secrets.token_hex(32)
    print(
        "[app] WARNING: SECRET_KEY not set in .env — using a random key for this process. "
        "Sessions will NOT survive a restart, and this is unsafe for any multi-worker/production "
        "deployment. Set SECRET_KEY in .env (any long random string) before deploying."
    )
app.secret_key = _secret_key

# Session cookie hardening. SESSION_COOKIE_SECURE is opt-in via env rather
# than always-on, because always-on would silently break login on a local
# plain-http dev server; set COOKIE_SECURE=1 once this runs behind HTTPS.
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "0") == "1",
)

# CORS: only allow the configured origin(s) to make credentialed requests,
# rather than reflecting any origin (the effective behavior of enabling
# supports_credentials with no allowlist) — that combination lets any
# website read authenticated responses from a logged-in user's browser.
# Defaults to common local dev origins; set ALLOWED_ORIGINS in .env
# (comma-separated) for anything else, including your real deployed domain.
_allowed_origins = [o.strip() for o in os.getenv(
    "ALLOWED_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000"
).split(",") if o.strip()]
CORS(app, supports_credentials=True, origins=_allowed_origins)

# Rate limiting: protects login/register from brute-force and credential
# stuffing, and protects /api/chat from one user burning through the whole
# app's (usually free-tier, shared) Gemini quota. In-memory storage is
# fine for a single-process dev/small deployment; point REDIS_URL at a
# real store for multi-worker production so limits are shared correctly.
limiter = Limiter(
    get_remote_address, app=app, storage_uri=os.getenv("REDIS_URL", "memory://"),
    default_limits=[], strategy="fixed-window",
)

DB_PATH = os.getenv("DATABASE_PATH") or os.path.join(BASE_DIR, "krushi.db")

# Services -- initialised once at startup. All three ML models train on
# their real bundled datasets the first time the app boots (a few seconds).
crop_model = CropRecommendationModel()
yield_model = YieldModel()
water_advisor = WaterManagementAdvisor()
weather_service = WeatherService(os.getenv("OPENWEATHER_API_KEY"))
market_service = MarketService(os.getenv("MARKET_API_KEY"))
location_service = LocationService()
gemini = client_from_env()

with open(os.path.join(BASE_DIR, "data", "states_districts.json"), encoding="utf-8") as f:
    STATES_DISTRICTS = json.load(f)

SOIL_TYPES = ["Alluvial", "Black (Regur)", "Red", "Laterite", "Arid / Desert",
              "Mountain / Forest", "Saline / Alkaline", "Peaty / Marshy"]
SEASONS = ["Kharif", "Rabi", "Summer", "Whole Year", "Winter", "Autumn"]

# Uploaded leaf photos live OUTSIDE static/ so they are never publicly
# reachable by URL; /api/uploads/<name> serves them to their owner only.
UPLOAD_DIR = os.getenv("UPLOAD_DIR") or os.path.join(BASE_DIR, "private_uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

KNOWN_CROPS = set(crop_model.crop_info) | set(yield_model.get_model_info()["covered_crops"])
try:
    from regional_crops import ALL_CROPS as _ALL_DATASET_CROPS
    KNOWN_CROPS |= {c.lower() for c in _ALL_DATASET_CROPS}
except Exception:
    pass
from fertilizer_recommendation import CROP_FERTILIZER_PLAN as _FERT
from crop_calendar import CROP_DURATION_DAYS as _DUR
KNOWN_CROPS |= set(_FERT) | set(_DUR)

rag = RagService(gemini, auth.get_db, BASE_DIR)
engine = DecisionEngine(crop_model, yield_model, water_advisor, weather_service, market_service, gemini,
                        auth.get_db, valid_crops=KNOWN_CROPS)
dashboards = DashboardService(auth.get_db, weather_service, water_advisor, market_service, engine)


class InputError(ValueError):
    """Invalid user input - the message is safe to show to the user."""


def _server_error(e):
    """Never leak internals (file paths, SQL, library messages) to the browser.
    Bad input -> 400 with a friendly message; anything else is logged in full
    on the server and answered with a generic 500."""
    if isinstance(e, (InputError, PlanInputError)):
        return jsonify({"success": False, "error": str(e)}), 400
    if isinstance(e, (ValueError, TypeError, KeyError)):
        logger.warning("bad input: %r", e)
        return jsonify({"success": False, "error": "Some of the values you entered are missing or invalid - "
                                                   "please check them and try again."}), 400
    logger.exception("unhandled error in %s", request.path)
    return jsonify({"success": False, "error": "Something went wrong on our side. Please try again."}), 500


def _num(data, key, default=None, lo=None, hi=None, label=None):
    """Read a bounded float from a JSON body; raises InputError with a clear message."""
    raw = data.get(key, default)
    label = label or key
    if raw is None or raw == "":
        if default is None:
            raise InputError(f"{label} is required.")
        raw = default
    try:
        v = float(raw)
    except (TypeError, ValueError):
        raise InputError(f"{label} must be a number.")
    if v != v or v in (float("inf"), float("-inf")):
        raise InputError(f"{label} must be a real number.")
    if lo is not None and v < lo or hi is not None and v > hi:
        raise InputError(f"{label} must be between {lo:g} and {hi:g}.")
    return v


def _json_body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


@app.after_request
def security_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(self), microphone=()")
    if request.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


def _wants_json():
    return request.path.startswith("/api/")


@app.errorhandler(413)
def too_large(e):
    return jsonify({"success": False, "error": "That upload is too large (limit 14 MB)."}), 413


@app.errorhandler(404)
def not_found(e):
    if _wants_json():
        return jsonify({"success": False, "error": "Not found."}), 404
    return render_template("error.html", code=404, title="Page not found",
                           message="That page doesn't exist."), 404


@app.errorhandler(429)
def rate_limited(e):
    return jsonify({"success": False, "error": "Too many requests - please wait a little and try again."}), 429


@app.errorhandler(500)
def server_error_page(e):
    if _wants_json():
        return jsonify({"success": False, "error": "Something went wrong on our side. Please try again."}), 500
    return render_template("error.html", code=500, title="Something went wrong",
                           message="We hit an unexpected problem. Please go back and try again."), 500


@app.context_processor
def inject_user():
    # Every template can reference `user` directly (e.g. base.html's nav),
    # without each view function having to pass it in explicitly.
    u = auth.current_user()
    return {"user": u, "is_demo": auth.is_demo_user(u)}


def _cleanup_user_files(user_id):
    """Remove a user's uploaded photos from disk and their private knowledge docs."""
    try:
        conn = db_compat.get_connection(DB_PATH)
        rows = conn.execute("SELECT filename FROM user_uploads WHERE user_id = ?", (user_id,)).fetchall()
        conn.close()
        for r in rows:
            try:
                os.remove(os.path.join(UPLOAD_DIR, r["filename"]))
            except OSError:
                pass
        rag.delete_user_documents(user_id)
    except Exception as e:
        print(f"[app] file cleanup failed for user {user_id}: {e}")


def init_db():
    # If DATABASE_PATH points at a mounted volume directory that doesn't
    # exist yet on first boot (e.g. a fresh Railway volume), create it
    # rather than fail with a cryptic sqlite3 "unable to open database" —
    # only relevant for SQLite; Postgres (DATABASE_URL) ignores DB_PATH
    # entirely.
    if not db_compat.USING_POSTGRES:
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = db_compat.get_connection(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            location TEXT, state TEXT, district TEXT, season TEXT,
            n REAL, p REAL, k REAL, ph REAL,
            temperature REAL, humidity REAL, rainfall REAL,
            top_crop TEXT, confidence REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS user_uploads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            mime TEXT,
            kind TEXT DEFAULT 'leaf_photo',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()
    auth.init_auth_tables()
    farm_records.init_farm_tables()
    engine.init_tables()
    rag.init_tables()
    try:
        rag.ensure_seeded()
    except Exception as e:  # the app must still boot if the knowledge base can't be built
        print(f"[app] knowledge base seeding failed: {e}")
    try:
        auth.purge_stale_demo_users(extra_cleanup=_cleanup_user_files)
    except Exception as e:
        print(f"[app] demo cleanup skipped: {e}")


def log_recommendation(payload, top_result, user_id=None):
    try:
        conn = db_compat.get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO recommendations
               (user_id, location, state, district, season, n, p, k, ph,
                temperature, humidity, rainfall, top_crop, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id, payload.get("location"), payload.get("state"), payload.get("district"),
                payload.get("season"), payload.get("n"), payload.get("p"), payload.get("k"),
                payload.get("ph"), payload.get("temperature"), payload.get("humidity"),
                payload.get("rainfall"), top_result.get("crop"), top_result.get("confidence"),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[app] could not log recommendation: {e}")


# Runs at import time, not just inside `if __name__ == "__main__"` —
# gunicorn (used in production, see Procfile) imports this module and
# calls the `app` object directly, so it never executes that block.
# Without this being here, unconditionally, the database tables are
# never created in production and every query 500s with "relation does
# not exist" — found exactly that way deploying this to Render.
init_db()


# ========================================================================= #
# Pages — every feature lives on its own route now, and every page except
# /login requires a signed-in session (auth.page_login_required redirects
# to /login instead of the app.py silently rendering nothing).
# ========================================================================= #
@app.route("/")
def root():
    """Public landing page. Signed-in farmers get an 'open dashboard' button;
    visitors get Sign in / Register / Try the demo."""
    info = crop_model.get_model_info()
    yinfo = yield_model.get_model_info()
    stats = {"samples": info.get("training_samples"), "crops": info.get("crop_classes"),
             "accuracy": info.get("test_accuracy_pct"),
             "yield_crops": len(yinfo.get("covered_crops", []))}
    return render_template("landing.html", stats=stats)


@app.route("/demo")
@limiter.limit("30 per hour")
def demo_page():
    """One-click guest access for judges and first-time visitors: creates an
    isolated demo account, signs it in and drops the visitor on the dashboard."""
    user = _start_demo_session()
    if not user:
        return redirect(url_for("login_page"))
    return redirect(url_for("dashboard_page"))


@app.route("/login")
def login_page():
    if session.get("user_id"):
        return redirect(url_for("dashboard_page"))
    return render_template("login.html")


@app.route("/home")
@auth.page_login_required
def home_page():
    return render_template("home.html")


@app.route("/profile")
@auth.page_login_required
def profile_page():
    return render_template("profile.html")


@app.route("/recommend")
@auth.page_login_required
def recommend_page():
    return render_template("recommend.html")


@app.route("/soil")
@auth.page_login_required
def soil_page():
    return render_template("soil.html")


@app.route("/yield")
@auth.page_login_required
def yield_page():
    return render_template("yield.html")


@app.route("/market")
@auth.page_login_required
def market_page():
    return render_template("market.html")


@app.route("/fertilizer")
@auth.page_login_required
def fertilizer_page():
    return render_template("fertilizer.html")


@app.route("/profit")
@auth.page_login_required
def profit_page():
    return render_template("profit.html")


@app.route("/disease")
@auth.page_login_required
def disease_page():
    return render_template("disease.html")


@app.route("/water")
@auth.page_login_required
def water_page():
    return render_template("water.html")


@app.route("/calendar")
@auth.page_login_required
def calendar_page():
    return render_template("calendar.html")


@app.route("/dashboard")
@auth.page_login_required
def dashboard_page():
    return render_template("dashboard.html")


@app.route("/map")
@auth.page_login_required
def map_page():
    return render_template("map.html")


@app.route("/knowledge")
@auth.page_login_required
def knowledge_page():
    return render_template("knowledge.html")


@app.route("/about")
@auth.page_login_required
def about_page():
    return render_template("about.html")


@app.route("/assistant")
@auth.page_login_required
def assistant_page():
    return render_template("assistant.html")


@app.route("/chat")
@auth.page_login_required
def chat_page():
    return redirect(url_for("assistant_page"))


@app.route("/decision-engine")
@auth.page_login_required
def decision_page():
    return render_template("decision.html")


@app.route("/records")
@auth.page_login_required
def records_page():
    return render_template("records.html")


@app.route("/analytics")
@auth.page_login_required
def analytics_page():
    return render_template("analytics.html")


@app.route("/admin")
@auth.page_admin_required
def admin_page():
    return render_template("admin.html")


# ========================================================================= #
# Core data endpoints (still require login — see note above)
# ========================================================================= #
@app.route("/api/model-info")
@auth.login_required
def model_info():
    return jsonify({
        "success": True,
        "crop_model": crop_model.get_model_info(),
        "yield_model": yield_model.get_model_info(),
        "market_model": market_service.get_model_info(),
    })


@app.route("/api/reference-data")
def reference_data():
    return jsonify({
        "success": True,
        "states": sorted(STATES_DISTRICTS.keys()),
        "districts_by_state": STATES_DISTRICTS,
        "soil_types": SOIL_TYPES,
        "seasons": SEASONS,
        "crops": sorted(c for c in KNOWN_CROPS if re.fullmatch(r"[a-z][a-z ]{2,24}", c)),
        "languages": [
            {"code": "en", "label": "English"}, {"code": "hi", "label": "Hindi"},
            {"code": "kn", "label": "Kannada"}, {"code": "mr", "label": "Marathi"},
            {"code": "ta", "label": "Tamil"}, {"code": "te", "label": "Telugu"},
        ],
    })


@app.route("/api/regional-crops")
@auth.login_required
def regional_crops_route():
    """Real crops grown in a given state, from government production
    records — covers 49 real crops (sugarcane, tobacco, jowar, bajra,
    ragi, groundnut, wheat, onion, and more), not just the 22 the
    N/P/K soil-based model knows. See regional_crops.py for why this is
    a real ranked list, not a trained confidence score."""
    state = request.args.get("state", "")
    return jsonify({"success": True, "result": get_common_crops(state, top_n=int(request.args.get("top_n", 15)))})


# ========================================================================= #
# Auth (these stay public — they're how you get a session in the first place)
# ========================================================================= #
@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("8 per hour")
def register():
    data = _json_body()
    name, email, password = str(data.get("name", "")).strip(), str(data.get("email", "")).strip(), data.get("password", "")
    if not isinstance(password, str):
        password = ""
    if not name or not email or not password:
        return jsonify({"success": False, "error": "name, email and password are required."}), 400
    if len(password) < 8:
        return jsonify({"success": False, "error": "Password must be at least 8 characters."}), 400
    if len(password) > 128 or len(name) > 80 or len(email) > 254:
        return jsonify({"success": False, "error": "Name, email or password is too long."}), 400
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return jsonify({"success": False, "error": "Please enter a valid email address."}), 400
    if email.lower().endswith("@" + auth.DEMO_EMAIL_DOMAIN):
        return jsonify({"success": False, "error": "That email domain is reserved."}), 400
    farm = data.get("farm_size_acres")
    if farm not in (None, ""):
        try:
            if not (0 < float(farm) <= 100000):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Farm size must be a number of acres."}), 400
    if data.get("location") and len(str(data["location"])) > 120:
        return jsonify({"success": False, "error": "Location is too long."}), 400

    result = auth.register_user(
        name=name, email=email, password=password,
        location=data.get("location"), farm_size_acres=data.get("farm_size_acres"),
        soil_type=data.get("soil_type"), preferred_language=data.get("preferred_language", "en"),
        role="farmer",  # public registration can NEVER self-assign a role — admin accounts are
                        # created only via scripts/create_admin.py (see README), run by whoever
                        # controls the server, not by anyone who can hit this API.
    )
    if not result["success"]:
        return jsonify(result), 409

    user = auth.get_user_by_id(result["user_id"])
    auth.login_user_session(user)
    email_result = auth.send_welcome_email(user)
    return jsonify({
        "success": True, "user": auth.public_user_dict(user),
        "welcome_email_sent": email_result["sent"],
    })


def _seed_demo_data(user):
    """Give a fresh demo account a believable starting point. Soil analysis and
    the yield figure are real outputs of the app's own modules; the money
    entries are sample records, and every one is labelled as such."""
    uid = user["id"]
    note = "Demo sample record"
    for category, amount in (("seeds", 4200), ("fertilizer", 5600), ("labour", 8000),
                             ("pesticides", 1800), ("water", 2200)):
        farm_records.add_expense(uid, category, amount, "maize", note)
    farm_records.add_income(uid, 38000, "maize", note)
    soil = analyze_soil(120, 18, 150, 6.8, 0.6)
    farm_records.log_soil_health(uid, soil["soil_health_score"], soil["nitrogen_status"],
                                 soil["phosphorus_status"], soil["potassium_status"])
    y = yield_model.get_expected_yield("maize", state="Karnataka", season="Kharif")
    if y.get("covered"):
        farm_records.log_yield_prediction(uid, "maize", 2.5, round(y["predicted_yield_tonnes_per_ha"] * 0.404686 * 2.5, 2),
                                          y["test_r2"])
    sowing = date.today() - timedelta(days=20)
    profile = water_advisor.irrigation_profiles.get("maize", water_advisor.default_profile)
    cal = get_crop_calendar("maize", sowing, irrigation_interval_days=profile["interval_days"])
    if cal.get("covered") and cal.get("type") == "annual":
        farm_records.save_crop_plan(uid, "maize", cal["sowing_date"], cal["expected_harvest_date"],
                                    json.dumps(cal["events"]))


def _start_demo_session():
    try:
        user = auth.create_demo_user()
        if not user:
            return None
        _seed_demo_data(user)
    except Exception:
        logger.exception("could not create demo account")
        return None
    session.clear()
    auth.login_user_session(user)
    return user


@app.route("/api/auth/demo", methods=["POST"])
@limiter.limit("30 per hour")
def demo_login():
    user = _start_demo_session()
    if not user:
        return jsonify({"success": False, "error": "Could not start the demo right now. Please try again."}), 500
    return jsonify({"success": True, "user": auth.public_user_dict(user), "redirect": url_for("dashboard_page")})


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("15 per minute")
def login():
    data = request.json or {}
    user = auth.authenticate(data.get("email", ""), data.get("password", ""))
    if not user:
        return jsonify({"success": False, "error": "Invalid email or password."}), 401
    auth.login_user_session(user)
    return jsonify({"success": True, "user": auth.public_user_dict(user)})


@app.route("/api/auth/logout", methods=["POST"])
def logout():
    auth.logout_user_session()
    return jsonify({"success": True})


@app.route("/api/auth/me")
def me():
    user = auth.current_user()
    return jsonify({"success": True, "user": auth.public_user_dict(user)})


@app.route("/api/auth/profile", methods=["PUT"])
@auth.login_required
def update_profile():
    data = _json_body()
    name = str(data["name"]).strip() if data.get("name") else None
    location = str(data["location"]).strip() if data.get("location") else None
    if (name and len(name) > 80) or (location and len(location) > 120):
        return jsonify({"success": False, "error": "Name or location is too long."}), 400
    farm = data.get("farm_size_acres")
    if farm in ("", None):
        farm = None
    else:
        try:
            farm = float(farm)
            if not (0 < farm <= 100000):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "error": "Farm size must be a number of acres."}), 400
    lang = data.get("preferred_language")
    if lang and lang not in ("en", "hi", "kn", "mr", "ta", "te"):
        return jsonify({"success": False, "error": "Unsupported language."}), 400
    auth.update_profile(
        session["user_id"], name=name, location=location, farm_size_acres=farm,
        soil_type=(str(data["soil_type"])[:40] if data.get("soil_type") else None),
        preferred_language=lang,
    )
    user = auth.get_user_by_id(session["user_id"])
    return jsonify({"success": True, "user": auth.public_user_dict(user)})


@app.route("/api/auth/delete-account", methods=["POST"])
@auth.login_required
def delete_account():
    data = _json_body()
    user = auth.get_user_by_id(session["user_id"])
    if auth.is_demo_user(user):
        return jsonify({"success": False, "error": "Demo accounts are deleted automatically after 24 hours - "
                                                   "just log out when you're done."}), 400
    if not check_password_hash(user["password_hash"], str(data.get("password", ""))):
        return jsonify({"success": False, "error": "Incorrect password."}), 401

    _cleanup_user_files(user["id"])
    auth.delete_user(user["id"])
    auth.logout_user_session()
    return jsonify({"success": True})


@app.route("/api/auth/email-status")
def email_status():
    return jsonify({"success": True, **auth.email_config_status()})


@app.route("/api/auth/forgot-password", methods=["POST"])
@limiter.limit("5 per hour")
def forgot_password():
    data = request.json or {}
    email = data.get("email", "")
    code, user = auth.create_password_reset(email)
    if not code:
        # Don't reveal whether the email exists -- standard practice.
        return jsonify({"success": True, "message": "If that email has an account, a code has been sent to it."})

    if auth.is_demo_user(user):
        return jsonify({"success": True, "message": "If that email has an account, a code has been sent to it."})
    result = auth.send_email(
        user["email"], "Your KrushiMitra AI password reset code",
        f"Hi {user['name']},\n\nYour KrushiMitra AI password reset code is: {code}\n\n"
        f"This code expires in {auth.RESET_TOKEN_TTL_MINUTES} minutes and can only be used once.\n\n"
        f"If you didn't request this, you can ignore this email — your password won't change.",
    )

    if result["sent"]:
        return jsonify({"success": True, "email_sent": True,
                         "message": f"A 6-digit code has been sent to {user['email']}. Enter it below."})

    # The email could not be sent. Handing the reset code straight back in the
    # HTTP response would let ANYONE reset ANY account's password just by
    # knowing the email address, so that only happens when the operator has
    # explicitly opted into dev mode (ALLOW_DEV_RESET_CODES=1) - never by default.
    logger.warning("password-reset email not sent (%s)", result.get("reason"))
    if os.getenv("ALLOW_DEV_RESET_CODES", "0") == "1":
        return jsonify({
            "success": True, "email_sent": False,
            "message": "DEV MODE: email isn't configured/working, so here is the code directly.",
            "reset_token": code, "expires_in_minutes": auth.RESET_TOKEN_TTL_MINUTES,
        })
    return jsonify({"success": True, "message": "If that email has an account, a code has been sent to it."})


@app.route("/api/auth/verify-reset-code", methods=["POST"])
@limiter.limit("10 per hour")
def verify_reset_code():
    data = request.json or {}
    ok, error = auth.verify_reset_code(data.get("email", ""), data.get("token", ""))
    if not ok:
        return jsonify({"success": False, "error": error}), 400
    return jsonify({"success": True})


@app.route("/api/auth/reset-password", methods=["POST"])
@limiter.limit("10 per hour")
def reset_password_route():
    data = request.json or {}
    ok, error = auth.reset_password(data.get("email", ""), data.get("token", ""), data.get("new_password", ""))
    if not ok:
        return jsonify({"success": False, "error": error}), 400
    return jsonify({"success": True})


@app.route("/api/admin/users")
@auth.admin_required
def admin_users():
    conn = auth.get_db()
    rows = conn.execute("SELECT id, name, email, location, role, created_at FROM users").fetchall()
    conn.close()
    conn2 = db_compat.get_connection(DB_PATH)
    total_recs = conn2.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    conn2.close()
    return jsonify({
        "success": True,
        "users": [dict(r) for r in rows],
        "stats": {"total_users": len(rows), "total_recommendations_generated": total_recs},
    })


@app.route("/api/admin/stats")
@auth.admin_required
def admin_stats():
    return jsonify({"success": True, "stats": get_admin_stats()})


@app.route("/api/admin/crops")
@auth.admin_required
def admin_crops():
    """Read-only view of the crop model's training coverage — 'managing
    crops' here means seeing what the model actually knows, not editing
    live ML training data through a form."""
    return jsonify({
        "success": True,
        "crop_model": crop_model.get_model_info(),
        "yield_model_crops": yield_model.get_model_info()["covered_crops"],
        "market_model_crops": market_service.get_model_info()["covered_crops"],
    })


@app.route("/api/admin/weather-status")
@auth.admin_required
def admin_weather_status():
    """A live diagnostic call so the admin can see the weather pipeline is
    actually working, not a static status flag."""
    try:
        sample = weather_service.get_current_weather("Delhi")
        return jsonify({"success": True, "sample": sample,
                         "openweather_key_configured": bool(os.getenv("OPENWEATHER_API_KEY"))})
    except Exception as e:
        return _server_error(e)


@app.route("/api/admin/news", methods=["GET", "POST"])
@auth.admin_required
def admin_news():
    if request.method == "POST":
        data = request.json or {}
        add_news(session["user_id"], data.get("title", ""), data.get("body", ""))
        return jsonify({"success": True})
    return jsonify({"success": True, "news": get_news()})


@app.route("/api/admin/news/<int:news_id>", methods=["DELETE"])
@auth.admin_required
def admin_delete_news(news_id):
    delete_news(news_id)
    return jsonify({"success": True})


@app.route("/api/news")
@auth.login_required
def public_news():
    """Same announcements, read-only, for the farmer-facing home page."""
    return jsonify({"success": True, "news": get_news(limit=5)})


@app.route("/api/admin/disease-database", methods=["GET", "POST"])
@auth.admin_required
def admin_disease_database():
    if request.method == "POST":
        data = request.json or {}
        add_custom_disease(
            session["user_id"], data.get("crop", ""), data.get("disease", ""),
            data.get("symptoms", []), data.get("cause", ""), data.get("treatment", ""),
            data.get("recommended_fungicide", ""),
        )
        return jsonify({"success": True})
    return jsonify({"success": True, "static_reference": DISEASE_REFERENCE,
                     "custom_entries": get_custom_diseases()})


@app.route("/api/admin/disease-database/<int:entry_id>", methods=["DELETE"])
@auth.admin_required
def admin_delete_disease(entry_id):
    delete_custom_disease(entry_id)
    return jsonify({"success": True})


# ========================================================================= #
# Location
# ========================================================================= #
@app.route("/api/reverse-geocode")
@auth.login_required
def reverse_geocode():
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "lat and lon query params are required"}), 400

    result = location_service.reverse_geocode(lat, lon)
    notes = location_service.get_region_notes(result["location_string"])
    return jsonify({"success": True, **result, "region_notes": notes})


@app.route("/api/detect-location")
@auth.login_required
def detect_location():
    try:
        loc = location_service.get_location_from_ip()
        if loc:
            notes = location_service.get_region_notes(loc["location_string"])
            return jsonify({"success": True, "location": loc["location_string"],
                             "lat": loc["lat"], "lon": loc["lon"], "region_notes": notes,
                             "accuracy_warning": "Estimated from your network address — this can be "
                                                  "off by a large distance, especially on mobile data. "
                                                  "Allow location access for an accurate GPS-based result."})
        return jsonify({"success": False, "error": "Could not detect location automatically. "
                                                     "Please enter it manually."})
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Weather
# ========================================================================= #
def _weather_payload(current, forecast):
    return {"success": True, "current": current, "forecast": forecast,
            "alerts": weather_service.get_alerts(forecast)}


@app.route("/api/weather/<location>")
@auth.login_required
def get_weather(location):
    try:
        current = weather_service.get_current_weather(location)
        forecast = weather_service.get_forecast(location)
        return jsonify(_weather_payload(current, forecast))
    except Exception as e:
        return _server_error(e)


@app.route("/api/weather-by-coords")
@auth.login_required
def get_weather_by_coords():
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
        label = request.args.get("label")
        current = weather_service.get_current_weather_by_coords(lat, lon, label)
        forecast = weather_service.get_forecast_by_coords(lat, lon)
        return jsonify(_weather_payload(current, forecast))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "lat and lon query params are required"}), 400
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Crop recommendation
# ========================================================================= #
@app.route("/api/recommend-crops", methods=["POST"])
@auth.login_required
def recommend_crops():
    try:
        data = _json_body()
        location = str(data.get("location", ""))[:120]
        state = str(data["state"])[:60] if data.get("state") else None
        district = str(data["district"])[:60] if data.get("district") else None
        season = str(data["season"])[:20] if data.get("season") else None
        lat, lon = data.get("lat"), data.get("lon")
        if lat is not None and lon is not None:
            lat = _num({"v": lat}, "v", lo=-90, hi=90, label="Latitude")
            lon = _num({"v": lon}, "v", lo=-180, hi=180, label="Longitude")

        n = _num(data, "n", 50, 0, 1000, "Nitrogen")
        p = _num(data, "p", 50, 0, 1000, "Phosphorus")
        k = _num(data, "k", 50, 0, 2000, "Potassium")
        ph = _num(data, "ph", 6.5, 3, 10, "Soil pH")

        temperature = data.get("temperature")
        humidity = data.get("humidity")
        rainfall = data.get("rainfall")
        rainfall_is_monthly = False
        if rainfall in ("", None):
            rainfall = None

        weather_data = None
        if rainfall is None and lat is not None and lon is not None:
            # A single hour's precipitation is not what the crop model was trained on
            # (monthly-scale rainfall, ~20-300 mm). Use real observed rainfall for the
            # last 90 days at this location instead.
            observed = fetch_recent_monthly_rainfall(float(lat), float(lon))
            if observed is not None:
                rainfall, rainfall_is_monthly = observed, True
        if temperature is None or humidity is None or rainfall is None:
            if lat is not None and lon is not None:
                weather_data = weather_service.get_current_weather_by_coords(
                    float(lat), float(lon), label=location or None
                )
            else:
                weather_data = weather_service.get_current_weather(location or state or "Delhi")
            temperature = temperature if temperature is not None else weather_data.get("temperature", 25)
            humidity = humidity if humidity is not None else weather_data.get("humidity", 60)
            rainfall = rainfall if rainfall is not None else weather_data.get("rainfall", 100)

        rainfall_mm = float(rainfall) if (rainfall_is_monthly or float(rainfall) > 5) else float(rainfall) * 30

        # The crop model itself has NO location input — it's trained purely
        # on N/P/K/temperature/humidity/pH/rainfall (see ml_models.py), so
        # two farmers in different states with the same soil numbers would
        # otherwise get an identical list regardless of state. When a state
        # is given, pull more candidates than we need and re-rank using
        # real historical state-level crop production records
        # (regional_crops.py), instead of leaving state purely decorative.
        fetch_n = 12 if state else 6
        recommendations = crop_model.recommend_crops(
            n=n, p=p, k=k, temperature=float(temperature), humidity=float(humidity),
            ph=ph, rainfall=rainfall_mm, top_n=fetch_n,
        )

        for rec in recommendations:
            rec["yield_estimate"] = yield_model.get_expected_yield(
                rec["crop"], state=state, season=season, rainfall=rainfall_mm, temperature=float(temperature)
            )
            rec["season_match"] = (
                season is not None and season.strip().lower() in rec.get("season", "").lower()
            ) if season else None
            rec["regionally_grown"] = is_grown_in_state(rec["crop"], state) if state else None

        # market_estimate is the one network-hitting call per crop (yield
        # is a local model lookup) — run these concurrently instead of one
        # at a time, so a slow/unreachable live price API costs one wait,
        # not one wait PER recommended crop.
        with ThreadPoolExecutor(max_workers=len(recommendations)) as pool:
            market_results = pool.map(
                lambda rec: market_service.get_price_estimate(rec["crop"], state=state), recommendations
            )
        for rec, market_estimate in zip(recommendations, market_results):
            rec["market_estimate"] = market_estimate

        if state:
            # Only a CONFIRMED real match (True) gets bubbled up. None and
            # False are deliberately tied at the same tier and keep their
            # original model-confidence order — the data has real gaps
            # (e.g. Rajasthan is entirely absent from this dataset), so
            # treating "no record" as equivalent to "actively worse" would
            # bury good, high-confidence picks under a data-completeness
            # artifact rather than a real regional signal.
            tier = {True: 0, None: 1, False: 1}
            recommendations.sort(key=lambda r: tier[r["regionally_grown"]])
        recommendations = recommendations[:6]

        recommendations = _add_profitability(recommendations)

        user = auth.current_user()
        if recommendations:
            log_recommendation(
                {"location": location, "state": state, "district": district, "season": season,
                 "n": n, "p": p, "k": k, "ph": ph, "temperature": temperature, "humidity": humidity,
                 "rainfall": rainfall},
                recommendations[0], user_id=user["id"] if user else None,
            )

        return jsonify({
            "success": True,
            "recommendations": recommendations,
            "weather": weather_data,
            "model": crop_model.get_model_info(),
        })
    except Exception as e:
        return _server_error(e)


def _add_profitability(recommendations):
    """Profitability is estimated revenue potential (expected yield x
    predicted price), ranked RELATIVE to the other recommended crops in
    this same response. It's explicitly revenue, not net profit -- there's
    no real cost-of-cultivation dataset behind this app, so subtracting
    costs would mean inventing numbers. Only crops with BOTH a real yield
    estimate and a real price estimate get a rating; others say so."""
    revenues = []
    for rec in recommendations:
        yld = rec["yield_estimate"]
        mkt = rec["market_estimate"]
        if yld.get("covered") and mkt.get("covered"):
            revenue_per_ha = yld["predicted_yield_tonnes_per_ha"] * 10 * mkt["predicted_modal_price"]
            rec["_revenue_per_ha_rs"] = revenue_per_ha
            revenues.append(revenue_per_ha)
        else:
            rec["_revenue_per_ha_rs"] = None

    if len(revenues) >= 2:
        sorted_rev = sorted(revenues, reverse=True)
        hi_cut = sorted_rev[max(0, len(sorted_rev) // 3 - 1)]
        lo_cut = sorted_rev[min(len(sorted_rev) - 1, (2 * len(sorted_rev)) // 3)]
        for rec in recommendations:
            rev = rec["_revenue_per_ha_rs"]
            if rev is None:
                rec["profitability"] = {"covered": False,
                                         "message": "Needs both a real yield estimate and a real price "
                                                     "estimate for this crop — not available for all crops yet."}
            else:
                rating = "High" if rev >= hi_cut else ("Low" if rev <= lo_cut else "Medium")
                rec["profitability"] = {"covered": True, "rating": rating,
                                         "estimated_revenue_per_ha_rs": round(rev, 0),
                                         "basis": "expected yield x predicted price (revenue, not net profit — "
                                                   "cultivation costs are not modeled)"}
        for rec in recommendations:
            rec.pop("_revenue_per_ha_rs", None)
    else:
        for rec in recommendations:
            rec["profitability"] = {"covered": False,
                                     "message": "Not enough recommended crops with both real yield and "
                                                 "price data to compare profitability."}
            rec.pop("_revenue_per_ha_rs", None)
    return recommendations


# ========================================================================= #
# Soil health
# ========================================================================= #
@app.route("/api/soil-health", methods=["POST"])
@auth.login_required
def soil_health():
    try:
        data = _json_body()
        result = analyze_soil(
            n=_num(data, "n", 0, 0, 2000, "Nitrogen"), p=_num(data, "p", 0, 0, 1000, "Phosphorus"),
            k=_num(data, "k", 0, 0, 3000, "Potassium"), ph=_num(data, "ph", 6.5, 0, 14, "Soil pH"),
            organic_carbon=(_num(data, "organic_carbon", None, 0, 20, "Organic carbon")
                            if data.get("organic_carbon") not in (None, "") else None),
        )
        user = auth.current_user()
        if user:
            farm_records.log_soil_health(user["id"], result["soil_health_score"],
                                          result["nitrogen_status"], result["phosphorus_status"],
                                          result["potassium_status"])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Irrigation
# ========================================================================= #
@app.route("/api/water-management", methods=["POST"])
@auth.login_required
def water_management():
    try:
        data = request.json or {}
        crop_type = data.get("crop_type")
        soil_type = data.get("soil_type")
        location = data.get("location")
        lat, lon = data.get("lat"), data.get("lon")

        if lat is not None and lon is not None:
            weather_forecast = weather_service.get_forecast_by_coords(float(lat), float(lon))
        else:
            weather_forecast = weather_service.get_forecast(location or "Delhi")

        advice = water_advisor.get_irrigation_advice(
            crop_type=crop_type, soil_type=soil_type, weather_forecast=weather_forecast
        )
        summary = _irrigation_summary(advice["irrigation_schedule"])
        user = auth.current_user()
        if user:
            total_mm = sum(d["water_amount_mm"] for d in advice["irrigation_schedule"])
            farm_records.log_water_usage(user["id"], crop_type, round(total_mm, 1))
        return jsonify({"success": True, "advice": advice, "forecast": weather_forecast,
                         "summary": summary,
                         "alerts": weather_service.get_alerts(weather_forecast)})
    except Exception as e:
        return _server_error(e)


def _irrigation_summary(schedule):
    """The single-line 'Water Required: 18mm / Next Irrigation: after 3
    days' headline — derived from the same schedule already computed, not
    a separate calculation."""
    next_day = next((d for d in schedule if d["irrigation_needed"]), None)
    if not next_day:
        return {"water_required_mm": 0, "next_irrigation_in_days": None,
                "message": "No irrigation needed in the next 7 days based on the forecast."}
    return {
        "water_required_mm": next_day["water_amount_mm"],
        "next_irrigation_in_days": next_day["day"],
        "message": f"{next_day['water_amount_mm']}mm required — next irrigation in "
                   f"{next_day['day']} day{'s' if next_day['day'] != 1 else ''}.",
    }


# ========================================================================= #
# Market
# ========================================================================= #
@app.route("/api/market-trends/<crop>")
@auth.login_required
def get_market_trends(crop):
    try:
        state = request.args.get("state")
        estimate = market_service.get_price_estimate(crop, state=state)
        return jsonify({"success": True, "estimate": estimate})
    except Exception as e:
        return _server_error(e)


@app.route("/api/market-prices/<crop>")
@auth.login_required
def get_market_prices(crop):
    try:
        state = request.args.get("state")
        result = market_service.get_market_prices(crop, state=state)
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


@app.route("/api/market-nearby/<crop>")
@auth.login_required
def get_market_nearby(crop):
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
        result = market_service.get_nearby_markets(crop, lat, lon)
        return jsonify({"success": True, "result": result})
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "lat and lon query params are required"}), 400
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Fertilizer recommendation
# ========================================================================= #
@app.route("/api/fertilizer-plan", methods=["POST"])
@auth.login_required
def fertilizer_plan():
    try:
        data = request.json or {}
        result = get_fertilizer_plan(str(data.get("crop", ""))[:40], area_acres=_num(data, "area_acres", 1.0, 0.05, 100000, "Area"))
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Crop calendar
# ========================================================================= #
@app.route("/api/crop-calendar", methods=["POST"])
@auth.login_required
def crop_calendar():
    try:
        data = request.json or {}
        crop = data.get("crop", "")
        sowing_date_str = data.get("sowing_date")
        sowing_date = (
            datetime.strptime(sowing_date_str, "%Y-%m-%d").date() if sowing_date_str else date.today()
        )
        profile = water_advisor.irrigation_profiles.get(
            crop.strip().lower(), water_advisor.default_profile
        )
        result = get_crop_calendar(crop, sowing_date, irrigation_interval_days=profile["interval_days"])

        user = auth.current_user()
        if user and result.get("covered") and result.get("type") == "annual":
            farm_records.save_crop_plan(
                user["id"], result["crop"], result["sowing_date"], result["expected_harvest_date"],
                json.dumps(result["events"]),
            )
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Disease reference (symptom-based, NOT image AI — see disease_reference.py)
# ========================================================================= #
@app.route("/api/disease-symptoms/<crop>")
@auth.login_required
def disease_symptoms(crop):
    return jsonify({"success": True, "result": list_symptoms_for_crop(crop, extra_diseases=get_custom_diseases(crop))})


@app.route("/api/disease-check", methods=["POST"])
@auth.login_required
def disease_check():
    try:
        data = request.json or {}
        crop = data.get("crop", "")
        result = match_disease(crop, data.get("symptoms", []), extra_diseases=get_custom_diseases(crop))

        user = auth.current_user()
        if user and result.get("covered") and result.get("matches"):
            farm_records.log_disease_check(user["id"], result["crop"], result["matches"][0]["disease"])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


@app.route("/api/disease-photo", methods=["POST"])
@auth.login_required
@limiter.limit("20 per hour")
def disease_photo():
    """Validates and stores a leaf photo privately, then - if a Gemini key is
    configured - runs a real multimodal assessment on it. Without a key the
    response says plainly that the photo was NOT analysed."""
    file = request.files.get("photo")
    if not file:
        return jsonify({"success": False, "error": "No photo file provided."}), 400
    data = file.read(vision_service.MAX_IMAGE_BYTES + 1)
    try:
        mime, ext = vision_service.sniff_image(data)
    except vision_service.ImageError as e:
        return jsonify({"success": False, "error": str(e)}), 400

    filename = vision_service.new_filename(ext)
    with open(os.path.join(UPLOAD_DIR, filename), "wb") as f:
        f.write(data)
    conn = db_compat.get_connection(DB_PATH)
    conn.execute("INSERT INTO user_uploads (user_id, filename, mime, kind) VALUES (?, ?, ?, 'leaf_photo')",
                 (session["user_id"], filename, mime))
    conn.commit()
    conn.close()

    crop = (request.form.get("crop") or "").strip().lower()[:40] or None
    try:
        analysis = vision_service.analyse_photo(gemini, data, mime, crop=crop)
    except Exception:
        logger.exception("photo analysis failed")
        analysis = {"analysed": False, "reason": "error",
                    "message": "Photo saved, but the analysis step failed unexpectedly - try again later."}
    if analysis.get("analysed") and crop and analysis["possible_conditions"]:
        top = analysis["possible_conditions"][0]
        if top["likelihood"] in ("medium", "high"):
            farm_records.log_disease_check(session["user_id"], crop, f"{top['name']} (photo, AI-assessed)")
    return jsonify({"success": True, "url": f"/api/uploads/{filename}", "analysis": analysis})


@app.route("/api/uploads/<filename>")
@auth.login_required
def serve_upload(filename):
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", filename):
        abort(404)
    conn = db_compat.get_connection(DB_PATH)
    row = conn.execute("SELECT mime FROM user_uploads WHERE filename = ? AND user_id = ?",
                       (filename, session["user_id"])).fetchone()
    conn.close()
    if not row:
        abort(404)
    resp = send_from_directory(UPLOAD_DIR, filename, mimetype=row["mime"])
    resp.headers["Cache-Control"] = "private, max-age=3600"
    return resp


# ========================================================================= #
# Standalone yield prediction
# ========================================================================= #
@app.route("/api/yield-prediction", methods=["POST"])
@auth.login_required
def yield_prediction():
    try:
        data = request.json or {}
        crop = data.get("crop", "")
        area_acres = _num(data, "area_acres", 1, 0.05, 100000, "Area")
        state = data.get("state")
        season = data.get("season")
        rainfall = data.get("rainfall")
        temperature = data.get("temperature")

        result = yield_model.get_expected_yield(
            crop, state=state, season=season,
            rainfall=float(rainfall) if rainfall not in (None, "") else None,
            temperature=float(temperature) if temperature not in (None, "") else None,
        )
        if result.get("covered"):
            area_ha = area_acres * 0.404686
            total_tonnes = round(result["predicted_yield_tonnes_per_ha"] * area_ha, 2)
            result["area_acres"] = area_acres
            result["total_expected_yield_tonnes"] = total_tonnes
            result["accuracy_pct_note"] = "This is the model's held-out R\u00b2 expressed as a " \
                                            "percentage, not classification accuracy — see README."

            user = auth.current_user()
            if user:
                farm_records.log_yield_prediction(user["id"], crop, area_acres, total_tonnes,
                                                    result["test_r2"])
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Profit estimation
# ========================================================================= #
@app.route("/api/profit-estimation", methods=["POST"])
@auth.login_required
def profit_estimation_route():
    try:
        data = request.json or {}
        crop = data.get("crop", "")
        area_acres = _num(data, "area_acres", 1, 0.05, 100000, "Area")
        state = data.get("state")
        season = data.get("season")
        if not isinstance(data.get("expenses", {}), dict):
            raise InputError("Expenses must be name/amount pairs.")
        for _k, _v in (data.get("expenses") or {}).items():
            if _v not in (None, "") and not (0 <= _num({"v": _v}, "v", lo=0, hi=1e9, label=f"Expense '{_k}'") <= 1e9):
                raise InputError("Invalid expense amount.")

        yield_est = yield_model.get_expected_yield(crop, state=state, season=season)
        price_est = market_service.get_price_estimate(crop, state=state)

        result = estimate_profit(
            area_acres=area_acres, expenses=data.get("expenses", {}),
            yield_estimate=yield_est, price_estimate=price_est,
            manual_price_rs_per_quintal=data.get("manual_price_rs_per_quintal"),
        )
        return jsonify({"success": True, "result": result})
    except Exception as e:
        return _server_error(e)


# ========================================================================= #
# Farm records / dashboard
# ========================================================================= #
EXPENSE_CATEGORIES = {"seeds", "fertilizer", "labour", "water", "pesticides", "other"}


def _record_text(data):
    category = str(data.get("category", "other")).strip().lower()
    if category not in EXPENSE_CATEGORIES:
        category = "other"
    crop = str(data["crop"]).strip()[:40] if data.get("crop") else None
    note = str(data["note"]).strip()[:200] if data.get("note") else None
    return category, crop, note


@app.route("/api/farm/expense", methods=["POST"])
@auth.login_required
def add_expense():
    try:
        data = _json_body()
        category, crop, note = _record_text(data)
        farm_records.add_expense(session["user_id"], category,
                                 _num(data, "amount_rs", 0, 0, 1e9, "Amount"), crop, note)
        return jsonify({"success": True})
    except Exception as e:
        return _server_error(e)


@app.route("/api/farm/expense/<int:record_id>", methods=["PUT"])
@auth.login_required
def update_expense_route(record_id):
    try:
        data = _json_body()
        category, crop, note = _record_text(data)
        amount = _num(data, "amount_rs", 0, 0, 1e9, "Amount")
    except Exception as e:
        return _server_error(e)
    ok = farm_records.update_expense(session["user_id"], record_id, category, amount, crop, note)
    if not ok:
        return jsonify({"success": False, "error": "Record not found."}), 404
    return jsonify({"success": True})


@app.route("/api/farm/expense/<int:record_id>", methods=["DELETE"])
@auth.login_required
def delete_expense_route(record_id):
    ok = farm_records.delete_expense(session["user_id"], record_id)
    if not ok:
        return jsonify({"success": False, "error": "Record not found."}), 404
    return jsonify({"success": True})


@app.route("/api/farm/income", methods=["POST"])
@auth.login_required
def add_income():
    try:
        data = _json_body()
        _, crop, note = _record_text(data)
        farm_records.add_income(session["user_id"], _num(data, "amount_rs", 0, 0, 1e9, "Amount"), crop, note)
        return jsonify({"success": True})
    except Exception as e:
        return _server_error(e)


@app.route("/api/farm/income/<int:record_id>", methods=["PUT"])
@auth.login_required
def update_income_route(record_id):
    try:
        data = _json_body()
        _, crop, note = _record_text(data)
        amount = _num(data, "amount_rs", 0, 0, 1e9, "Amount")
    except Exception as e:
        return _server_error(e)
    ok = farm_records.update_income(session["user_id"], record_id, amount, crop, note)
    if not ok:
        return jsonify({"success": False, "error": "Record not found."}), 404
    return jsonify({"success": True})


@app.route("/api/farm/income/<int:record_id>", methods=["DELETE"])
@auth.login_required
def delete_income_route(record_id):
    ok = farm_records.delete_income(session["user_id"], record_id)
    if not ok:
        return jsonify({"success": False, "error": "Record not found."}), 404
    return jsonify({"success": True})


@app.route("/api/farm/dashboard")
@auth.login_required
def farm_dashboard():
    return jsonify({"success": True, "dashboard": farm_records.get_dashboard(session["user_id"])})


@app.route("/api/farm/records")
@auth.login_required
def farm_records_route():
    return jsonify({"success": True, "records": farm_records.get_farm_records(session["user_id"])})


@app.route("/api/farm/fertilizer-usage", methods=["POST"])
@auth.login_required
def add_fertilizer_usage_route():
    data = request.json or {}
    farm_records.add_fertilizer_usage(
        session["user_id"], data.get("crop"), data.get("fertilizer", ""),
        float(data.get("quantity_kg", 0)) if data.get("quantity_kg") else None,
        data.get("applied_on"), data.get("note"),
    )
    return jsonify({"success": True})


@app.route("/api/farm/fertilizer-usage/<int:record_id>", methods=["PUT"])
@auth.login_required
def update_fertilizer_usage_route(record_id):
    data = request.json or {}
    ok = farm_records.update_fertilizer_usage(
        session["user_id"], record_id, data.get("crop"), data.get("fertilizer", ""),
        float(data.get("quantity_kg", 0)) if data.get("quantity_kg") else None,
        data.get("applied_on"), data.get("note"),
    )
    if not ok:
        return jsonify({"success": False, "error": "Record not found."}), 404
    return jsonify({"success": True})


@app.route("/api/farm/fertilizer-usage/<int:record_id>", methods=["DELETE"])
@auth.login_required
def delete_fertilizer_usage_route(record_id):
    ok = farm_records.delete_fertilizer_usage(session["user_id"], record_id)
    if not ok:
        return jsonify({"success": False, "error": "Record not found."}), 404
    return jsonify({"success": True})


@app.route("/api/farm/analytics")
@auth.login_required
def farm_analytics():
    period = request.args.get("period", "monthly")
    if period not in ("monthly", "yearly"):
        period = "monthly"
    return jsonify({"success": True, "analytics": farm_records.get_analytics(session["user_id"], period)})


# ========================================================================= #
# Knowledge base
# ========================================================================= #
@app.route("/api/knowledge-base")
@auth.login_required
def knowledge_base():
    return jsonify({"success": True, "result": get_knowledge_base()})


@app.route("/api/schemes/eligibility", methods=["POST"])
@auth.login_required
def schemes_eligibility():
    data = request.json or {}
    result = check_eligibility(
        owns_land=bool(data.get("owns_land")), grows_notified_crop=bool(data.get("grows_notified_crop")),
        income_tax_payer=bool(data.get("income_tax_payer")),
        government_employee=bool(data.get("government_employee")),
    )
    return jsonify({"success": True, "result": result})


# ========================================================================= #
# Smart notifications
# ========================================================================= #
@app.route("/api/notifications")
@auth.login_required
def notifications():
    user = auth.current_user()
    lat, lon = request.args.get("lat"), request.args.get("lon")

    forecast = None
    try:
        if lat and lon:
            forecast = weather_service.get_forecast_by_coords(float(lat), float(lon))
        elif user and user.get("location"):
            forecast = weather_service.get_forecast(user["location"])
    except Exception:
        forecast = None

    crop_plans = farm_records.get_active_crop_plans(user["id"])
    latest_match = farm_records.get_latest_disease_check(user["id"])

    notifs = build_notifications(crop_plans, forecast, latest_disease_match=latest_match)
    return jsonify({"success": True, "notifications": notifs})


# ========================================================================= #
# RAG agricultural assistant (retrieval + Gemini - see rag_service.py)
# ========================================================================= #
def _assistant_answer():
    data = _json_body()
    user = auth.current_user()
    history = data.get("history", [])
    if not isinstance(history, list):
        history = []
    context_bits = []
    if user.get("location"):
        context_bits.append(f"location {user['location']}")
    if user.get("soil_type"):
        context_bits.append(f"soil {user['soil_type']}")
    if data.get("crop"):
        context_bits.append(f"crop of interest {str(data['crop'])[:40]}")
    return jsonify(rag.answer(
        data.get("message", ""), history, user["id"],
        language=str(data.get("language") or user.get("preferred_language") or "en"),
        farm_context=", ".join(context_bits) or None))


@app.route("/api/chat", methods=["POST"])
@auth.login_required
@limiter.limit("40 per hour")
def chat():
    """Kept for backwards compatibility - same RAG pipeline as /api/assistant/ask."""
    return _assistant_answer()


@app.route("/api/assistant/ask", methods=["POST"])
@auth.login_required
@limiter.limit("40 per hour")
def assistant_ask():
    return _assistant_answer()


@app.route("/api/assistant/status")
@auth.login_required
def assistant_status():
    return jsonify({"success": True, **rag.status(session["user_id"])})


@app.route("/api/assistant/documents", methods=["GET"])
@auth.login_required
def assistant_documents():
    return jsonify({"success": True, "documents": rag.list_documents(session["user_id"])})


@app.route("/api/assistant/documents", methods=["POST"])
@auth.login_required
@limiter.limit("15 per hour")
def assistant_upload_document():
    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"success": False, "error": "Choose a PDF, TXT or MD file to upload."}), 400
    user = auth.current_user()
    filename = secure_filename(file.filename) or "document.txt"
    title = (request.form.get("title") or os.path.splitext(filename)[0]).strip()[:120] or "Untitled"
    # admins can publish a document to every farmer; everyone else's uploads are private
    scope = "global" if (user["role"] == "admin" and request.form.get("shared") == "1") else "user"
    try:
        result = rag.add_document(user["id"], title, filename, file.read(), scope=scope)
    except RagError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    return jsonify({"success": True, **result, "scope": scope})


@app.route("/api/assistant/documents/<int:doc_id>", methods=["DELETE"])
@auth.login_required
def assistant_delete_document(doc_id):
    user = auth.current_user()
    if not rag.delete_document(user["id"], doc_id, is_admin=user["role"] == "admin"):
        return jsonify({"success": False, "error": "Document not found, or it can't be deleted."}), 404
    return jsonify({"success": True})


# ========================================================================= #
# AI Farm Decision Engine (see decision_engine.py)
# ========================================================================= #
@app.route("/api/decision-engine/plan", methods=["POST"])
@auth.login_required
@limiter.limit("40 per hour")
def decision_plan():
    try:
        plan = engine.build_plan(_json_body(), user=auth.current_user())
        return jsonify(plan)
    except Exception as e:
        return _server_error(e)


@app.route("/api/decision-engine/plans")
@auth.login_required
def decision_plans():
    return jsonify({"success": True, "plans": engine.list_plans(session["user_id"], limit=15)})


@app.route("/api/decision-engine/plans/<plan_id>")
@auth.login_required
def decision_get_plan(plan_id):
    plan = engine.get_plan(session["user_id"], plan_id) if re.fullmatch(r"[0-9a-f]{16}", plan_id) else None
    if not plan:
        return jsonify({"success": False, "error": "Plan not found."}), 404
    return jsonify({"success": True, **plan})


@app.route("/api/decision-engine/plans/<plan_id>/explain", methods=["POST"])
@auth.login_required
@limiter.limit("20 per hour")
def decision_explain(plan_id):
    if not re.fullmatch(r"[0-9a-f]{16}", plan_id):
        return jsonify({"success": False, "error": "Plan not found."}), 404
    user = auth.current_user()
    lang = str(_json_body().get("language") or user.get("preferred_language") or "en")
    return jsonify(engine.explain(user["id"], plan_id, language=lang))


@app.route("/api/decision-engine/plans/<plan_id>/save", methods=["POST"])
@auth.login_required
def decision_save(plan_id):
    """'Save to my farm': stores the chosen crop's calendar as a crop plan (so the
    dashboard, reminders and notifications pick it up) and logs the plan's soil
    check and yield estimate to the farmer's records."""
    uid = session["user_id"]
    plan = engine.get_plan(uid, plan_id) if re.fullmatch(r"[0-9a-f]{16}", plan_id) else None
    if not plan:
        return jsonify({"success": False, "error": "Plan not found."}), 404
    if plan.get("saved"):
        return jsonify({"success": True, "already_saved": True})
    cal = plan.get("calendar") or {}
    crop = plan["summary"]["primary_crop"]
    if cal.get("available") and cal.get("type") == "annual":
        farm_records.save_crop_plan(uid, crop, cal["sowing_date"], cal["expected_harvest_date"],
                                    json.dumps(cal["events"]))
    elif cal.get("available"):
        farm_records.save_crop_plan(uid, crop, plan["summary"]["sowing_date"], None, json.dumps([]))
    soil = plan.get("soil") or {}
    if soil.get("available"):
        h = soil["health"]
        farm_records.log_soil_health(uid, h["soil_health_score"], h["nitrogen_status"],
                                     h["phosphorus_status"], h["potassium_status"])
    y = plan.get("yield") or {}
    if y.get("available"):
        farm_records.log_yield_prediction(uid, crop, plan["summary"]["area_acres"],
                                          y["total_tonnes"]["expected"], y["model_r2"])
    engine.mark_saved(uid, plan_id)
    return jsonify({"success": True, "calendar_saved": bool(cal.get("available"))})


@app.route("/api/decision-engine/plans/<plan_id>", methods=["DELETE"])
@auth.login_required
def decision_delete(plan_id):
    if re.fullmatch(r"[0-9a-f]{16}", plan_id):
        engine.delete_plan(session["user_id"], plan_id)
    return jsonify({"success": True})


# ========================================================================= #
# Farmer command-center dashboard
# ========================================================================= #
@app.route("/api/dashboard/overview")
@auth.login_required
def dashboard_overview():
    try:
        lat = lon = None
        if request.args.get("lat") and request.args.get("lon"):
            lat = _num(request.args, "lat", lo=-90, hi=90, label="Latitude")
            lon = _num(request.args, "lon", lo=-180, hi=180, label="Longitude")
        return jsonify(dashboards.build_overview(auth.current_user(), lat, lon))
    except Exception as e:
        return _server_error(e)


@app.route("/api/health")
def health():
    """Liveness probe for hosting platforms - public, reveals nothing sensitive."""
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    # debug mode is opt-in via env, not hardcoded — Flask's debug mode
    # exposes an interactive in-browser debugger that lets anyone who can
    # trigger an unhandled exception execute arbitrary Python on the
    # server. Fine for local development (set FLASK_DEBUG=1), never safe
    # to leave on for anything reachable outside your own machine.
    # use_reloader=False: the debug reloader watches the whole project
    # directory, including krushi.db — every recommendation/login write to
    # that SQLite file was triggering a full server restart mid-session.
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode, use_reloader=False, host="0.0.0.0", port=5000)
