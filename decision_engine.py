"""
decision_engine.py
--------------------
The KrushiMitra AI Farm Decision Engine.

It does not add a new model. It orchestrates the modules the app already has -
crop recommendation, soil health, weather, yield prediction, market prices,
fertilizer plan, irrigation advisor and crop calendar - into one personalised
farm plan, and is strict about *what kind of information* each number is.

Every section of the plan is tagged with a provenance ``kind``:

    measured     a value the farmer typed in (soil test, area, costs entered)
    live         fetched from a live service right now (weather forecast,
                 data.gov.in prices when MARKET_API_KEY is set)
    model        a trained-model prediction (crop suitability, yield, price)
    reference    published reference tables / transparent rules (fertilizer
                 doses, crop duration, irrigation profile, soil-card bands)
    observed     real historical records summarised (mandi price records,
                 state production records) - history, not a forecast
    unavailable  we could not produce it; the plan says why

Hard rules enforced here:
  * nothing is fabricated: if an input or data source is missing the section
    says so and, where possible, falls back to a smaller honest alternative;
  * costs the engine cannot know (seeds, labour, pesticides, irrigation) are
    NEVER guessed - they only count if the farmer enters them, and the
    profit figure says plainly what it leaves out;
  * profit is a range built from model error margins, labelled an estimate,
    never a guarantee.
"""

import json
import os
import uuid
from datetime import date, datetime, timedelta

import requests

import db_compat
from crop_calendar import CROP_DURATION_DAYS, PERENNIAL_CROPS, get_crop_calendar
from disease_reference import DISEASE_REFERENCE
from fertilizer_recommendation import CROP_FERTILIZER_PLAN, get_fertilizer_plan
from regional_crops import get_common_crops, get_season_crops
from yield_model import CROP_YIELD_MAP
from soil_health import analyze_soil

ACRE_TO_HA = 0.404686
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

SEASONS = ["Kharif", "Rabi", "Summer", "Whole Year", "Winter", "Autumn"]

# dataset crop name -> the key the rest of the app uses (e.g. "Gram" -> "chickpea")
_DATASET_TO_KEY = {v.lower(): k for k, v in CROP_YIELD_MAP.items()}
# market data is filed under the trade name for a few crops
_PRICE_ALIAS = {"chickpea": "gram", "blackgram": "urad"}

PROVENANCE_LEGEND = {
    "measured": "A value you entered.",
    "live": "Fetched from a live service right now.",
    "model": "A trained-model prediction - an estimate, not a measurement.",
    "reference": "Published reference tables or transparent rules - general guidance.",
    "observed": "Summary of real historical records - history, not a forecast.",
    "unavailable": "Could not be produced - see the explanation.",
}


class PlanInputError(ValueError):
    """Invalid user input; message is safe to show."""


# ---------------------------------------------------------------------- #
# Input validation
# ---------------------------------------------------------------------- #
def _num(data, key, lo, hi, label, required=False):
    raw = data.get(key)
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        if required:
            raise PlanInputError(f"{label} is required.")
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise PlanInputError(f"{label} must be a number.")
    if value != value or value in (float("inf"), float("-inf")):
        raise PlanInputError(f"{label} must be a real number.")
    if not (lo <= value <= hi):
        raise PlanInputError(f"{label} must be between {lo:g} and {hi:g}.")
    return value


def _text(data, key, max_len=80):
    v = data.get(key)
    if v is None:
        return None
    v = str(v).strip()
    return v[:max_len] if v else None


def infer_season(today=None):
    m = (today or date.today()).month
    if 6 <= m <= 10:
        return "Kharif"
    if m in (11, 12, 1, 2, 3):
        return "Rabi"
    return "Summer"


def parse_inputs(data, user=None, valid_crops=None):
    """Validate + normalise the request. Returns (inputs, gaps)."""
    data = data or {}
    user = user or {}
    gaps = []

    inputs = {
        "location": _text(data, "location", 120) or user.get("location"),
        "state": _text(data, "state"),
        "district": _text(data, "district"),
        "lat": _num(data, "lat", -90, 90, "Latitude"),
        "lon": _num(data, "lon", -180, 180, "Longitude"),
        "area_acres": _num(data, "area_acres", 0.05, 100000, "Farm area (acres)"),
        "soil_type": _text(data, "soil_type", 40) or user.get("soil_type"),
        "n": _num(data, "n", 0, 1000, "Nitrogen"),
        "p": _num(data, "p", 0, 1000, "Phosphorus"),
        "k": _num(data, "k", 0, 2000, "Potassium"),
        "ph": _num(data, "ph", 3, 10, "Soil pH"),
        "organic_carbon": _num(data, "organic_carbon", 0, 10, "Organic carbon (%)"),
        "temperature": _num(data, "temperature", -10, 55, "Temperature"),
        "humidity": _num(data, "humidity", 0, 100, "Humidity"),
        "monthly_rainfall_mm": _num(data, "monthly_rainfall_mm", 0, 3000, "Rainfall"),
        "manual_price_rs_per_quintal": _num(data, "manual_price_rs_per_quintal", 1, 1000000, "Expected price"),
        "manual_yield_t_per_acre": _num(data, "manual_yield_t_per_acre", 0.01, 500, "Expected yield"),
        "language": (_text(data, "language", 5) or user.get("preferred_language") or "en")[:2],
    }

    if inputs["area_acres"] is None:
        profile_area = user.get("farm_size_acres")
        if profile_area:
            inputs["area_acres"] = float(profile_area)
            inputs["area_from_profile"] = True
        else:
            inputs["area_acres"] = 1.0
            inputs["area_defaulted"] = True
            gaps.append("Farm area not provided - the plan is calculated for 1 acre. Enter your area for "
                        "totals that match your farm.")

    season = _text(data, "season", 20)
    if season and season.title() not in SEASONS and season not in SEASONS:
        raise PlanInputError(f"Season must be one of: {', '.join(SEASONS)}.")
    inputs["season"] = season.title() if season else None
    inputs["season_inferred"] = False
    if not inputs["season"]:
        inputs["season"] = infer_season()
        inputs["season_inferred"] = True
        gaps.append(f"Season not provided - assumed {inputs['season']} from today's date.")

    crop = _text(data, "selected_crop", 40)
    if crop:
        crop = crop.lower()
        if valid_crops is not None and crop not in valid_crops:
            raise PlanInputError(f"'{crop}' isn't a crop KrushiMitra has data for.")
    inputs["selected_crop"] = crop

    sd = _text(data, "sowing_date", 12)
    if sd:
        try:
            sowing = datetime.strptime(sd, "%Y-%m-%d").date()
        except ValueError:
            raise PlanInputError("Sowing date must look like 2026-11-05.")
        if abs((sowing - date.today()).days) > 400:
            raise PlanInputError("Sowing date must be within about a year of today.")
        inputs["sowing_date"] = sowing.isoformat()
    else:
        inputs["sowing_date"] = date.today().isoformat()
        inputs["sowing_date_defaulted"] = True

    costs = {}
    raw_costs = data.get("expenses") or {}
    if not isinstance(raw_costs, dict):
        raise PlanInputError("Costs must be given as name/amount pairs.")
    for k in ("seeds", "labour", "pesticides", "water", "other"):
        v = raw_costs.get(k)
        if v in (None, ""):
            continue
        try:
            amt = float(v)
        except (TypeError, ValueError):
            raise PlanInputError(f"Cost for {k} must be a number.")
        if amt < 0 or amt > 1e8:
            raise PlanInputError(f"Cost for {k} must be between 0 and 100,000,000.")
        if amt:
            costs[k] = round(amt, 2)
    inputs["entered_costs"] = costs

    soil_values = [inputs[k] for k in ("n", "p", "k", "ph")]
    inputs["soil_complete"] = all(v is not None for v in soil_values)
    if not inputs["soil_complete"]:
        if any(v is not None for v in soil_values):
            missing = [lbl for lbl, k in (("N", "n"), ("P", "p"), ("K", "k"), ("pH", "ph")) if inputs[k] is None]
            gaps.append(f"Soil test incomplete (missing {', '.join(missing)}) - soil-based crop ranking and "
                        f"nutrient analysis need all of N, P, K and pH.")
        else:
            gaps.append("No soil test values - crop ranking falls back to what is widely grown in your "
                        "state, and nutrient deficiencies cannot be assessed.")
    if inputs["lat"] is None and inputs["lon"] is None and not inputs["location"]:
        gaps.append("No location - live weather, irrigation timing and weather precautions are unavailable.")
    if (inputs["lat"] is None) != (inputs["lon"] is None):
        raise PlanInputError("Provide both latitude and longitude, or neither.")
    if not inputs["state"] and not inputs["soil_complete"]:
        raise PlanInputError("Give the engine something to work with: either a full soil test (N, P, K, pH) "
                             "or at least your state.")
    return inputs, gaps


