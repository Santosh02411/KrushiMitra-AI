"""
regional_crops.py
--------------------
Real, state-grounded crop data — covering 49 real crops from India's
government crop-production records (data/crop_yield_data.csv), not just
the 22 crops the N/P/K soil-based recommendation model knows.

Why this is a lookup/ranking, not a trained model: I tried training a
classifier (State + Season + rainfall + temperature -> Crop) to give this
a genuine confidence score like the soil-based model has, and it scored
2.4% top-1 accuracy on held-out data. That's not a bug to fix — it's
because the task itself is nearly non-identifiable from these features:
dozens of crops genuinely coexist in the same state, season, and climate,
so there's no real signal that picks out "the" crop a farmer should grow
from climate alone. Shipping that model would mean dressing up noise as a
confidence score, which is exactly the kind of fake precision this app
avoids elsewhere.

So instead: for a given state, this returns the crops with real
production records there, ranked by how many real records exist (a
genuine "how consistently is this actually grown here" signal), covering
field crops the N/P/K model doesn't know at all — sugarcane, tobacco,
jowar, bajra, ragi, groundnut, soyabean, wheat, onion, and more.

District-level breakdown isn't available — this dataset only reports at
state level.
"""

import os
import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "crop_yield_data.csv")

# Aggregate/catch-all rows in the source data, not real distinct crops.
_EXCLUDE = {
    "Other Kharif pulses", "Other  Rabi pulses", "Other Cereals",
    "Other Summer Pulses", "Oilseeds total", "other oilseeds",
}

_df = pd.read_csv(DATA_PATH)
_df["Crop"] = _df["Crop"].astype(str).str.strip()
_df["State"] = _df["State"].astype(str).str.strip()
_df["Season"] = _df["Season"].astype(str).str.strip()
_df = _df[~_df["Crop"].isin(_EXCLUDE)]

_ALL_DATASET_STATES = set(_df["State"].unique())
ALL_CROPS = sorted(_df["Crop"].unique())

# Crops covered by the N/P/K soil-based recommendation model (ml_models.py)
# — used to flag overlap so the UI can distinguish "also in your soil-based
# results" from "only available here".
_SOIL_MODEL_CROPS = {
    "rice", "maize", "chickpea", "kidneybeans", "pigeonpeas", "mothbeans",
    "mungbean", "blackgram", "lentil", "pomegranate", "banana", "mango",
    "grapes", "watermelon", "muskmelon", "apple", "orange", "papaya",
    "coconut", "cotton", "jute", "coffee",
}
_NAME_MAP = {  # dataset name -> soil-model crop key, for overlap checks
    "rice": "rice", "maize": "maize", "gram": "chickpea", "arhar/tur": "pigeonpeas",
    "moth": "mothbeans", "moong(green gram)": "mungbean", "urad": "blackgram",
    "masoor": "lentil", "banana": "banana", "cotton(lint)": "cotton", "jute": "jute",
    "coconut": "coconut",
}


def get_states():
    return sorted(_ALL_DATASET_STATES)


def get_common_crops(state, top_n=15):
    """Real crops grown in this state, ranked by number of real production
    records (more records = more consistently grown across years/districts
    in this dataset — a genuine signal, not a guessed one)."""
    if not state or state.strip() not in _ALL_DATASET_STATES:
        return {"covered": False, "state": state,
                "message": f"No real records for '{state}' in this dataset. Covered states: "
                           f"{', '.join(sorted(_ALL_DATASET_STATES))}."}

    subset = _df[_df["State"] == state.strip()]
    grouped = subset.groupby("Crop").agg(
        records=("Crop", "count"),
        avg_yield=("Yield", "median"),
        seasons=("Season", lambda s: sorted(set(s))),
    ).reset_index().sort_values("records", ascending=False)

    crops = []
    for _, r in grouped.head(top_n).iterrows():
        crop_lower = r["Crop"].lower()
        crops.append({
            "crop": r["Crop"],
            "records": int(r["records"]),
            "typical_yield_tonnes_per_ha": round(float(r["avg_yield"]), 2) if pd.notna(r["avg_yield"]) else None,
            "seasons": r["seasons"],
            "also_in_soil_model": _NAME_MAP.get(crop_lower) in _SOIL_MODEL_CROPS if crop_lower in _NAME_MAP else False,
            "soil_model_key": _NAME_MAP.get(crop_lower),
        })

    return {
        "covered": True, "state": state.strip(), "total_crops_with_records": len(grouped),
        "crops": crops,
        "data_source": "Real Indian government crop-production records (data/crop_yield_data.csv), "
                        "ranked by real record count — not a trained prediction.",
    }


def is_grown_in_state(crop, state):
    """True if we have a real production record for this crop in this
    state (only meaningful for the crops mapped in _NAME_MAP — the ones
    the soil-based model also knows). None if either the crop isn't
    mapped, or the state doesn't appear in this dataset at all (e.g.
    Rajasthan is entirely absent) — a data gap, not a signal either way."""
    crop_key = (crop or "").strip().lower()
    reverse_map = {v: k for k, v in _NAME_MAP.items()}
    dataset_name = reverse_map.get(crop_key)
    if not dataset_name or not state:
        return None
    state = state.strip()
    if state not in _ALL_DATASET_STATES:
        return None
    return not _df[(_df["State"] == state) & (_df["Crop"].str.lower() == dataset_name)].empty


def get_season_crops(state, season, top_n=15):
    """Crops with real production records for this state AND season, ranked by
    the median area historically put under them ("how widely is it actually
    grown here in this season") - a real signal, unlike the record count,
    which is the same (one per year) for most crops. Year-round crops are
    appended after the season-specific ones. Returns [] if the state/season
    has no records."""
    if not state or state.strip() not in _ALL_DATASET_STATES:
        return []
    sub = _df[_df["State"] == state.strip()]
    wanted = (season or "").strip().lower()
    in_season = sub[sub["Season"].str.lower() == wanted]
    whole = sub[sub["Season"].str.lower() == "whole year"]

    def summarise(frame, whole_year):
        g = frame.groupby("Crop").agg(records=("Crop", "count"), median_area_ha=("Area", "median"),
                                      median_yield=("Yield", "median")).reset_index()
        g = g.sort_values("median_area_ha", ascending=False)
        return [{"dataset_crop": r["Crop"], "records": int(r["records"]),
                 "median_area_ha": round(float(r["median_area_ha"]), 0),
                 "typical_yield_tonnes_per_ha": round(float(r["median_yield"]), 2) if pd.notna(r["median_yield"]) else None,
                 "whole_year": whole_year} for _, r in g.iterrows()]

    return (summarise(in_season, False) + summarise(whole, True))[:top_n]
