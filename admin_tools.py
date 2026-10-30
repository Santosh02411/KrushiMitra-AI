"""
admin_tools.py
-----------------
Backend for the admin panel: farmer management, a simple news/announcement
board, disease-database entries admins can add, and dashboard stats — all
real queries against the app's own database, no fabricated numbers.

"Revenue (if SaaS)" from the original feature list is deliberately not
shown as a number: Krushi has no billing/subscription system in this
build, so there is no real revenue to report. The dashboard says so
instead of inventing a figure.
"""

from datetime import datetime, timedelta

import db_compat
from auth import DB_PATH, get_db


# ------------------------------------------------------------------ #
# News / announcements
# ------------------------------------------------------------------ #
def add_news(posted_by, title, body):
    conn = get_db()
    conn.execute("INSERT INTO admin_news (posted_by, title, body) VALUES (?, ?, ?)",
                 (posted_by, title, body))
    conn.commit()
    conn.close()


def get_news(limit=20):
    conn = get_db()
    rows = conn.execute(
        "SELECT admin_news.*, users.name as posted_by_name FROM admin_news "
        "JOIN users ON users.id = admin_news.posted_by "
        "ORDER BY admin_news.created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_news(news_id):
    conn = get_db()
    conn.execute("DELETE FROM admin_news WHERE id = ?", (news_id,))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Disease database (admin-added entries, merged with the static
# reference table in disease_reference.py at query time)
# ------------------------------------------------------------------ #
def add_custom_disease(added_by, crop, disease, symptoms, cause, treatment, recommended_fungicide):
    conn = get_db()
    conn.execute(
        "INSERT INTO custom_diseases (added_by, crop, disease, symptoms, cause, treatment, "
        "recommended_fungicide) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (added_by, crop.strip().lower(), disease, "|".join(symptoms), cause, treatment, recommended_fungicide),
    )
    conn.commit()
    conn.close()


def get_custom_diseases(crop=None):
    conn = get_db()
    if crop:
        rows = conn.execute("SELECT * FROM custom_diseases WHERE crop = ?", (crop.strip().lower(),)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM custom_diseases").fetchall()
    conn.close()
    return [{
        "disease": r["disease"], "symptoms": r["symptoms"].split("|"),
        "cause": r["cause"], "treatment": r["treatment"],
        "recommended_fungicide": r["recommended_fungicide"],
    } for r in rows]


def delete_custom_disease(disease_id):
    conn = get_db()
    conn.execute("DELETE FROM custom_diseases WHERE id = ?", (disease_id,))
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ #
# Dashboard stats
# ------------------------------------------------------------------ #
def get_admin_stats():
    conn = get_db()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    # "Active" = has at least one real record/log in the last 30 days —
    # a real, defined query, not a guess. The cutoff is computed in
    # Python (not SQL's datetime('now', ...), which is SQLite-only
    # syntax Postgres doesn't understand) so this works on both.
    cutoff = (datetime.utcnow() - timedelta(days=30)).isoformat()
    active_users = conn.execute("""
        SELECT COUNT(DISTINCT user_id) FROM (
            SELECT user_id, created_at FROM expenses
            UNION ALL SELECT user_id, created_at FROM income
            UNION ALL SELECT user_id, created_at FROM soil_health_logs
            UNION ALL SELECT user_id, created_at FROM water_usage_logs
            UNION ALL SELECT user_id, created_at FROM yield_logs
        ) AS recent_activity WHERE created_at >= ?
    """, (cutoff,)).fetchone()[0]

    disease_scans = conn.execute("SELECT COUNT(*) FROM disease_checks").fetchone()[0]
    conn.close()

    conn2 = db_compat.get_connection(DB_PATH)
    total_recommendations = conn2.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
    conn2.close()

    return {
        "total_users": total_users,
        "active_users_30d": active_users,
        "recommendations_generated": total_recommendations,
        "disease_scans": disease_scans,
        "revenue": None,
        "revenue_note": "Krushi has no billing/subscription system in this build, so there is no "
                         "real revenue figure to report.",
    }