# ---------------------------------------------------------------------- #
# Helpers over live data
# ---------------------------------------------------------------------- #
def fetch_recent_monthly_rainfall(lat, lon, days=90):
    """Mean monthly rainfall (mm) observed over the last ``days`` days from the
    Open-Meteo archive (real observations, free, keyless). The crop model's
    'rainfall' feature is a monthly-scale value (training range ~20-300 mm),
    so this is the closest real, location-specific quantity we can supply.
    Returns None on any failure."""
    try:
        end = date.today() - timedelta(days=5)  # archive lags a few days
        start = end - timedelta(days=days)
        resp = requests.get(ARCHIVE_URL, params={
            "latitude": lat, "longitude": lon, "start_date": start.isoformat(),
            "end_date": end.isoformat(), "daily": "precipitation_sum", "timezone": "auto"}, timeout=6)
        resp.raise_for_status()
        vals = [v for v in resp.json().get("daily", {}).get("precipitation_sum", []) if v is not None]
        if len(vals) < days * 0.7:
            return None
        return round(sum(vals) / (len(vals) / 30.0), 1)
    except Exception as e:
        print(f"[decision_engine] rainfall archive unavailable: {e}")
        return None


def _is_offline(weather_obj):
    if isinstance(weather_obj, dict):
        return str(weather_obj.get("source", "")).startswith("offline")
    if isinstance(weather_obj, list) and weather_obj:
        return str(weather_obj[0].get("weather", "")).startswith("offline")
    return True


def irrigation_summary(schedule):
    next_day = next((d for d in schedule if d["irrigation_needed"]), None)
    if not next_day:
        return {"water_required_mm": 0, "next_irrigation_in_days": None,
                "message": "No irrigation needed in the next 7 days based on the forecast."}
    return {"water_required_mm": next_day["water_amount_mm"], "next_irrigation_in_days": next_day["day"],
            "message": f"{next_day['water_amount_mm']} mm needed - next irrigation in "
                       f"{next_day['day']} day{'s' if next_day['day'] != 1 else ''}."}


