"""
knowledge_base.py
--------------------
Static reference content: articles, best practices, organic farming and
pest management notes, and real government scheme references.

Two deliberate omissions from the original spec, both to avoid shipping
something fake:
  - "Videos": I have no web-search/fetch tool available in this build to
    find and verify real video URLs, and guessing YouTube links would
    almost certainly produce dead or wrong links. Instead, each topic
    below has a suggested search term the farmer can use themselves.
  - Government scheme details (amounts, eligibility): these change over
    time and I can't verify today's figures without a live search. Only
    the scheme's real name, purpose, and official government URL are
    given — the app tells the user to confirm current details there,
    rather than stating a number that might be stale or wrong.
"""

ARTICLES = [
    {"title": "Reading your soil test report",
     "summary": "What N, P, K, pH, and organic carbon numbers actually mean for what you can grow, "
                 "and why a single test isn't the whole picture over a growing season.",
     "search_term": "how to read soil health card India"},
    {"title": "Crop rotation basics",
     "summary": "Why alternating cereal and legume crops across seasons helps soil nitrogen and "
                 "breaks pest/disease cycles that build up when the same crop is grown repeatedly.",
     "search_term": "crop rotation benefits India"},
    {"title": "Understanding irrigation scheduling",
     "summary": "The idea behind 'how much and when' to irrigate — matching water applied to what "
                 "the crop is actually losing to evapotranspiration, not a fixed calendar.",
     "search_term": "irrigation scheduling evapotranspiration basics"},
    {"title": "Post-harvest storage losses",
     "summary": "A large share of crop value in India is lost after harvest, not before it — basic "
                 "drying, cleaning, and storage practices that reduce spoilage before sale.",
     "search_term": "post harvest storage best practices India"},
]

BEST_PRACTICES = [
    "Soil-test before every season, not just once — nutrient status changes with what you grew last.",
    "Match variety to season and local rainfall pattern rather than always using the same seed source.",
    "Time nitrogen application to growth stages (basal + top-dressing) instead of one large dose — "
    "it reduces both waste and leaching into groundwater.",
    "Scout fields regularly for early pest/disease signs — early intervention is cheaper and more "
    "effective than late-stage treatment.",
    "Keep basic records (what you planted, when, input costs, yield) — a season-over-season pattern "
    "is far more useful than any single season's number.",
]

ORGANIC_FARMING = [
    "Vermicompost and farmyard manure (FYM) rebuild organic carbon that chemical fertilizer alone "
    "doesn't replace — apply before sowing, worked into the topsoil.",
    "Green manuring (growing and ploughing in a legume crop like dhaincha or sunhemp before the main "
    "crop) is a low-cost way to add nitrogen and organic matter together.",
    "Neem-based sprays (neem oil, neem seed kernel extract) are a widely used organic option for "
    "many sucking pests — effectiveness varies by pest, so scout before assuming it worked.",
    "Trichoderma and Pseudomonas-based biofungicides are commonly used organic seed/soil treatments "
    "for reducing certain soil-borne fungal diseases.",
    "Converting fully to organic typically comes with a transition-period yield dip before soil "
    "biology rebuilds — budget for that rather than expecting an immediate even trade.",
]

PEST_MANAGEMENT = [
    "Yellow sticky traps help monitor and reduce whitefly/aphid populations without broad-spectrum "
    "spraying.",
    "Pheromone traps for pests like pink bollworm (cotton) or fruit borer help you time spraying to "
    "actual pest pressure instead of a fixed calendar.",
    "Rotate pesticide chemical classes across a season rather than repeating the same one — repeated "
    "use of one mode of action is the main driver of resistance building up in a pest population.",
    "Border/trap cropping (planting a pest-attractive crop around the field edge) can reduce pressure "
    "on the main crop for some pest species.",
    "Always follow the pre-harvest interval on any pesticide label — the gap between last application "
    "and safe harvest exists for a real residue-safety reason.",
]

