"""
crop_calendar.py
------------------
Given a sowing date and a crop, computes real calendar dates for sowing,
fertilizer applications, irrigation, and harvest — using published typical
crop-duration figures and the fertilizer/irrigation schedules already
defined in fertilizer_recommendation.py and ml_models.WaterManagementAdvisor.

This is arithmetic on real reference data (crop duration in days, growth
stage timing), not a prediction — the same sowing date always produces the
same calendar. Perennial crops (mango, banana, coconut, etc.) don't fit a
single sow-to-harvest cycle, so they get a simpler seasonal-care summary
instead of a fabricated one-shot harvest date.
"""

from datetime import timedelta

from fertilizer_recommendation import CROP_FERTILIZER_PLAN

# Typical total duration (days from sowing to harvest) for annual/seasonal
# crops, per common published agronomic references.
CROP_DURATION_DAYS = {
    "rice": 130, "wheat": 120, "maize": 95, "cotton": 165, "chickpea": 105,
    "lentil": 105, "pigeonpeas": 165, "mothbeans": 70, "mungbean": 65,
    "blackgram": 80, "jute": 110, "watermelon": 85, "muskmelon": 85,
    # Additional annual/seasonal crops (typical published duration figures —
    # actual timing shifts with variety, region, and season):
    "bajra": 80, "barley": 130, "castor": 165, "coriander": 100, "cowpea": 70,
    "chilli": 165, "garlic": 160, "ginger": 225, "groundnut": 110, "guar": 95,
    "horsegram": 105, "jowar": 110, "khesari": 120, "linseed": 120, "mesta": 135,
    "niger": 100, "onion": 140, "potato": 100, "ragi": 120, "mustard": 125,
    "safflower": 135, "sunnhemp": 100, "sesame": 90, "small millets": 85,
    "soybean": 100, "sugarcane": 365, "sunflower": 90, "sweet potato": 100,
    "tapioca": 270, "tobacco": 130, "turmeric": 240,
}

PERENNIAL_CROPS = {"banana", "mango", "grapes", "apple", "orange", "papaya",
                    "coconut", "coffee", "pomegranate", "arecanut", "black pepper",
                    "cardamom", "cashewnut"}

# Rough day-in-stage parser for the fertilizer schedule's "stage" labels
# (e.g. "Tillering (~25-30 days)") -> a representative day offset from sowing.
def _stage_day_offset(stage_label):
    if "sowing" in stage_label.lower() or "transplanting" in stage_label.lower() or "planting" in stage_label.lower():
        return 0
    import re
    nums = re.findall(r"\d+", stage_label)
    if nums:
        return sum(int(n) for n in nums) // len(nums)
    return None


def get_crop_calendar(crop, sowing_date, irrigation_interval_days=None):
    """sowing_date: a date object. irrigation_interval_days: from
    ml_models.WaterManagementAdvisor's irrigation_profiles, passed in by the
    caller so this module doesn't need to import that class directly."""
    crop_key = (crop or "").strip().lower()

    if crop_key in PERENNIAL_CROPS:
        return {
            "covered": True, "crop": crop_key, "type": "perennial",
            "message": f"{crop_key.title()} is a perennial crop, so it doesn't follow a single "
                       f"sowing-to-harvest cycle — care windows repeat every year once established.",
            "events": [],
        }

    duration = CROP_DURATION_DAYS.get(crop_key)
    if not duration:
        return {"covered": False, "crop": crop,
                "message": f"No standard duration reference for '{crop}' yet. Currently covers: "
                           f"{', '.join(CROP_DURATION_DAYS.keys())}."}

    events = [{"date": sowing_date.isoformat(), "type": "sowing", "label": "Sowing"}]

    fert_plan = CROP_FERTILIZER_PLAN.get(crop_key)
    if fert_plan:
        seen_stages = set()
        for step in fert_plan["schedule"]:
            if step["stage"] in seen_stages:
                continue
            seen_stages.add(step["stage"])
            offset = _stage_day_offset(step["stage"])
            if offset is None:
                continue
            events.append({
                "date": (sowing_date + timedelta(days=offset)).isoformat(),
                "type": "fertilizer", "label": f"Fertilizer: {step['stage']}",
            })

    if irrigation_interval_days:
        day = irrigation_interval_days
        while day < duration:
            events.append({
                "date": (sowing_date + timedelta(days=day)).isoformat(),
                "type": "irrigation", "label": "Irrigation window",
            })
            day += irrigation_interval_days

    harvest_date = sowing_date + timedelta(days=duration)
    events.append({"date": harvest_date.isoformat(), "type": "harvest", "label": "Expected harvest"})

    events.sort(key=lambda e: e["date"])
    return {
        "covered": True, "crop": crop_key, "type": "annual", "duration_days": duration,
        "sowing_date": sowing_date.isoformat(), "expected_harvest_date": harvest_date.isoformat(),
        "events": events,
        "reference": "Duration and stage timing from standard published agronomic references for this "
                     "crop. Actual dates shift with variety, weather, and local practice.",
    }