# ---------------------------------------------------------------------- #
# Engine
# ---------------------------------------------------------------------- #
class DecisionEngine:
    def __init__(self, crop_model, yield_model, water_advisor, weather_service, market_service, gemini,
                 get_db, valid_crops=None):
        self.crop_model = crop_model
        self.yield_model = yield_model
        self.water = water_advisor
        self.weather = weather_service
        self.market = market_service
        self.gemini = gemini
        self.get_db = get_db
        self.valid_crops = valid_crops

        df = crop_model.df
        self._crop_ranges = {
            crop: {col: (float(g[col].quantile(0.10)), float(g[col].quantile(0.90)))
                   for col in ("N", "P", "K", "temperature", "humidity", "ph", "rainfall")}
            for crop, g in df.groupby("label")
        }
        self._train_bounds = {col: (float(df[col].min()), float(df[col].max()))
                              for col in ("N", "P", "K", "temperature", "humidity", "ph", "rainfall")}

    def _price_estimate(self, crop, state):
        est = self.market.get_price_estimate(crop, state=state)
        if not est.get("covered") and crop in _PRICE_ALIAS:
            alt = self.market.get_price_estimate(_PRICE_ALIAS[crop], state=state)
            if alt.get("covered"):
                alt = dict(alt, crop=crop)
                return alt
        return est

    # ------------------------------ storage ----------------------------- #
    def init_tables(self):
        conn = self.get_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS decision_plans (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                crop TEXT,
                area_acres REAL,
                inputs_json TEXT,
                plan_json TEXT NOT NULL,
                explanation TEXT,
                saved INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        conn.close()

    def _store(self, user_id, plan, inputs):
        plan_id = uuid.uuid4().hex[:16]
        conn = self.get_db()
        conn.execute(
            "INSERT INTO decision_plans (id, user_id, crop, area_acres, inputs_json, plan_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (plan_id, user_id, plan["summary"].get("primary_crop"), inputs.get("area_acres"),
             json.dumps(inputs), json.dumps(plan)))
        # keep each farmer's 40 most recent unsaved plans; saved plans are kept
        old = conn.execute("SELECT id FROM decision_plans WHERE user_id = ? AND saved = 0 "
                           "ORDER BY created_at DESC, id DESC", (user_id,)).fetchall()
        for r in old[40:]:
            conn.execute("DELETE FROM decision_plans WHERE id = ?", (r["id"],))
        conn.commit()
        conn.close()
        return plan_id

    def get_plan(self, user_id, plan_id):
        conn = self.get_db()
        row = conn.execute("SELECT * FROM decision_plans WHERE id = ? AND user_id = ?",
                           (plan_id, user_id)).fetchone()
        conn.close()
        if not row:
            return None
        plan = json.loads(row["plan_json"])
        plan["plan_id"] = row["id"]
        plan["saved"] = bool(row["saved"])
        plan["explanation"] = row["explanation"]
        plan["created_at"] = str(row["created_at"])[:19]
        return plan

    def list_plans(self, user_id, limit=10):
        conn = self.get_db()
        rows = conn.execute("SELECT id, crop, area_acres, saved, created_at, plan_json FROM decision_plans "
                            "WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
                            (user_id, limit)).fetchall()
        conn.close()
        out = []
        for r in rows:
            try:
                s = json.loads(r["plan_json"]).get("summary", {})
            except ValueError:
                s = {}
            out.append({"plan_id": r["id"], "crop": r["crop"], "area_acres": r["area_acres"],
                        "saved": bool(r["saved"]), "created_at": str(r["created_at"])[:19],
                        "season": s.get("season"), "headline": s.get("headline")})
        return out

    def latest_saved_plan(self, user_id):
        conn = self.get_db()
        row = conn.execute("SELECT id FROM decision_plans WHERE user_id = ? AND saved = 1 "
                           "ORDER BY created_at DESC, id DESC LIMIT 1", (user_id,)).fetchone()
        conn.close()
        return self.get_plan(user_id, row["id"]) if row else None

    def mark_saved(self, user_id, plan_id):
        conn = self.get_db()
        cur = conn.execute("UPDATE decision_plans SET saved = 1 WHERE id = ? AND user_id = ?", (plan_id, user_id))
        conn.commit()
        conn.close()
        return True

    def delete_plan(self, user_id, plan_id):
        conn = self.get_db()
        conn.execute("DELETE FROM decision_plans WHERE id = ? AND user_id = ?", (plan_id, user_id))
        conn.commit()
        conn.close()

    # ------------------------------ main -------------------------------- #
    def build_plan(self, data, user=None):
        inputs, gaps = parse_inputs(data, user, valid_crops=self.valid_crops)
        notes = []  # data-quality notes shown to the farmer

        # ---- 1. weather (live) ------------------------------------------------
        wx = self._get_weather(inputs)
        if wx["available"]:
            if inputs["lat"] is None and wx.get("lat") is not None:
                inputs["lat"], inputs["lon"] = wx["lat"], wx["lon"]
        else:
            gaps.append(wx["reason"])

        # ---- 2. climate features for the crop model -----------------------------
        climate = self._climate_features(inputs, wx, notes, gaps)

        # ---- 3. candidates ---------------------------------------------------------
        ranking = self._rank_crops(inputs, climate, notes, gaps)
        primary_key = ranking["primary"]
        if not primary_key:
            raise PlanInputError("Could not choose a crop with the information given. Add your state or a soil "
                                 "test and try again.")

        # ---- 4. evaluate primary + alternatives -------------------------------------
        primary = self._evaluate_crop(primary_key, inputs, climate, ranking, is_primary=True)
        alternatives = [self._evaluate_crop(k, inputs, climate, ranking, is_primary=False)
                        for k in ranking["alternatives"]]
        # relative-economics note for alternatives
        base_rev = (primary["economics_preview"] or {}).get("revenue_per_acre_expected")
        for alt in alternatives:
            alt_rev = (alt["economics_preview"] or {}).get("revenue_per_acre_expected")
            if base_rev and alt_rev:
                diff = (alt_rev - base_rev) / base_rev * 100
                alt["vs_primary"] = (f"Model-estimated revenue about {abs(diff):.0f}% "
                                     f"{'higher' if diff >= 0 else 'lower'} than {primary_key.title()} "
                                     f"(estimates, before costs).")

        # ---- 5. detailed sections for the primary crop --------------------------------
        area = inputs["area_acres"]
        soil = self._soil_section(inputs, primary_key, climate)
        fert = self._fertilizer_section(primary_key, area)
        irr = self._irrigation_section(primary_key, inputs, wx)
        weather_section = self._weather_section(wx, primary_key)
        yld = self._yield_section(primary_key, inputs, area)
        mkt = self._market_section(primary_key, inputs)
        econ = self._economics(primary_key, inputs, fert, yld, mkt, area)
        calendar = self._calendar_section(primary_key, inputs, irr)
        week = self._seven_day_plan(primary_key, inputs, wx, irr, fert, calendar, soil)
        risks = self._risks(primary_key, inputs, wx, soil, yld, mkt, climate, ranking)

        # ---- 6. assemble ---------------------------------------------------------------
        headline = self._headline(primary, ranking, inputs, econ)
        plan = {
            "success": True,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "disclaimer": ("Decision support, not a guarantee. Values marked 'model' are estimates with real "
                           "error margins; yields and prices can differ a lot from what is shown. Confirm "
                           "fertilizer and pesticide doses with a local Krishi Vigyan Kendra or input dealer."),
            "provenance_legend": PROVENANCE_LEGEND,
            "summary": {
                "headline": headline, "primary_crop": primary_key, "area_acres": area,
                "season": inputs["season"], "season_inferred": inputs["season_inferred"],
                "ranking_basis": ranking["basis"], "ranking_basis_kind": ranking["basis_kind"],
                "location": inputs["location"], "state": inputs["state"],
                "sowing_date": inputs["sowing_date"],
            },
            "inputs": {k: v for k, v in inputs.items() if v not in (None, {}, "")},
            "data_gaps": gaps,
            "data_quality": notes,
            "crops": {"primary": primary, "alternatives": alternatives},
            "soil": soil, "fertilizer": fert, "irrigation": irr, "weather": weather_section,
            "yield": yld, "market": mkt, "economics": econ, "calendar": calendar,
            "seven_day_plan": week, "risks": risks,
        }
        plan["plan_id"] = self._store(user["id"] if user else 0, plan, inputs)
        plan["saved"] = False
        plan["explanation"] = None
        return plan

    # ------------------------------ weather ----------------------------- #
    def _get_weather(self, inputs):
        lat, lon, loc = inputs["lat"], inputs["lon"], inputs["location"]
        if lat is None and not loc:
            return {"available": False, "reason": "No location - live weather unavailable."}
        try:
            if lat is not None:
                current = self.weather.get_current_weather_by_coords(lat, lon, loc)
                forecast = self.weather.get_forecast_by_coords(lat, lon)
                coords = (lat, lon)
            else:
                current = self.weather.get_current_weather(loc)
                forecast = self.weather.get_forecast(loc)
                coords = (None, None)
                try:
                    geo = self.weather._geocode(loc)
                    if geo:
                        coords = (geo["lat"], geo["lon"])
                except Exception:
                    pass
        except Exception as e:
            print(f"[decision_engine] weather failed: {e}")
            return {"available": False, "reason": "Live weather could not be fetched right now."}
        if _is_offline(current) or _is_offline(forecast):
            return {"available": False,
                    "reason": "Live weather is unreachable right now (offline sample values were NOT used) - "
                              "irrigation timing and weather precautions are unavailable."}
        return {"available": True, "current": current, "forecast": forecast,
                "alerts": self.weather.get_alerts(forecast), "lat": coords[0], "lon": coords[1],
                "source": current.get("source")}

    # ------------------------------ climate ----------------------------- #
    def _climate_features(self, inputs, wx, notes, gaps):
        """Temperature / humidity / rainfall to feed the crop model, each with
        where it came from."""
        out = {"temperature": None, "humidity": None, "rainfall": None, "sources": {}}
        fc = wx.get("forecast") if wx["available"] else None

        if inputs["temperature"] is not None:
            out["temperature"], out["sources"]["temperature"] = inputs["temperature"], "entered by you"
        elif fc:
            temps = [d["temperature"] for d in fc if d.get("temperature") is not None]
            if temps:
                out["temperature"] = round(sum(temps) / len(temps), 1)
                out["sources"]["temperature"] = "mean of the 7-day forecast (live)"
        if inputs["humidity"] is not None:
            out["humidity"], out["sources"]["humidity"] = inputs["humidity"], "entered by you"
        elif fc:
            hum = [d["humidity"] for d in fc if d.get("humidity") is not None]
            if hum:
                out["humidity"] = round(sum(hum) / len(hum), 1)
                out["sources"]["humidity"] = "mean of the 7-day forecast (live)"

        if inputs["monthly_rainfall_mm"] is not None:
            out["rainfall"], out["sources"]["rainfall"] = inputs["monthly_rainfall_mm"], "entered by you"
        else:
            lat, lon = inputs["lat"], inputs["lon"]
            if lat is None and wx.get("available"):
                lat, lon = wx.get("lat"), wx.get("lon")
            if lat is not None:
                r = fetch_recent_monthly_rainfall(lat, lon)
                if r is not None:
                    out["rainfall"] = r
                    out["sources"]["rainfall"] = "average monthly rainfall over the last 90 days (Open-Meteo observations)"
        if out["rainfall"] is None:
            gaps.append("Recent rainfall could not be determined - the crop model used the dataset's typical "
                        "rainfall instead. Enter your monthly rainfall for a better match.")
        return out

    # ------------------------------ ranking ----------------------------- #
    def _rank_crops(self, inputs, climate, notes, gaps):
        state, season = inputs["state"], inputs["season"]
        ml_ok = inputs["soil_complete"] and climate["temperature"] is not None and climate["humidity"] is not None
        ml_candidates = []
        clipped = []

        if ml_ok:
            tb = self._train_bounds
            def clip(name, v, label):
                lo, hi = tb[name]
                if v < lo or v > hi:
                    clipped.append(f"{label} {v:g} is outside the crop model's training range "
                                   f"({lo:g}-{hi:g}); it was treated as {min(max(v, lo), hi):g}.")
                return min(max(v, lo), hi)
            rainfall = climate["rainfall"]
            if rainfall is None:
                rainfall = float(self.crop_model.df["rainfall"].median())
            try:
                recs = self.crop_model.recommend_crops(
                    n=clip("N", inputs["n"], "Nitrogen"), p=clip("P", inputs["p"], "Phosphorus"),
                    k=clip("K", inputs["k"], "Potassium"), temperature=climate["temperature"],
                    humidity=climate["humidity"], ph=clip("ph", inputs["ph"], "pH"),
                    rainfall=min(max(rainfall, 0), 3000), top_n=10)
                ml_candidates = recs
            except Exception as e:
                print(f"[decision_engine] crop model failed: {e}")
                ml_ok = False
        if clipped:
            notes.append("Soil values: " + " ".join(clipped) + " The crop model uses a smaller N-P-K scale than "
                         "Soil Health Card readings, so treat the crop ranking as indicative.")

        regional = []
        if state:
            season_crops = get_season_crops(state, season, top_n=30)
            if season_crops:
                for c in season_crops:
                    key = _DATASET_TO_KEY.get(c["dataset_crop"].lower()) or c["dataset_crop"].lower()
                    if self.yield_model.is_covered(key) or key in self.crop_model.crop_info:
                        regional.append({"key": key, "records": c["records"], "season_match": True,
                                         "median_area_ha": c["median_area_ha"], "whole_year": c["whole_year"],
                                         "typical_yield": c["typical_yield_tonnes_per_ha"],
                                         "seasons": [season]})
            else:
                reg = get_common_crops(state, top_n=1)
                gaps.append(f"No {season}-season production records for '{state}' in the dataset"
                            if reg.get("covered") else reg.get("message", f"No production records for '{state}'."))

        info = {c["crop"]: c for c in ml_candidates}
        selected = inputs["selected_crop"]
        if selected:
            primary, basis, kind = selected, "Crop chosen by you.", "measured"
        elif ml_ok and ml_candidates:
            primary = ml_candidates[0]["crop"]
            basis = ("Soil-and-climate suitability from a RandomForest trained on 2,200 real field samples "
                     "(top model confidence).")
            kind = "model"
        elif regional:
            primary = regional[0]["key"]
            basis = (f"Soil values were not complete, so this is ranked by how widely it is grown in {state} in "
                     f"the {season} season (real production records, by area) - not by soil suitability.")
            kind = "observed"
        else:
            return {"primary": None}

        alternatives = []
        for c in ml_candidates:
            if c["crop"] != primary and c["confidence"] >= 1.0:
                alternatives.append(c["crop"])
        for r in regional:
            if r["key"] != primary and r["key"] not in alternatives:
                alternatives.append(r["key"])
        alternatives = alternatives[:5]
        if ml_ok and len(alternatives) < 3:
            for c in ml_candidates:
                if c["crop"] != primary and c["crop"] not in alternatives:
                    alternatives.append(c["crop"])
                if len(alternatives) >= 3:
                    break

        return {"primary": primary, "alternatives": alternatives, "basis": basis, "basis_kind": kind,
                "ml": info, "ml_used": ml_ok and bool(ml_candidates), "regional": {r["key"]: r for r in regional},
                "selected_by_user": bool(selected)}

    # --------------------------- per-crop evaluation -------------------- #
    def _soil_fit(self, crop, inputs, climate):
        ranges = self._crop_ranges.get(crop)
        if not ranges:
            return {"covered": False, "message": "No soil-suitability reference for this crop (the soil model "
                                                  "covers 22 crops)."}
        checks = []
        pairs = [("N", "Nitrogen", inputs["n"]), ("P", "Phosphorus", inputs["p"]), ("K", "Potassium", inputs["k"]),
                 ("ph", "Soil pH", inputs["ph"]), ("temperature", "Temperature", climate["temperature"]),
                 ("humidity", "Humidity", climate["humidity"]), ("rainfall", "Monthly rainfall", climate["rainfall"])]
        for col, label, value in pairs:
            if value is None:
                continue
            lo, hi = ranges[col]
            status = "within" if lo <= value <= hi else ("below" if value < lo else "above")
            checks.append({"parameter": label, "your_value": round(value, 1),
                           "typical_range": [round(lo, 1), round(hi, 1)], "status": status})
        if not checks:
            return {"covered": False, "message": "Not enough soil/climate values to compare."}
        within = sum(1 for c in checks if c["status"] == "within")
        ratio = within / len(checks)
        verdict = "Good fit" if ratio >= 0.8 else ("Partial fit" if ratio >= 0.5 else "Poor fit")
        return {"covered": True, "verdict": verdict, "within": within, "checked": len(checks), "checks": checks,
                "kind": "reference",
                "basis": "Compared with the middle 80% of values where this crop is grown in the 2,200-sample "
                         "crop-recommendation dataset."}

    def _evaluate_crop(self, crop, inputs, climate, ranking, is_primary):
        state, season = inputs["state"], inputs["season"]
        ml = ranking["ml"].get(crop)
        reg = ranking["regional"].get(crop)
        out = {"crop": crop, "role": "primary" if is_primary else "alternative"}
        reasons = []
        if ml:
            out["suitability_confidence_pct"] = ml["confidence"]
            out["suitability_kind"] = "model"
            out["season"] = ml.get("season")
            out["water_requirement"] = ml.get("water_requirement")
            out["market_demand"] = ml.get("market_demand")
            out["description"] = ml.get("description")
            reasons.append(f"Soil/climate model confidence {ml['confidence']:.0f}%")
        else:
            info = self.crop_model.crop_info.get(crop, {})
            if info:
                out.update({"season": info.get("season"), "water_requirement": info.get("water_requirement"),
                            "market_demand": info.get("market_demand"), "description": info.get("description")})
        if reg:
            reasons.append(f"widely grown in {state} in {'all seasons' if reg.get('whole_year') else season} "
                           f"(about {reg['median_area_ha']:,.0f} ha typically, from {reg['records']} yearly records)")
        if ml and ml.get("season") and season.lower() not in ml["season"].lower() \
                and "perennial" not in ml["season"].lower():
            out["season_warning"] = (f"{crop.title()} is typically a {ml['season']} crop; you selected {season}.")
        out["soil_fit"] = self._soil_fit(crop, inputs, climate)
        if out["soil_fit"].get("covered") and inputs["soil_complete"]:
            reasons.append(f"soil/climate fit: {out['soil_fit']['verdict'].lower()} "
                           f"({out['soil_fit']['within']}/{out['soil_fit']['checked']} parameters in typical range)")

        # economics preview (per acre) for comparing crops
        preview = None
        try:
            y = self.yield_model.get_expected_yield(crop, state=state, season=season)
            p = self._price_estimate(crop, state)
            if y.get("covered"):
                out["expected_yield_tonnes_per_acre"] = round(y["predicted_yield_tonnes_per_ha"] * ACRE_TO_HA, 2)
                reasons.append(f"model-expected yield {out['expected_yield_tonnes_per_acre']} t/acre")
            if y.get("covered") and p.get("covered"):
                price = p["predicted_modal_price"]
                out["price_rs_per_quintal"] = price
                preview = {"revenue_per_acre_expected": round(
                    y["predicted_yield_tonnes_per_ha"] * ACRE_TO_HA * 10 * price)}
                out["revenue_per_acre_expected_rs"] = preview["revenue_per_acre_expected"]
            elif y.get("covered"):
                out["price_note"] = "No price data for this crop - revenue can't be compared."
        except Exception as e:
            print(f"[decision_engine] preview failed for {crop}: {e}")
        out["economics_preview"] = preview
        out["why"] = "; ".join(reasons) if reasons else "Limited data available for this crop."
        return out

    # ------------------------------ sections ---------------------------- #
    def _soil_section(self, inputs, crop, climate):
        if not inputs["soil_complete"]:
            return {"available": False, "kind": "unavailable",
                    "message": "Enter N, P, K and pH from a soil test to get a soil health score, nutrient "
                               "deficiencies and a soil-based suitability check.",
                    "suitability": self._soil_fit(crop, inputs, climate)}
        health = analyze_soil(inputs["n"], inputs["p"], inputs["k"], inputs["ph"], inputs["organic_carbon"])
        return {"available": True, "kind": "reference", "health": health,
                "deficiencies": health["deficiencies"],
                "suitability": self._soil_fit(crop, inputs, climate),
                "soil_type": inputs["soil_type"],
                "note": "Nutrient classes use Soil Health Card bands (kg/ha). General guidance - confirm "
                        "dosage with a soil-testing lab."}

    def _fertilizer_section(self, crop, area):
        plan = get_fertilizer_plan(crop, area_acres=area)
        if not plan["covered"]:
            return {"available": False, "kind": "unavailable", "message": plan["message"].split(" Currently")[0]}
        return {"available": True, "kind": "reference", **plan}

    def _irrigation_section(self, crop, inputs, wx):
        if not wx["available"]:
            return {"available": False, "kind": "unavailable", "message": wx["reason"]}
        advice = self.water.get_irrigation_advice(crop_type=crop, soil_type=(inputs["soil_type"] or "").lower(),
                                                  weather_forecast=wx["forecast"])
        profile = self.water.irrigation_profiles.get(crop)
        return {"available": True, "kind": "live", "advice": advice,
                "summary": irrigation_summary(advice["irrigation_schedule"]),
                "uses_crop_profile": bool(profile),
                "note": ("Crop-specific irrigation profile." if profile else
                         "No crop-specific irrigation profile for this crop - a general profile was used."),
                "method": "Rule-based water balance (simplified evapotranspiration minus forecast rainfall)."}

    def _weather_section(self, wx, crop):
        if not wx["available"]:
            return {"available": False, "kind": "unavailable", "message": wx["reason"]}
        fc = wx["forecast"]
        precautions = []
        for d in fc:
            date_s, rain = d.get("date", ""), d.get("rainfall") or 0
            temp, hum, wind = d.get("temperature"), d.get("humidity"), d.get("wind_speed")
            if rain >= 35:
                precautions.append({"date": date_s, "severity": "high", "type": "heavy_rain",
                                    "text": f"Heavy rain (~{rain:.0f} mm). Check field drainage and bunds; postpone "
                                            f"spraying, sowing and fertilizer."})
            elif rain >= 15:
                precautions.append({"date": date_s, "severity": "moderate", "type": "rain",
                                    "text": f"Rain (~{rain:.0f} mm). Hold top-dressing fertilizer and spraying - "
                                            f"nutrients wash off and sprays are lost."})
            if temp is not None and temp >= 38:
                precautions.append({"date": date_s, "severity": "high" if temp >= 42 else "moderate", "type": "heat",
                                    "text": f"Hot day (~{temp:.0f}°C average). Irrigate early morning or evening, "
                                            f"avoid midday field work, consider mulching."})
            if hum is not None and temp is not None and hum >= 85 and 20 <= temp <= 30:
                precautions.append({"date": date_s, "severity": "moderate", "type": "fungal",
                                    "text": f"Humid ({hum:.0f}%) and mild - favours fungal disease. Scout leaves, "
                                            f"avoid evening overhead irrigation, keep rows airy."})
            if wind is not None and wind >= 25:
                precautions.append({"date": date_s, "severity": "moderate", "type": "wind",
                                    "text": f"Strong wind (~{wind:.0f} km/h). Don't spray - drift wastes product "
                                            f"and can harm neighbours."})
        spray_ok = [d["date"] for d in fc if (d.get("rainfall") or 0) < 2 and
                    (d.get("wind_speed") is None or d["wind_speed"] < 20)]
        return {"available": True, "kind": "live", "source": wx.get("source"), "current": wx["current"],
                "forecast": fc, "alerts": wx["alerts"], "precautions": precautions,
                "spray_windows": spray_ok,
                "rule_note": "Precautions come from fixed thresholds applied to the live forecast "
                             "(rain 15/35 mm, heat 38/42°C, humidity 85%, wind 25 km/h)."}

    def _yield_section(self, crop, inputs, area):
        y = self.yield_model.get_expected_yield(crop, state=inputs["state"], season=inputs["season"])
        manual = inputs.get("manual_yield_t_per_acre")
        if not y.get("covered"):
            if manual:
                total = round(manual * area, 2)
                return {"available": True, "kind": "measured", "area_acres": area,
                        "per_hectare": {"expected": round(manual / ACRE_TO_HA, 2), "low": round(manual / ACRE_TO_HA, 2),
                                        "high": round(manual / ACRE_TO_HA, 2)},
                        "total_tonnes": {"expected": total, "low": total, "high": total},
                        "model_r2": None, "model_mae_t_per_ha": None, "using_manual_yield": True,
                        "note": f"No yield model for '{crop}', so this uses the yield you entered "
                                f"({manual:g} t/acre) - there is no error range because it isn't a model estimate."}
            return {"available": False, "kind": "unavailable",
                    "message": f"No yield model for '{crop}' (it covers 46 crops). Enter your own expected yield "
                               f"(tonnes per acre) to estimate revenue."}
        ha = area * ACRE_TO_HA
        pred = y["predicted_yield_tonnes_per_ha"]
        mae = y.get("test_mae_tonnes_per_ha") or 0
        lo_ha = max(0.0, pred - mae)
        hi_ha = pred + mae
        return {
            "available": True, "kind": "model",
            "per_hectare": {"expected": pred, "low": round(lo_ha, 2), "high": round(hi_ha, 2)},
            "total_tonnes": {"expected": round(pred * ha, 2), "low": round(lo_ha * ha, 2),
                             "high": round(hi_ha * ha, 2)},
            "area_acres": area,
            "observed_state_range_t_per_ha": y["observed_range_tonnes_per_ha"],
            "observed_median_t_per_ha": y["observed_median_tonnes_per_ha"],
            "model_r2": y["test_r2"], "model_mae_t_per_ha": mae,
            "state_used": y["state_used"], "season_used": y["season_used"],
            "note": (f"Low/high bracket the model's average error (±{mae:.2f} t/ha on held-out data). Weather "
                     f"and your own practices are not model inputs - the estimate reflects typical results for "
                     f"{y['state_used']}, {y['season_used']}."),
        }

    def _market_section(self, crop, inputs):
        est = self._price_estimate(crop, inputs["state"])
        manual = inputs["manual_price_rs_per_quintal"]
        out = {"available": False, "kind": "unavailable", "crop": crop}
        if est.get("covered"):
            live = "live" in str(est.get("data_source", "")).lower() and "ml-predicted" not in \
                str(est.get("data_source", "")).lower() and "observed" not in str(est.get("data_source", "")).lower()
            kind = "live" if live else ("model" if est.get("test_r2") is not None else "observed")
            out = {"available": True, "kind": kind, "crop": crop,
                   "price_rs_per_quintal": est["predicted_modal_price"],
                   "observed_range": est.get("observed_price_range"),
                   "mae_rs_per_quintal": est.get("test_mae_rs_per_quintal"),
                   "model_r2": est.get("test_r2"), "sample_size": est.get("sample_size"),
                   "state_used": est.get("state_used"), "data_source": est.get("data_source")}
            if est.get("test_r2") is not None and est["test_r2"] < 0.5:
                out["accuracy_warning"] = (f"This price model is weak (held-out R² {est['test_r2']:.2f}) - treat "
                                           f"it as a rough guide only.")
        elif not manual:
            out["message"] = (est.get("message") or "No price data for this crop.")
            out["message"] = out["message"].split(" Add more")[0] + " Enter your own expected price to see revenue."
        if manual:
            out["manual_price_rs_per_quintal"] = manual
            out["using_manual_price"] = True
            if not out["available"]:
                out.update({"available": True, "kind": "measured", "price_rs_per_quintal": manual,
                            "data_source": "price you entered"})
        # real nearby market prices (observed records) when we have coordinates
        lat, lon = inputs["lat"], inputs["lon"]
        if lat is not None and lon is not None:
            try:
                nearby = self.market.get_nearby_markets(crop, lat, lon, max_results=3)
                if nearby.get("covered") and nearby.get("markets"):
                    out["nearby_markets"] = nearby["markets"][:3]
            except Exception as e:
                print(f"[decision_engine] nearby markets failed: {e}")
        return out

    def _economics(self, crop, inputs, fert, yld, mkt, area):
        costs, unknown = [], []
        if fert.get("available"):
            costs.append({"item": "Fertilizer (standard dose)", "amount_rs": fert["total_approx_cost_rs"],
                          "kind": "reference",
                          "basis": "Standard dose x approximate reference bag prices - confirm with your dealer."})
        else:
            unknown.append("fertilizer (no standard dose reference for this crop)")
        labels = {"seeds": "Seeds", "labour": "Labour", "pesticides": "Pesticides", "water": "Irrigation / water",
                  "other": "Other costs"}
        for k, label in labels.items():
            if k in inputs["entered_costs"]:
                costs.append({"item": label, "amount_rs": inputs["entered_costs"][k], "kind": "measured",
                              "basis": "Entered by you."})
            elif k != "other":
                unknown.append(label.lower())
        total_known = round(sum(c["amount_rs"] or 0 for c in costs), 0)

        out = {"costs": costs, "total_known_costs_rs": total_known, "costs_not_estimated": unknown,
               "kind": "model"}

        price = mkt.get("price_rs_per_quintal") if mkt.get("available") else None
        if not (yld.get("available") and price):
            out["revenue"] = None
            out["profit"] = None
            reasons = []
            if not yld.get("available"):
                reasons.append("no yield estimate for this crop")
            if not price:
                reasons.append("no price data (enter your expected price to unlock this)")
            out["message"] = "Revenue and profit can't be estimated: " + " and ".join(reasons) + "."
            return out

        t = yld["total_tonnes"]
        mae_p = mkt.get("mae_rs_per_quintal")
        rng = mkt.get("observed_range")
        if mae_p:
            p_lo, p_hi = max(1, price - mae_p), price + mae_p
        elif rng and not mkt.get("using_manual_price") and mkt["kind"] != "measured":
            p_lo, p_hi = rng[0], rng[1]
        else:
            p_lo = p_hi = price
        rev = {"low": round(t["low"] * 10 * p_lo), "expected": round(t["expected"] * 10 * price),
               "high": round(t["high"] * 10 * p_hi)}
        out["revenue"] = rev
        out["price_used_rs_per_quintal"] = {"low": round(p_lo), "expected": round(price), "high": round(p_hi)}
        out["profit"] = {k: round(v - total_known) for k, v in rev.items()}
        out["profit_label"] = "Revenue minus the costs listed above"
        caveats = ["These are estimates built from model error margins, not guarantees; the real outcome can "
                   "fall outside this range."]
        if unknown:
            caveats.append("Not included (not entered by you and not estimated by KrushiMitra): "
                           + ", ".join(unknown) + ". Actual profit will be lower by the amount you spend on these.")
        if mkt.get("accuracy_warning"):
            caveats.append(mkt["accuracy_warning"])
        out["caveats"] = caveats
        out["per_acre"] = {"revenue_expected": round(rev["expected"] / area), "known_costs": round(total_known / area)}
        return out

    def _calendar_section(self, crop, inputs, irr):
        sowing = datetime.strptime(inputs["sowing_date"], "%Y-%m-%d").date()
        profile = self.water.irrigation_profiles.get(crop, self.water.default_profile)
        cal = get_crop_calendar(crop, sowing, irrigation_interval_days=profile["interval_days"])
        if not cal.get("covered"):
            return {"available": False, "kind": "unavailable", "message": cal["message"].split(" Currently")[0]}
        return {"available": True, "kind": "reference", **cal}

    # ------------------------------ 7-day plan -------------------------- #
    def _seven_day_plan(self, crop, inputs, wx, irr, fert, calendar, soil):
        today = date.today()
        sowing = datetime.strptime(inputs["sowing_date"], "%Y-%m-%d").date()
        forecast = wx.get("forecast") if wx["available"] else None
        sched = irr["advice"]["irrigation_schedule"] if irr.get("available") else []
        events = calendar.get("events", []) if calendar.get("available") else []
        days = []
        for i in range(7):
            d = today + timedelta(days=i)
            fc = forecast[i] if forecast and i < len(forecast) else None
            date_s = (fc.get("date") if fc and fc.get("date") else d.isoformat())
            tasks = []
            rain = (fc.get("rainfall") or 0) if fc else None
            wind = fc.get("wind_speed") if fc else None

            # soil prep ahead of sowing
            days_to_sowing = (sowing - d).days
            if 0 <= days_to_sowing <= 6 and crop not in PERENNIAL_CROPS:
                if days_to_sowing == 0:
                    msg = f"Sow {crop}"
                    if rain is not None and rain >= 15:
                        msg += f" - heavy rain forecast (~{rain:.0f} mm); consider delaying a day or two"
                    tasks.append({"type": "sowing", "text": msg, "basis": "your sowing date"})
                elif days_to_sowing in (1, 2):
                    tasks.append({"type": "prep", "text": f"Prepare the seedbed and arrange seed and inputs "
                                                           f"(sowing in {days_to_sowing} day"
                                                           f"{'s' if days_to_sowing > 1 else ''})",
                                  "basis": "your sowing date"})
            if i == 0 and soil.get("available"):
                h = soil["health"]
                if h.get("organic_carbon_status") == "Low" and days_to_sowing >= 0:
                    tasks.append({"type": "soil", "text": "Work farmyard manure / compost into the soil before sowing "
                                                          "(organic carbon is low)", "basis": "soil test"})
                if h["ph_status"] == "Acidic" and days_to_sowing >= 0:
                    tasks.append({"type": "soil", "text": "Apply agricultural lime ahead of sowing (soil is acidic)",
                                  "basis": "soil test"})
                elif h["ph_status"] == "Alkaline" and days_to_sowing >= 0:
                    tasks.append({"type": "soil", "text": "Apply gypsum ahead of sowing (soil is alkaline)",
                                  "basis": "soil test"})

            # crop calendar events landing on this date
            for ev in events:
                if ev["date"] == d.isoformat():
                    if ev["type"] == "fertilizer":
                        stage = ev["label"].replace("Fertilizer: ", "")
                        items = [x for x in (fert.get("items") or []) if x["stage"] == stage]
                        if items:
                            qty = ", ".join(f"{x['fertilizer']} {x['quantity_kg']} kg" for x in items)
                            txt = f"Fertilizer - {stage}: {qty}"
                        else:
                            txt = ev["label"]
                        if rain is not None and rain >= 15:
                            txt += " (heavy rain forecast - hold off, apply on the next dry day)"
                        tasks.append({"type": "fertilizer", "text": txt, "basis": "crop calendar + fertilizer plan"})
                    elif ev["type"] == "harvest":
                        tasks.append({"type": "harvest", "text": "Expected harvest date", "basis": "crop calendar"})

            # irrigation from live water balance
            if i < len(sched):
                s = sched[i]
                if s["irrigation_needed"]:
                    tasks.append({"type": "irrigation", "text": f"Irrigate about {s['water_amount_mm']} mm "
                                                                 f"(early morning or evening)", "basis": s["reason"]})
                else:
                    tasks.append({"type": "irrigation", "text": "Skip irrigation", "basis": s["reason"]})

            # weather-driven
            if fc:
                if rain >= 35:
                    tasks.append({"type": "drainage", "text": "Check drainage channels and bunds", "basis": "heavy rain forecast"})
                if fc.get("humidity") is not None and fc.get("temperature") is not None \
                        and fc["humidity"] >= 85 and 20 <= fc["temperature"] <= 30:
                    tasks.append({"type": "scouting", "text": "Scout leaves for fungal disease signs",
                                  "basis": "humid, mild weather"})
                elif i % 3 == 1:
                    tasks.append({"type": "scouting", "text": "Routine field scouting for pests and disease",
                                  "basis": "regular practice"})
                if rain < 2 and (wind is None or wind < 20):
                    tasks.append({"type": "spray_window", "text": "Good day for any planned spraying",
                                  "basis": "dry and calm"})
            elif i % 3 == 1:
                tasks.append({"type": "scouting", "text": "Routine field scouting for pests and disease",
                              "basis": "regular practice"})

            days.append({
                "day": i + 1, "date": date_s,
                "weather": ({"summary": fc.get("weather"), "temperature": fc.get("temperature"),
                             "rain_mm": rain, "humidity": fc.get("humidity")} if fc else None),
                "tasks": tasks,
            })
        return {"kind": "reference" if not forecast else "live", "days": days,
                "note": ("Built from your sowing date, the crop calendar, the fertilizer plan and the live "
                         "7-day forecast." if forecast else
                         "Live weather unavailable - tasks are based on your sowing date and the crop calendar only.")}

    # ------------------------------ risks ------------------------------- #
    def _risks(self, crop, inputs, wx, soil, yld, mkt, climate, ranking):
        risks = []
        def add(level, kind, text):
            risks.append({"level": level, "category": kind, "text": text})

        if wx["available"]:
            heavy = [a for a in wx["alerts"] if a["severity"] == "high"]
            for a in heavy[:3]:
                add("high", "weather", a["message"])
            if not heavy and wx["alerts"]:
                add("medium", "weather", wx["alerts"][0]["message"])
        else:
            add("medium", "data", "Live weather was unavailable, so weather risks could not be assessed.")

        if soil.get("available"):
            h = soil["health"]
            if h["deficiencies"]:
                add("medium", "soil", f"Low nutrients: {', '.join(h['deficiencies'])}. Yield suffers if not corrected.")
            if h["ph_status"] != "Optimal":
                add("medium", "soil", f"Soil is {h['ph_status'].lower()} (pH {inputs['ph']:g}) - nutrient uptake "
                                      f"is reduced until corrected.")
            if h["soil_health_score"] < 40:
                add("high", "soil", f"Soil health score is low ({h['soil_health_score']}/100).")
        fit = soil.get("suitability") or {}
        if fit.get("covered") and fit["verdict"] == "Poor fit" and inputs["soil_complete"]:
            add("high", "suitability", f"Your soil/climate values sit outside {crop.title()}'s typical range on most "
                                       f"parameters - consider one of the alternatives.")

        ml = ranking["ml"].get(crop)
        if ml and ml.get("season") and inputs["season"].lower() not in ml["season"].lower() \
                and "perennial" not in ml["season"].lower():
            add("medium", "season", f"{crop.title()} is typically a {ml['season']} crop but the plan is for {inputs['season']}.")

        if yld.get("available"):
            spread = yld["per_hectare"]["high"] - yld["per_hectare"]["low"]
            if yld["per_hectare"]["expected"] and spread / yld["per_hectare"]["expected"] > 0.6:
                add("medium", "yield", "The yield estimate is uncertain (wide error margin) - plan for the low "
                                       "end when budgeting.")
        else:
            add("low", "data", "No yield model for this crop, so output can't be estimated.")

        if mkt.get("accuracy_warning"):
            add("medium", "market", mkt["accuracy_warning"])
        elif not mkt.get("available"):
            add("medium", "market", "No price data - revenue is unknown. Check your local mandi before committing.")
        else:
            add("low", "market", "Mandi prices move with arrivals and season; the price at harvest may differ "
                                 "from today's.")

        if ranking["ml"].get(crop) and climate["rainfall"] is not None:
            water = (ranking["ml"][crop].get("water_requirement") or "").lower()
            if water == "high" and climate["rainfall"] < 60:
                add("medium", "water", f"{crop.title()} needs a lot of water and recent monthly rainfall is only "
                                       f"~{climate['rainfall']:.0f} mm - secure irrigation before sowing.")

        diseases = DISEASE_REFERENCE.get(crop, [])
        if diseases:
            names = ", ".join(d["disease"].split(" (")[0] for d in diseases[:4])
            add("low", "disease", f"Common diseases to watch for in {crop}: {names}. Scout regularly; the Disease "
                                  f"Check tool can help match symptoms.")
        if not CROP_FERTILIZER_PLAN.get(crop):
            add("low", "data", "No standard fertilizer reference for this crop - ask a local expert for a dose.")
        return risks

    def _headline(self, primary, ranking, inputs, econ):
        crop = primary["crop"].title()
        area = inputs["area_acres"]
        if ranking.get("selected_by_user"):
            base = f"Plan for {crop} on {area:g} acre{'s' if area != 1 else ''} ({inputs['season']})."
        elif ranking["basis_kind"] == "model":
            conf = primary.get("suitability_confidence_pct")
            if conf is not None and conf < 50:
                base = (f"{crop} is the closest soil-and-climate match, but the model is not confident "
                        f"({conf:.0f}%) - compare the alternatives below before deciding.")
            else:
                base = (f"{crop} is the best soil-and-climate match" +
                        (f" (model confidence {conf:.0f}%)" if conf is not None else "") +
                        f" for {area:g} acre{'s' if area != 1 else ''} this {inputs['season']} season.")
        else:
            base = (f"{crop} is the most widely grown crop in {inputs['state']} in the {inputs['season']} season - "
                    f"add a soil test for a soil-based pick.")
        if econ.get("profit"):
            p = econ["profit"]
            def _m(v):
                return f"-₹{abs(v):,}" if v < 0 else f"₹{v:,}"
            base += (f" Estimated revenue minus known costs: {_m(p['low'])} to {_m(p['high'])} "
                     f"(an estimate, not a guarantee).")
        return base

    # ----------------------------- AI explanation ----------------------- #
    def compact_facts(self, plan):
        """A small, number-faithful digest of the plan for the language model."""
        p = plan
        crop = p["summary"]["primary_crop"]
        facts = {
            "crop": crop, "area_acres": p["summary"]["area_acres"], "season": p["summary"]["season"],
            "season_assumed_from_date": p["summary"]["season_inferred"],
            "state": p["summary"].get("state"), "ranking_basis": p["summary"]["ranking_basis"],
            "alternatives": [{"crop": a["crop"], "why": a["why"]} for a in p["crops"]["alternatives"][:4]],
            "soil": ({"health_score": p["soil"]["health"]["soil_health_score"],
                      "deficiencies": p["soil"]["deficiencies"], "ph_status": p["soil"]["health"]["ph_status"],
                      "fit_verdict": (p["soil"].get("suitability") or {}).get("verdict")}
                     if p["soil"].get("available") else "not assessed - soil test not provided"),
            "fertilizer": ({"total_approx_cost_rs": p["fertilizer"]["total_approx_cost_rs"],
                            "items": [f"{i['stage']}: {i['fertilizer']} {i['quantity_kg']} kg"
                                      for i in p["fertilizer"]["items"]]}
                           if p["fertilizer"].get("available") else "no standard dose reference"),
            "irrigation": (p["irrigation"]["summary"]["message"] if p["irrigation"].get("available") else "unavailable"),
            "weather_precautions": [x["text"] for x in (p["weather"].get("precautions") or [])[:5]]
            if p["weather"].get("available") else "live weather unavailable",
            "yield_total_tonnes (model estimate, low/expected/high)": p["yield"].get("total_tonnes")
            if p["yield"].get("available") else "unavailable",
            "yield_model_r2": p["yield"].get("model_r2") if p["yield"].get("available") else None,
            "price_rs_per_quintal": p["market"].get("price_rs_per_quintal") if p["market"].get("available") else "unavailable",
            "price_data_kind": p["market"].get("kind"),
            "costs_included": [f"{c['item']}: ₹{c['amount_rs']:,.0f}" for c in p["economics"]["costs"]],
            "costs_not_included": p["economics"]["costs_not_estimated"],
            "revenue_rs (estimate low/expected/high)": p["economics"].get("revenue"),
            "profit_rs (revenue minus included costs; estimate)": p["economics"].get("profit"),
            "next_7_days": [{"date": d["date"], "tasks": [t["text"] for t in d["tasks"]]}
                            for d in p["seven_day_plan"]["days"]],
            "top_risks": [r["text"] for r in p["risks"][:6]],
            "data_gaps": p["data_gaps"], "data_quality_notes": p["data_quality"],
        }
        return facts

    EXPLAIN_SYSTEM = (
        "You are KrushiMitra AI, explaining a computed farming plan to a farmer in plain, friendly language. "
        "Use ONLY the facts in the JSON. Never add numbers, prices, doses or dates that are not in it. "
        "Always call model outputs 'estimated' and mention that results can differ. Never promise or guarantee "
        "profit or yield. Be explicit about anything marked unavailable or missing and what the farmer can "
        "enter to improve it. Write these short sections with these exact headings: "
        "'Summary', 'Why this crop', 'This week', 'Money (estimate)', 'Watch-outs'. "
        "Use short sentences and simple bullets. Under 320 words."
    )

    def explain(self, user_id, plan_id, language="en"):
        plan = self.get_plan(user_id, plan_id)
        if not plan:
            return {"success": False, "error": "Plan not found."}
        if plan.get("explanation"):
            return {"success": True, "explanation": plan["explanation"], "cached": True}
        if not self.gemini.configured:
            return {"success": False, "reason": "not_configured",
                    "error": "AI explanation needs GEMINI_API_KEY (the plan itself above is fully computed "
                             "without it)."}
        names = {"en": "English", "hi": "Hindi", "kn": "Kannada", "mr": "Marathi", "ta": "Tamil", "te": "Telugu"}
        facts = json.dumps(self.compact_facts(plan), ensure_ascii=False, default=str)
        res = self.gemini.generate(
            [{"role": "user", "parts": [{"text": f"Reply language: {names.get((language or 'en')[:2], 'English')}\n\n"
                                                  f"PLAN FACTS (JSON):\n{facts}"}]}],
            system=self.EXPLAIN_SYSTEM, max_tokens=1600, temperature=0.3)
        if not res.get("ok"):
            return {"success": False, "error": res.get("error", "The explanation service is unavailable.")}
        conn = self.get_db()
        conn.execute("UPDATE decision_plans SET explanation = ? WHERE id = ? AND user_id = ?",
                     (res["text"], plan_id, user_id))
        conn.commit()
        conn.close()
        return {"success": True, "explanation": res["text"], "model_used": res.get("model_used")}