# Real, well-known Indian central government agricultural schemes. Only
# name/purpose/official URL are given — amounts and eligibility rules
# change, so the app points to the source instead of stating a number.
GOVERNMENT_SCHEMES = [
    {"name": "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)",
     "purpose": "Direct income support to landholding farmer families, paid in installments.",
     "official_url": "https://pmkisan.gov.in"},
    {"name": "PMFBY (Pradhan Mantri Fasal Bima Yojana)",
     "purpose": "Crop insurance scheme covering yield loss from natural calamities, pests, and diseases.",
     "official_url": "https://pmfby.gov.in"},
    {"name": "Kisan Credit Card (KCC)",
     "purpose": "Short-term formal credit for crop production and allied needs at concessional interest.",
     "official_url": "https://www.myscheme.gov.in"},
    {"name": "Soil Health Card Scheme",
     "purpose": "Periodic soil testing and nutrient recommendations issued to farmers — the same N/P/K "
                "bands this app's soil health tool uses come from this scheme's classification.",
     "official_url": "https://soilhealth.dac.gov.in"},
    {"name": "PMKSY (Pradhan Mantri Krishi Sinchayee Yojana)",
     "purpose": "Irrigation infrastructure and water-use-efficiency support, including micro-irrigation "
                "(drip/sprinkler) subsidy.",
     "official_url": "https://pmksy.gov.in"},
    {"name": "e-NAM (National Agriculture Market)",
     "purpose": "Online trading platform linking mandis across states for more transparent price discovery.",
     "official_url": "https://enam.gov.in"},
]

DISCLAIMER = (
    "Scheme names, purposes, and URLs above are real and current as of this app's last update, but "
    "amounts, eligibility criteria, and application windows change — always confirm current details "
    "on the official site before applying."
)

# Coarse, broadly-stable eligibility framing per scheme. This is
# intentionally NOT a precise legal eligibility determination — exact
# rules (income-tax-payer exclusions, land ceiling changes, notified crop
# lists per district, etc.) change over time and I have no live search
# tool in this build to verify today's exact criteria. This checker gives
# an indicative "likely eligible to look into" signal on a few stable,
# widely-known factors, and always says to confirm on the official portal.
ELIGIBILITY_RULES = {
    "PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)": {
        "requires": ["owns_land"],
        "excludes": ["income_tax_payer", "government_employee"],
        "note": "Broadly for landholding farmer families; several categories (income-tax payers, "
                "government employees/pensioners above a certain level, institutional landholders) "
                "are typically excluded. Exact rules are on the official portal.",
    },
    "PMFBY (Pradhan Mantri Fasal Bima Yojana)": {
        "requires": ["grows_notified_crop"],
        "excludes": [],
        "note": "For farmers growing crops notified for insurance in their district/season — both "
                "landowners and tenant/sharecropper farmers can typically apply.",
    },
    "Kisan Credit Card (KCC)": {
        "requires": ["owns_land"],
        "excludes": [],
        "note": "Open to farmers, tenant farmers, and sharecroppers with cultivable land or a lease/"
                "crop-sharing arrangement — check with your bank branch for documentation needed.",
    },
    "Soil Health Card Scheme": {
        "requires": [],
        "excludes": [],
        "note": "Open to all farmers — apply through your local agriculture department for soil "
                "sample collection.",
    },
    "PMKSY (Pradhan Mantri Krishi Sinchayee Yojana)": {
        "requires": ["owns_land"],
        "excludes": [],
        "note": "Micro-irrigation subsidy component generally applies to farmers with land eligible "
                "for drip/sprinkler installation — subsidy percentage varies by state and category.",
    },
    "e-NAM (National Agriculture Market)": {
        "requires": [],
        "excludes": [],
        "note": "Open to farmers selling through a mandi registered on the e-NAM platform.",
    },
}


def check_eligibility(owns_land=False, grows_notified_crop=False, income_tax_payer=False,
                       government_employee=False):
    facts = {
        "owns_land": owns_land, "grows_notified_crop": grows_notified_crop,
        "income_tax_payer": income_tax_payer, "government_employee": government_employee,
    }
    results = []
    for scheme in GOVERNMENT_SCHEMES:
        rule = ELIGIBILITY_RULES.get(scheme["name"])
        if not rule:
            continue
        meets_requirements = all(facts.get(r) for r in rule["requires"])
        hits_exclusion = any(facts.get(e) for e in rule["excludes"])
        likely_eligible = meets_requirements and not hits_exclusion
        results.append({
            "scheme": scheme["name"], "official_url": scheme["official_url"],
            "likely_eligible": likely_eligible, "note": rule["note"],
        })
    return {
        "results": results,
        "disclaimer": "This is an indicative check on a few broad, stable factors — not a legal "
                       "eligibility determination. Confirm on each scheme's official portal before applying.",
    }


def get_knowledge_base():
    return {
        "articles": ARTICLES, "best_practices": BEST_PRACTICES, "organic_farming": ORGANIC_FARMING,
        "pest_management": PEST_MANAGEMENT, "government_schemes": GOVERNMENT_SCHEMES,
        "disclaimer": DISCLAIMER,
        "videos_note": "No verified video links are included — search the suggested term for each "
                       "article on YouTube directly rather than trusting an unverified link here.",
    }
