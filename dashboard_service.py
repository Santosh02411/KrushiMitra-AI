"""
dashboard_service.py
----------------------
Builds the KrushiMitra AI "farm command center" payload from the farmer's own
records (SQL tables) plus a live weather call. Nothing here is hardcoded: when
there is no data for a widget the payload says so (``has_data: False``) and the
page shows an empty state that tells the farmer how to fill it.

Sources
  crop_plans               -> current crops, upcoming activities, fertilizer
                              schedule, irrigation windows
  decision_plans           -> the latest saved AI Farm Decision Engine plan
  soil_health_logs         -> soil health score + trend
  yield_logs               -> yield predictions history
  expenses / income        -> money summary + monthly series
  water_usage_logs, disease_checks, fertilizer_usage_logs -> recent activity
  live weather + water advisor + market service -> conditions, alerts,
                              irrigation reminder, current price
"""

import json
from datetime import date, datetime, timedelta

from decision_engine import irrigation_summary


def _d(value):
    """Parse a DB timestamp (SQLite string / Postgres datetime) to a datetime."""
    if hasattr(value, "strftime"):
        return value
    try:
        return datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _rows(conn, sql, params):
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


class DashboardService:
    def __init__(self, get_db, weather_service, water_advisor, market_service, engine):
        self.get_db = get_db
        self.weather = weather_service
        self.water = water_advisor
        self.market = market_service
        self.engine = engine

    # ------------------------------------------------------------------ #
    def build_overview(self, user, lat=None, lon=None):
        uid = user["id"]
        conn = self.get_db()
        expenses = _rows(conn, "SELECT * FROM expenses WHERE user_id = ? ORDER BY created_at DESC LIMIT 500", (uid,))
        income = _rows(conn, "SELECT * FROM income WHERE user_id = ? ORDER BY created_at DESC LIMIT 500", (uid,))
        soil_logs = _rows(conn, "SELECT * FROM soil_health_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 30", (uid,))
        yield_logs = _rows(conn, "SELECT * FROM yield_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (uid,))
        water_logs = _rows(conn, "SELECT * FROM water_usage_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (uid,))
        disease = _rows(conn, "SELECT * FROM disease_checks WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", (uid,))
        fert_logs = _rows(conn, "SELECT * FROM fertilizer_usage_logs WHERE user_id = ? ORDER BY created_at DESC LIMIT 10", (uid,))
        plans = _rows(conn, "SELECT * FROM crop_plans WHERE user_id = ? ORDER BY created_at DESC LIMIT 20", (uid,))
        conn.close()

        today = date.today()
        active_plans = [p for p in plans if not p.get("harvest_date") or str(p["harvest_date"]) >= today.isoformat()]
        saved_plan = self.engine.latest_saved_plan(uid)

        weather = self._weather(user, lat, lon)
        primary_crop = (active_plans[0]["crop"] if active_plans else
                        (saved_plan["summary"]["primary_crop"] if saved_plan else None))

        return {
            "success": True,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "farm": self._farm(user, active_plans, saved_plan),
            "current_crops": self._current_crops(active_plans, today),
            "soil": self._soil(soil_logs),
            "weather": weather,
            "activities": self._activities(active_plans, today),
            "irrigation": self._irrigation(primary_crop, user, weather),
            "market": self._market(primary_crop, user),
            "yield": self._yield(yield_logs, saved_plan),
            "finance": self._finance(expenses, income),
            "recent": self._recent(expenses, income, soil_logs, yield_logs, water_logs, disease, fert_logs, plans),
            "decision_plan": self._plan_card(saved_plan),
            "recent_plans": self.engine.list_plans(uid, limit=5),
            "has_any_data": bool(expenses or income or soil_logs or yield_logs or water_logs or plans or saved_plan),
        }

    # ------------------------------------------------------------------ #
    def _farm(self, user, active_plans, saved_plan):
        return {
            "name": user["name"], "location": user.get("location"),
            "farm_size_acres": user.get("farm_size_acres"), "soil_type": user.get("soil_type"),
            "active_crops": len(active_plans),
            "profile_complete": bool(user.get("location") and user.get("farm_size_acres")),
        }

    def _current_crops(self, active_plans, today):
        out = []
        for p in active_plans:
            try:
                sow = datetime.strptime(p["sowing_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                continue
            harvest = None
            if p.get("harvest_date"):
                try:
                    harvest = datetime.strptime(p["harvest_date"], "%Y-%m-%d").date()
                except ValueError:
                    harvest = None
            progress = None
            if harvest and harvest > sow:
                progress = max(0, min(100, round((today - sow).days / (harvest - sow).days * 100)))
            out.append({
                "crop": p["crop"], "sowing_date": p["sowing_date"], "harvest_date": p.get("harvest_date"),
                "days_since_sowing": (today - sow).days,
                "days_to_harvest": (harvest - today).days if harvest else None,
                "progress_pct": progress,
                "status": "Not yet sown" if sow > today else ("Growing" if progress is None or progress < 100 else "Harvest due"),
            })
        return out

    def _soil(self, soil_logs):
        if not soil_logs:
            return {"has_data": False, "message": "No soil health check yet - run one in Soil or the Decision Engine."}
        latest = soil_logs[0]
        score = latest["score"]
        band = "Good" if score >= 70 else ("Fair" if score >= 45 else "Needs attention")
        return {"has_data": True, "score": score, "band": band, "n": latest["n_status"], "p": latest["p_status"],
                "k": latest["k_status"], "checked_on": str(latest["created_at"])[:10],
                "trend": [{"date": str(l["created_at"])[:10], "score": l["score"]} for l in reversed(soil_logs[:12])]}

    def _weather(self, user, lat, lon):
        try:
            if lat is not None and lon is not None:
                current = self.weather.get_current_weather_by_coords(lat, lon, user.get("location"))
                forecast = self.weather.get_forecast_by_coords(lat, lon)
            elif user.get("location"):
                current = self.weather.get_current_weather(user["location"])
                forecast = self.weather.get_forecast(user["location"])
            else:
                return {"available": False, "message": "Add your location in your profile (or allow GPS) to see live weather."}
        except Exception as e:
            print(f"[dashboard] weather failed: {e}")
            return {"available": False, "message": "Live weather could not be fetched right now."}
        if str(current.get("source", "")).startswith("offline"):
            return {"available": False, "message": "Live weather is unreachable right now - no sample values are shown."}
        return {"available": True, "current": current, "forecast": forecast,
                "alerts": self.weather.get_alerts(forecast)}

    def _activities(self, active_plans, today):
        horizon = today + timedelta(days=14)
        upcoming, fert, irr = [], [], []
        for p in active_plans:
            try:
                events = json.loads(p.get("calendar_json") or "[]")
            except (ValueError, TypeError):
                events = []
            for ev in events:
                try:
                    ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
                except (ValueError, KeyError):
                    continue
                if today <= ev_date <= horizon:
                    item = {"date": ev["date"], "in_days": (ev_date - today).days, "type": ev["type"],
                            "label": ev["label"], "crop": p["crop"]}
                    upcoming.append(item)
                    if ev["type"] == "fertilizer":
                        fert.append(item)
                    elif ev["type"] == "irrigation":
                        irr.append(item)
        key = lambda x: (x["date"], x["type"])
        return {"has_data": bool(upcoming), "upcoming": sorted(upcoming, key=key)[:15],
                "fertilizer_schedule": sorted(fert, key=key)[:6], "irrigation_windows": sorted(irr, key=key)[:6],
                "message": None if upcoming else "No scheduled activities - save a plan from the Decision Engine "
                                                  "or build a crop calendar to see them here."}

    def _irrigation(self, crop, user, weather):
        if not crop:
            return {"has_data": False, "message": "Choose a crop (Decision Engine or Crop Calendar) to get irrigation reminders."}
        if not weather.get("available"):
            return {"has_data": False, "message": "Irrigation reminders need live weather."}
        advice = self.water.get_irrigation_advice(crop_type=crop, soil_type=(user.get("soil_type") or "").lower(),
                                                  weather_forecast=weather["forecast"])
        sched = advice["irrigation_schedule"]
        return {"has_data": True, "crop": crop, "summary": irrigation_summary(sched),
                "schedule": [{"date": d["date"], "needed": d["irrigation_needed"], "mm": d["water_amount_mm"]}
                             for d in sched]}

    def _market(self, crop, user):
        if not crop:
            return {"has_data": False, "message": "Pick a crop to see its market price."}
        state = None
        loc = user.get("location") or ""
        for part in [x.strip() for x in loc.split(",")]:
            state = part or state
        est = self.market.get_price_estimate(crop, state=state)
        if not est.get("covered"):
            return {"has_data": False, "crop": crop, "message": f"No price data available for {crop} yet."}
        return {"has_data": True, "crop": crop, "price_rs_per_quintal": est["predicted_modal_price"],
                "range": est.get("observed_price_range"), "source": est.get("data_source"),
                "is_prediction": est.get("test_r2") is not None}

    def _yield(self, yield_logs, saved_plan):
        out = {"has_data": bool(yield_logs), "history": [
            {"date": str(y["created_at"])[:10], "crop": y["crop"], "area_acres": y["area_acres"],
             "tonnes": y["predicted_yield_tonnes"]} for y in reversed(yield_logs[:10])]}
        if saved_plan and saved_plan["yield"].get("available"):
            out["plan_estimate"] = {"crop": saved_plan["summary"]["primary_crop"],
                                    "total_tonnes": saved_plan["yield"]["total_tonnes"]}
            out["has_data"] = True
        if not out["has_data"]:
            out["message"] = "No yield predictions yet - try the Yield tool or the Decision Engine."
        return out

    def _finance(self, expenses, income):
        total_exp = round(sum(e["amount_rs"] for e in expenses), 2)
        total_inc = round(sum(i["amount_rs"] for i in income), 2)
        by_cat = {}
        for e in expenses:
            by_cat[e["category"]] = round(by_cat.get(e["category"], 0) + e["amount_rs"], 2)
        monthly = {}
        for rows, key in ((expenses, "expenses"), (income, "income")):
            for r in rows:
                dt = _d(r["created_at"])
                if not dt:
                    continue
                m = dt.strftime("%Y-%m")
                monthly.setdefault(m, {"income": 0.0, "expenses": 0.0})[key] += r["amount_rs"]
        months = sorted(monthly)[-6:]
        return {"has_data": bool(expenses or income), "total_income_rs": total_inc, "total_expenses_rs": total_exp,
                "net_rs": round(total_inc - total_exp, 2), "expenses_by_category": by_cat,
                "monthly": [{"month": m, "income": round(monthly[m]["income"], 2),
                             "expenses": round(monthly[m]["expenses"], 2)} for m in months],
                "message": None if (expenses or income) else "No income or expenses recorded yet - add them in Records."}

    def _recent(self, expenses, income, soil_logs, yield_logs, water_logs, disease, fert_logs, plans):
        items = []
        def add(rows, icon, fmt):
            for r in rows[:8]:
                dt = _d(r["created_at"])
                if dt:
                    items.append({"when": dt.isoformat(sep=" ", timespec="minutes"), "icon": icon, "text": fmt(r)})
        add(expenses, "💸", lambda r: f"Expense ₹{r['amount_rs']:,.0f} - {r['category']}" + (f" ({r['crop']})" if r.get("crop") else ""))
        add(income, "💰", lambda r: f"Income ₹{r['amount_rs']:,.0f}" + (f" ({r['crop']})" if r.get("crop") else ""))
        add(soil_logs, "🌾", lambda r: f"Soil health check - score {r['score']}/100")
        add(yield_logs, "📊", lambda r: f"Yield estimate for {r['crop']}: {r['predicted_yield_tonnes']} t")
        add(water_logs, "💧", lambda r: f"Irrigation plan for {r['crop'] or 'general'} - {r['total_water_mm']} mm")
        add(disease, "🐛", lambda r: f"Disease check ({r['crop']}): {r['matched_disease']}")
        add(fert_logs, "🚜", lambda r: f"Fertilizer applied: {r['fertilizer']}" + (f" ({r['crop']})" if r.get("crop") else ""))
        add(plans, "📅", lambda r: f"Crop plan saved: {r['crop']}, sowing {r['sowing_date']}")
        items.sort(key=lambda x: x["when"], reverse=True)
        return items[:12]

    def _plan_card(self, plan):
        if not plan:
            return {"has_data": False, "message": "No saved plan yet - the AI Farm Decision Engine builds one from your soil, weather and market data."}
        econ = plan.get("economics") or {}
        return {"has_data": True, "plan_id": plan["plan_id"], "crop": plan["summary"]["primary_crop"],
                "headline": plan["summary"]["headline"], "created_at": plan.get("created_at"),
                "profit": econ.get("profit"), "top_risks": [r["text"] for r in plan.get("risks", [])
                                                            if r["level"] in ("high", "medium")][:3]}
