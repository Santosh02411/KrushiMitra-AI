"""
farm_records.py
------------------
Persistent, per-user farm records backing the Farm Dashboard. Every number
in here is either something the farmer typed in (expenses, income) or a
real result from one of the app's own real modules, logged automatically
the moment a logged-in user gets a soil-health score, an irrigation
schedule, or a yield prediction. There is no synthetic/demo data — a new
account's dashboard starts empty, same as the app itself would in
production.
"""

from datetime import datetime

from auth import get_db


def init_farm_tables():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            category TEXT NOT NULL, amount_rs REAL NOT NULL, crop TEXT, note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS income (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            amount_rs REAL NOT NULL, crop TEXT, note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS soil_health_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            score INTEGER NOT NULL, n_status TEXT, p_status TEXT, k_status TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS water_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            crop TEXT, total_water_mm REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS yield_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            crop TEXT, area_acres REAL, predicted_yield_tonnes REAL, model_r2 REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crop_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            crop TEXT NOT NULL, sowing_date TEXT NOT NULL, harvest_date TEXT,
            calendar_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS disease_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            crop TEXT, matched_disease TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fertilizer_usage_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
            crop TEXT, fertilizer TEXT NOT NULL, quantity_kg REAL, applied_on TEXT, note TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_news (
            id INTEGER PRIMARY KEY AUTOINCREMENT, posted_by INTEGER NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS custom_diseases (
            id INTEGER PRIMARY KEY AUTOINCREMENT, added_by INTEGER NOT NULL,
            crop TEXT NOT NULL, disease TEXT NOT NULL, symptoms TEXT NOT NULL,
            cause TEXT, treatment TEXT, recommended_fungicide TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


def add_expense(user_id, category, amount_rs, crop=None, note=None):
    conn = get_db()
    conn.execute("INSERT INTO expenses (user_id, category, amount_rs, crop, note) VALUES (?, ?, ?, ?, ?)",
                 (user_id, category, amount_rs, crop, note))
    conn.commit()
    conn.close()


def add_income(user_id, amount_rs, crop=None, note=None):
    conn = get_db()
    conn.execute("INSERT INTO income (user_id, amount_rs, crop, note) VALUES (?, ?, ?, ?)",
                 (user_id, amount_rs, crop, note))
    conn.commit()
    conn.close()


def log_soil_health(user_id, score, n_status, p_status, k_status):
    conn = get_db()
    conn.execute("INSERT INTO soil_health_logs (user_id, score, n_status, p_status, k_status) VALUES (?, ?, ?, ?, ?)",
                 (user_id, score, n_status, p_status, k_status))
    conn.commit()
    conn.close()


def log_water_usage(user_id, crop, total_water_mm):
    conn = get_db()
    conn.execute("INSERT INTO water_usage_logs (user_id, crop, total_water_mm) VALUES (?, ?, ?)",
                 (user_id, crop, total_water_mm))
    conn.commit()
    conn.close()


def log_yield_prediction(user_id, crop, area_acres, predicted_yield_tonnes, model_r2):
    conn = get_db()
    conn.execute(
        "INSERT INTO yield_logs (user_id, crop, area_acres, predicted_yield_tonnes, model_r2) VALUES (?, ?, ?, ?, ?)",
        (user_id, crop, area_acres, predicted_yield_tonnes, model_r2),
    )
    conn.commit()
    conn.close()


def log_disease_check(user_id, crop, matched_disease):
    conn = get_db()
    conn.execute("INSERT INTO disease_checks (user_id, crop, matched_disease) VALUES (?, ?, ?)",
                 (user_id, crop, matched_disease))
    conn.commit()
    conn.close()


def get_latest_disease_check(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM disease_checks WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,)
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {"disease": row["matched_disease"], "crop": row["crop"], "created_at": row["created_at"]}


def save_crop_plan(user_id, crop, sowing_date, harvest_date, calendar_json):
    conn = get_db()
    conn.execute(
        "INSERT INTO crop_plans (user_id, crop, sowing_date, harvest_date, calendar_json) VALUES (?, ?, ?, ?, ?)",
        (user_id, crop, sowing_date, harvest_date, calendar_json),
    )
    conn.commit()
    conn.close()


def get_active_crop_plans(user_id):
    """Plans whose harvest date hasn't passed yet — these are what
    notifications.py checks against."""
    conn = get_db()
    today = datetime.now().date().isoformat()
    rows = conn.execute(
        "SELECT * FROM crop_plans WHERE user_id = ? AND (harvest_date IS NULL OR harvest_date >= ?) "
        "ORDER BY sowing_date DESC",
        (user_id, today),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_fertilizer_usage(user_id, crop, fertilizer, quantity_kg, applied_on=None, note=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO fertilizer_usage_logs (user_id, crop, fertilizer, quantity_kg, applied_on, note) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, crop, fertilizer, quantity_kg, applied_on, note),
    )
    conn.commit()
    conn.close()


def update_expense(user_id, record_id, category, amount_rs, crop=None, note=None):
    """Only touches the row if it belongs to user_id — returns True if a row was updated."""
    conn = get_db()
    cur = conn.execute(
        "UPDATE expenses SET category = ?, amount_rs = ?, crop = ?, note = ? WHERE id = ? AND user_id = ?",
        (category, amount_rs, crop, note, record_id, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_expense(user_id, record_id):
    conn = get_db()
    cur = conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (record_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def update_income(user_id, record_id, amount_rs, crop=None, note=None):
    conn = get_db()
    cur = conn.execute(
        "UPDATE income SET amount_rs = ?, crop = ?, note = ? WHERE id = ? AND user_id = ?",
        (amount_rs, crop, note, record_id, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_income(user_id, record_id):
    conn = get_db()
    cur = conn.execute("DELETE FROM income WHERE id = ? AND user_id = ?", (record_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def update_fertilizer_usage(user_id, record_id, crop, fertilizer, quantity_kg, applied_on=None, note=None):
    conn = get_db()
    cur = conn.execute(
        "UPDATE fertilizer_usage_logs SET crop = ?, fertilizer = ?, quantity_kg = ?, applied_on = ?, note = ? "
        "WHERE id = ? AND user_id = ?",
        (crop, fertilizer, quantity_kg, applied_on, note, record_id, user_id),
    )
    conn.commit()
    updated = cur.rowcount > 0
    conn.close()
    return updated


def delete_fertilizer_usage(user_id, record_id):
    conn = get_db()
    cur = conn.execute("DELETE FROM fertilizer_usage_logs WHERE id = ? AND user_id = ?", (record_id, user_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


def _rows(user_id, table, limit=50):
    conn = get_db()
    rows = conn.execute(f"SELECT * FROM {table} WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                         (user_id, limit)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_farm_records(user_id):
    """Unified view for the Farm Records page: crops grown, yield, expenses,
    income, fertilizer usage — each pulled straight from its own real
    table, nothing synthesized."""
    return {
        "crops_grown": _rows(user_id, "crop_plans"),
        "yield_history": _rows(user_id, "yield_logs"),
        "expenses": _rows(user_id, "expenses"),
        "income": _rows(user_id, "income"),
        "fertilizer_usage": _rows(user_id, "fertilizer_usage_logs"),
    }


def _bucket_key(created_at, period):
    # SQLite returns TIMESTAMP columns as 'YYYY-MM-DD HH:MM:SS' strings;
    # Postgres returns native datetime objects for the same column type.
    # Handle both rather than assuming one.
    text = created_at.strftime("%Y-%m-%d %H:%M:%S") if hasattr(created_at, "strftime") else str(created_at)
    return text[:7] if period == "monthly" else text[:4]  # YYYY-MM or YYYY


def get_analytics(user_id, period="monthly"):
    """Real aggregation of the farmer's own logged data, bucketed by month
    or year — no forecasting, no synthetic trend, just sums/averages of
    what's actually been recorded."""
    conn = get_db()
    yield_rows = conn.execute("SELECT * FROM yield_logs WHERE user_id = ?", (user_id,)).fetchall()
    expense_rows = conn.execute("SELECT * FROM expenses WHERE user_id = ?", (user_id,)).fetchall()
    income_rows = conn.execute("SELECT * FROM income WHERE user_id = ?", (user_id,)).fetchall()
    water_rows = conn.execute("SELECT * FROM water_usage_logs WHERE user_id = ?", (user_id,)).fetchall()
    conn.close()

    def bucket_sum(rows, amount_key):
        buckets = {}
        for r in rows:
            k = _bucket_key(r["created_at"], period)
            buckets[k] = buckets.get(k, 0) + (r[amount_key] or 0)
        return dict(sorted(buckets.items()))

    yield_by_period = bucket_sum(yield_rows, "predicted_yield_tonnes")
    expenses_by_period = bucket_sum(expense_rows, "amount_rs")
    income_by_period = bucket_sum(income_rows, "amount_rs")
    water_by_period = bucket_sum(water_rows, "total_water_mm")

    profit_by_period = {}
    for k in set(list(expenses_by_period.keys()) + list(income_by_period.keys())):
        profit_by_period[k] = round(income_by_period.get(k, 0) - expenses_by_period.get(k, 0), 2)
    profit_by_period = dict(sorted(profit_by_period.items()))

    crop_comparison = {}
    for r in yield_rows:
        crop = r["crop"] or "unknown"
        crop_comparison.setdefault(crop, {"total_yield_tonnes": 0, "count": 0})
        crop_comparison[crop]["total_yield_tonnes"] += r["predicted_yield_tonnes"] or 0
        crop_comparison[crop]["count"] += 1
    for crop, exp in [(r["crop"] or "unknown", r["amount_rs"]) for r in expense_rows]:
        crop_comparison.setdefault(crop, {"total_yield_tonnes": 0, "count": 0})
        crop_comparison[crop]["total_expenses_rs"] = crop_comparison[crop].get("total_expenses_rs", 0) + exp

    return {
        "period": period,
        "yield_by_period": yield_by_period,
        "expenses_by_period": expenses_by_period,
        "income_by_period": income_by_period,
        "profit_by_period": profit_by_period,
        "water_usage_by_period": water_by_period,
        "crop_comparison": crop_comparison,
        "has_data": bool(yield_rows or expense_rows or income_rows or water_rows),
    }


def get_dashboard(user_id):
    expenses = _rows(user_id, "expenses")
    income = _rows(user_id, "income")
    soil_logs = _rows(user_id, "soil_health_logs")
    water_logs = _rows(user_id, "water_usage_logs")
    yield_logs = _rows(user_id, "yield_logs")

    total_expenses = round(sum(e["amount_rs"] for e in expenses), 2)
    total_income = round(sum(i["amount_rs"] for i in income), 2)
    expenses_by_category = {}
    for e in expenses:
        expenses_by_category[e["category"]] = expenses_by_category.get(e["category"], 0) + e["amount_rs"]

    return {
        "expenses": expenses, "income": income, "soil_health_logs": soil_logs,
        "water_usage_logs": water_logs, "yield_logs": yield_logs,
        "summary": {
            "total_expenses_rs": total_expenses, "total_income_rs": total_income,
            "net_profit_rs": round(total_income - total_expenses, 2),
            "expenses_by_category": expenses_by_category,
            "records_present": bool(expenses or income or soil_logs or water_logs or yield_logs),
        },
    }
