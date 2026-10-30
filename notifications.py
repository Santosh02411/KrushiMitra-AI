"""
notifications.py
-------------------
"Smart" notifications, all derived from data the app already computes for
real — nothing here is a separate prediction system:

  - Rain tomorrow: from the real weather forecast (day index 1).
  - Apply fertilizer today: from a saved crop_plans calendar (see
    farm_records.save_crop_plan) — checks whether today's date matches a
    fertilizer event in that plan.
  - Harvest time: same calendar, checks proximity to the harvest date.
  - Disease alert: NOT a diagnosis. This is a general fungal-disease-risk
    flag from real weather thresholds (high humidity + moderate
    temperature favor many fungal pathogens) — it tells the farmer
    conditions are worth watching, not that a specific disease is present.
    A confirmed disease match from disease_reference.py (if the farmer ran
    one) is surfaced here too, since that IS a real match already made.
"""

import json
from datetime import datetime, timedelta


def build_notifications(crop_plans, forecast, latest_disease_match=None):
    notifications = []

    # Rain tomorrow — from the real forecast, day index 1 (today is index 0).
    if forecast and len(forecast) > 1:
        tomorrow = forecast[1]
        rainfall = tomorrow.get("rainfall") or 0
        if rainfall >= 10:
            notifications.append({
                "type": "rain", "title": "Rain expected tomorrow",
                "message": f"~{rainfall}mm forecast for {tomorrow.get('date', 'tomorrow')} — consider "
                           f"delaying irrigation or spraying.",
            })

    # Fertilizer / harvest timing — from saved real crop calendars.
    today = datetime.now().date()
    for plan in (crop_plans or []):
        try:
            events = json.loads(plan.get("calendar_json") or "[]")
        except (json.JSONDecodeError, TypeError):
            events = []

        for ev in events:
            try:
                ev_date = datetime.strptime(ev["date"], "%Y-%m-%d").date()
            except (ValueError, KeyError):
                continue
            if ev.get("type") == "fertilizer" and ev_date == today:
                notifications.append({
                    "type": "fertilizer", "title": f"Apply fertilizer today — {plan['crop']}",
                    "message": ev.get("label", "Scheduled fertilizer application."),
                })

        if plan.get("harvest_date"):
            try:
                harvest = datetime.strptime(plan["harvest_date"], "%Y-%m-%d").date()
                days_to_harvest = (harvest - today).days
                if 0 <= days_to_harvest <= 3:
                    notifications.append({
                        "type": "harvest", "title": f"Harvest time approaching — {plan['crop']}",
                        "message": f"Expected harvest date is {plan['harvest_date']} "
                                   f"({days_to_harvest} day{'s' if days_to_harvest != 1 else ''} away).",
                    })
            except ValueError:
                pass

    # General fungal-disease-risk flag from real current weather — NOT a diagnosis.
    if forecast and len(forecast) > 0:
        today_weather = forecast[0]
        humidity = today_weather.get("humidity")
        temperature = today_weather.get("temperature")
        if humidity is not None and temperature is not None and humidity >= 85 and 20 <= temperature <= 30:
            notifications.append({
                "type": "disease_risk", "title": "Conditions favor fungal disease",
                "message": f"High humidity ({humidity}%) and moderate temperature ({temperature}°C) "
                           f"favor many fungal pathogens — scout your fields; this is a general risk "
                           f"flag, not a diagnosis.",
            })

    if latest_disease_match:
        notifications.append({
            "type": "disease_alert", "title": f"Possible match: {latest_disease_match['disease']}",
            "message": "From your last disease symptom check — see the Disease Check section for "
                       "treatment details.",
        })

    return notifications
