"""
soil_health.py
---------------
Rule-based soil health scoring and fertilizer guidance.

This is deliberately NOT dressed up as machine learning — nutrient
sufficiency ranges for soil testing are a well-established, published
standard (the ranges below follow the classification bands used by India's
Soil Health Card scheme for N/P/K, and standard organic-carbon bands used
in Indian soil testing labs). Treating a lookup-table classification as
"AI" would be exactly the kind of fake sophistication this project has
been trying to get away from — a transparent rule engine is the honest,
correct tool here.

All fertilizer quantities given are GENERAL guidance bands, not a
prescription for a specific field — the app says so, and recommends
confirming with a local soil-testing lab / Krishi Vigyan Kendra before
buying inputs, same as any published general guide would.
"""

# (low_max, medium_max) in kg/ha - values above medium_max are "high".
N_BANDS = (280, 560)     # Available Nitrogen, kg/ha
P_BANDS = (10, 25)       # Available Phosphorus (Olsen P), kg/ha
K_BANDS = (120, 280)     # Available Potassium, kg/ha
OC_BANDS = (0.5, 0.75)   # Organic Carbon, %

IDEAL_PH_RANGE = (6.0, 7.5)


def _classify(value, bands):
    low_max, medium_max = bands
    if value < low_max:
        return "Low"
    if value <= medium_max:
        return "Medium"
    return "High"


def analyze_soil(n, p, k, ph, organic_carbon=None):
    n_status = _classify(n, N_BANDS)
    p_status = _classify(p, P_BANDS)
    k_status = _classify(k, K_BANDS)
    oc_status = _classify(organic_carbon, OC_BANDS) if organic_carbon is not None else None

    ph_status = "Optimal"
    if ph < IDEAL_PH_RANGE[0]:
        ph_status = "Acidic"
    elif ph > IDEAL_PH_RANGE[1]:
        ph_status = "Alkaline"

    score = _health_score(n_status, p_status, k_status, oc_status, ph_status)
    deficiencies = [name for name, status in
                    [("Nitrogen", n_status), ("Phosphorus", p_status), ("Potassium", k_status),
                     ("Organic Carbon", oc_status)]
                    if status == "Low"]

    return {
        "nitrogen_status": n_status,
        "phosphorus_status": p_status,
        "potassium_status": k_status,
        "organic_carbon_status": oc_status,
        "ph_status": ph_status,
        "soil_health_score": score,
        "deficiencies": deficiencies,
        "fertilizer_recommendation": _fertilizer_recommendation(n_status, p_status, k_status, oc_status),
        "improvement_suggestions": _improvement_suggestions(n_status, p_status, k_status, oc_status, ph_status),
        "reference": "Bands follow India's Soil Health Card scheme classification for N/P/K "
                      "and standard organic-carbon bands used in Indian soil testing labs. "
                      "General guidance only — confirm exact dosage with a local soil-testing "
                      "lab or Krishi Vigyan Kendra before purchasing inputs.",
    }


def _health_score(n_status, p_status, k_status, oc_status, ph_status):
    """0-100 composite score. Transparent point scheme, not a trained model:
    each nutrient contributes up to 25 points (Low=0, Medium=15, High=25),
    scaled down to account for however many components were provided, then
    a pH penalty is applied for being outside the optimal range."""
    points_map = {"Low": 0, "Medium": 15, "High": 25}
    components = [n_status, p_status, k_status]
    if oc_status:
        components.append(oc_status)
    raw = sum(points_map[c] for c in components)
    max_raw = 25 * len(components)
    score = round((raw / max_raw) * 90)  # leave 10 points for pH

    if ph_status == "Optimal":
        score += 10
    elif ph_status in ("Acidic", "Alkaline"):
        score += 4
    return min(100, max(0, score))


def _fertilizer_recommendation(n_status, p_status, k_status, oc_status):
    recs = []
    if n_status == "Low":
        recs.append({"fertilizer": "Urea", "reason": "Nitrogen is low",
                      "guidance": "General guidance: ~100-130 kg/ha in split doses (basal + top-dressing)."})
    elif n_status == "Medium":
        recs.append({"fertilizer": "Urea", "reason": "Nitrogen is medium — a maintenance dose is usually enough",
                      "guidance": "General guidance: ~50-65 kg/ha."})

    if p_status == "Low":
        recs.append({"fertilizer": "DAP (Di-Ammonium Phosphate) or SSP", "reason": "Phosphorus is low",
                      "guidance": "General guidance: ~60-80 kg/ha as basal dose at sowing."})
    elif p_status == "Medium":
        recs.append({"fertilizer": "SSP (Single Super Phosphate)", "reason": "Phosphorus is medium",
                      "guidance": "General guidance: ~30-40 kg/ha as basal dose."})

    if k_status == "Low":
        recs.append({"fertilizer": "MOP (Muriate of Potash)", "reason": "Potassium is low",
                      "guidance": "General guidance: ~40-60 kg/ha as basal dose."})

    if oc_status == "Low":
        recs.append({"fertilizer": "Farmyard Manure (FYM) / Vermicompost", "reason": "Organic carbon is low",
                      "guidance": "General guidance: 5-10 tonnes/ha before sowing to rebuild soil organic matter."})

    if not recs:
        recs.append({"fertilizer": "None needed", "reason": "All measured nutrients are in the medium-to-high range",
                      "guidance": "Maintain current practice; retest each season."})
    return recs


def _improvement_suggestions(n_status, p_status, k_status, oc_status, ph_status):
    suggestions = []
    if oc_status == "Low":
        suggestions.append("Add organic matter (compost, FYM, green manure) to improve long-term soil structure "
                            "and nutrient retention.")
    if ph_status == "Acidic":
        suggestions.append("Soil is acidic — agricultural lime application can help raise pH toward the "
                            "6.0-7.5 optimal range.")
    elif ph_status == "Alkaline":
        suggestions.append("Soil is alkaline — gypsum application and avoiding over-irrigation with saline "
                            "water can help.")
    if n_status == "Low" and p_status == "Low" and k_status == "Low":
        suggestions.append("All three major nutrients are low — consider a full soil-test-based fertility "
                            "buildup plan rather than one-season correction.")
    if not suggestions:
        suggestions.append("Soil parameters are reasonably balanced — focus on maintaining organic matter "
                            "and testing every season to catch changes early.")
    return suggestions
