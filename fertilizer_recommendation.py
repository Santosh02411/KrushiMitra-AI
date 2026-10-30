"""
fertilizer_recommendation.py
------------------------------
Crop-specific fertilizer plan: which fertilizer, how much, roughly what it
costs, and when to apply it.

This is reference data from standard published package-of-practices
fertilizer doses (the kind of N-P-K-per-hectare recommendation issued by
Indian state agricultural universities / ICAR for major crops), converted
to per-acre quantities and split into a basal + top-dressing schedule.
Costs are APPROXIMATE representative market prices for common fertilizer
bags — clearly labeled as such, since real prices vary by state, dealer,
and subsidy changes over time. This is general guidance, not a substitute
for a local input dealer's current price list.

Coverage: the crops with an established standard N-P-K package-of-practices
figure — 36 crops as of this version. Anything else returns covered=False
rather than a guessed number. Long-duration plantation/spice crops (arecanut,
cardamom, black pepper, cashewnut) are deliberately left out even though
they're covered elsewhere in the app (yield model, crop calendar) — their
real-world fertilizer programs are multi-year and variety/spacing-dependent
in a way a single per-acre figure would misrepresent.
"""

# Approx representative retail price per 50kg bag (Rs.) — general reference,
# not live pricing. Government-notified MRPs (Urea/DAP/MOP) are widely
# published; actual price at your dealer may differ.
BAG_PRICE_RS = {
    "Urea": 266, "DAP": 1350, "MOP": 1700, "SSP": 500, "Complex (NPK 20:20:0:13)": 1470,
}
BAG_SIZE_KG = 50

# Standard recommended N-P-K dose in kg/acre for major crops (typical
# package-of-practices figures), plus which fertilizers are conventionally
# used to supply it and the usual application timing.
CROP_FERTILIZER_PLAN = {
    "rice": {"n_kg_acre": 48, "p_kg_acre": 24, "k_kg_acre": 24,
              "schedule": [
                  {"stage": "Basal (at transplanting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at transplanting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                  {"stage": "Basal (at transplanting)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                  {"stage": "Tillering (~25-30 days)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                  {"stage": "Panicle initiation (~45-50 days)", "fertilizer": "Urea", "share": 0.34, "of": "N"},
                  {"stage": "Panicle initiation (~45-50 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
              ]},
    "wheat": {"n_kg_acre": 48, "p_kg_acre": 24, "k_kg_acre": 16,
              "schedule": [
                  {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                  {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                  {"stage": "First irrigation (~20-25 days)", "fertilizer": "Urea", "share": 0.25, "of": "N"},
                  {"stage": "Second irrigation (~40-45 days)", "fertilizer": "Urea", "share": 0.25, "of": "N"},
              ]},
    "maize": {"n_kg_acre": 48, "p_kg_acre": 20, "k_kg_acre": 16,
              "schedule": [
                  {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                  {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.25, "of": "N"},
                  {"stage": "Knee-high (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                  {"stage": "Tasseling (~45-50 days)", "fertilizer": "Urea", "share": 0.25, "of": "N"},
                  {"stage": "Tasseling (~45-50 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
              ]},
    "cotton": {"n_kg_acre": 40, "p_kg_acre": 20, "k_kg_acre": 20,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.25, "of": "N"},
                   {"stage": "Squaring (~40-45 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "Flowering (~60-70 days)", "fertilizer": "Urea", "share": 0.25, "of": "N"},
                   {"stage": "Flowering (~60-70 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
               ]},
    "chickpea": {"n_kg_acre": 8, "p_kg_acre": 20, "k_kg_acre": 0,
                 "schedule": [
                     {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                     {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                 ]},
    "lentil": {"n_kg_acre": 8, "p_kg_acre": 16, "k_kg_acre": 0,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
               ]},
    "pigeonpeas": {"n_kg_acre": 10, "p_kg_acre": 20, "k_kg_acre": 0,
                   "schedule": [
                       {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                       {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                   ]},
    "mungbean": {"n_kg_acre": 8, "p_kg_acre": 16, "k_kg_acre": 0,
                 "schedule": [
                     {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                     {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                 ]},
    "blackgram": {"n_kg_acre": 8, "p_kg_acre": 16, "k_kg_acre": 0,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                  ]},
    "jute": {"n_kg_acre": 24, "p_kg_acre": 8, "k_kg_acre": 8,
             "schedule": [
                 {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                 {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                 {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                 {"stage": "~30 days after sowing", "fertilizer": "Urea", "share": 0.5, "of": "N"},
             ]},
    "banana": {"n_kg_acre": 80, "p_kg_acre": 12, "k_kg_acre": 120,
               "schedule": [
                   {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Every 2 months (year 1)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                   {"stage": "Every 2 months (year 1)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
               ]},
    "watermelon": {"n_kg_acre": 32, "p_kg_acre": 16, "k_kg_acre": 16,
                   "schedule": [
                       {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                       {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                       {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                       {"stage": "Vining stage (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                       {"stage": "Vining stage (~25-30 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                   ]},
    "muskmelon": {"n_kg_acre": 32, "p_kg_acre": 16, "k_kg_acre": 16,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                      {"stage": "Vining stage (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                      {"stage": "Vining stage (~25-30 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                  ]},
    # Additional crops — standard published package-of-practices N-P-K
    # doses (ICAR / state agricultural university figures, converted
    # kg/ha -> kg/acre), same approximate-cost caveat as above.
    "groundnut": {"n_kg_acre": 8, "p_kg_acre": 16, "k_kg_acre": 0,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                  ]},
    "soybean": {"n_kg_acre": 8, "p_kg_acre": 24, "k_kg_acre": 8,
                "schedule": [
                    {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                    {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                    {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                ]},
    "sunflower": {"n_kg_acre": 24, "p_kg_acre": 12, "k_kg_acre": 12,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                      {"stage": "Budding stage (~30-35 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                  ]},
    "mustard": {"n_kg_acre": 32, "p_kg_acre": 16, "k_kg_acre": 16,
                "schedule": [
                    {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                    {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                    {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                    {"stage": "First irrigation (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                ]},
    "sugarcane": {"n_kg_acre": 112, "p_kg_acre": 36, "k_kg_acre": 56,
                  "schedule": [
                      {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at planting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                      {"stage": "Basal (at planting)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                      {"stage": "Tillering (~45-60 days)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                      {"stage": "Grand growth (~90-120 days)", "fertilizer": "Urea", "share": 0.34, "of": "N"},
                      {"stage": "Grand growth (~90-120 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                  ]},
    "onion": {"n_kg_acre": 40, "p_kg_acre": 20, "k_kg_acre": 20,
              "schedule": [
                  {"stage": "Basal (at transplanting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at transplanting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                  {"stage": "Basal (at transplanting)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                  {"stage": "~30 days after transplanting", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                  {"stage": "Bulb formation (~60 days)", "fertilizer": "Urea", "share": 0.34, "of": "N"},
                  {"stage": "Bulb formation (~60 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
              ]},
    "potato": {"n_kg_acre": 48, "p_kg_acre": 32, "k_kg_acre": 40,
               "schedule": [
                   {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at planting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                   {"stage": "Basal (at planting)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "Earthing-up (~30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "Earthing-up (~30 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
               ]},
    "sesame": {"n_kg_acre": 16, "p_kg_acre": 8, "k_kg_acre": 0,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
               ]},
    "bajra": {"n_kg_acre": 20, "p_kg_acre": 8, "k_kg_acre": 0,
              "schedule": [
                  {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                  {"stage": "Tillering (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
              ]},
    "jowar": {"n_kg_acre": 32, "p_kg_acre": 16, "k_kg_acre": 0,
              "schedule": [
                  {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                  {"stage": "Tillering (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
              ]},
    "ragi": {"n_kg_acre": 18, "p_kg_acre": 8, "k_kg_acre": 0,
             "schedule": [
                 {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                 {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                 {"stage": "Tillering (~25-30 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
             ]},
    "barley": {"n_kg_acre": 24, "p_kg_acre": 12, "k_kg_acre": 0,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "First irrigation (~20-25 days)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
               ]},
    "castor": {"n_kg_acre": 24, "p_kg_acre": 8, "k_kg_acre": 8,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "~30-40 days after sowing", "fertilizer": "Urea", "share": 0.5, "of": "N"},
               ]},
    "turmeric": {"n_kg_acre": 24, "p_kg_acre": 20, "k_kg_acre": 48,
                 "schedule": [
                     {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                     {"stage": "Basal (at planting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                     {"stage": "Basal (at planting)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                     {"stage": "~90 days after planting", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                     {"stage": "Rhizome development (~135 days)", "fertilizer": "Urea", "share": 0.34, "of": "N"},
                     {"stage": "Rhizome development (~135 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                 ]},
    "ginger": {"n_kg_acre": 30, "p_kg_acre": 20, "k_kg_acre": 20,
               "schedule": [
                   {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at planting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                   {"stage": "Basal (at planting)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                   {"stage": "~60 days after planting", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                   {"stage": "Rhizome development (~90 days)", "fertilizer": "Urea", "share": 0.34, "of": "N"},
                   {"stage": "Rhizome development (~90 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
               ]},
    "garlic": {"n_kg_acre": 40, "p_kg_acre": 20, "k_kg_acre": 20,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "~30-45 days after sowing", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                   {"stage": "~30-45 days after sowing", "fertilizer": "MOP", "share": 0.5, "of": "K"},
               ]},
    "chilli": {"n_kg_acre": 40, "p_kg_acre": 20, "k_kg_acre": 20,
               "schedule": [
                   {"stage": "Basal (at transplanting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at transplanting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                   {"stage": "Basal (at transplanting)", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                   {"stage": "~30 days after transplanting", "fertilizer": "Urea", "share": 0.33, "of": "N"},
                   {"stage": "Flowering (~60 days)", "fertilizer": "Urea", "share": 0.34, "of": "N"},
                   {"stage": "Flowering (~60 days)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
               ]},
    "sweet potato": {"n_kg_acre": 20, "p_kg_acre": 10, "k_kg_acre": 20,
                     "schedule": [
                         {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                         {"stage": "Basal (at planting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                         {"stage": "Basal (at planting)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                         {"stage": "~30 days after planting", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                         {"stage": "~30 days after planting", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                     ]},
    "tobacco": {"n_kg_acre": 20, "p_kg_acre": 20, "k_kg_acre": 40,
                "schedule": [
                    {"stage": "Basal (at transplanting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                    {"stage": "Basal (at transplanting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                    {"stage": "Basal (at transplanting)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                    {"stage": "~30 days after transplanting", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                    {"stage": "~30 days after transplanting", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                ]},
    "coriander": {"n_kg_acre": 16, "p_kg_acre": 8, "k_kg_acre": 0,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                  ]},
    "safflower": {"n_kg_acre": 16, "p_kg_acre": 8, "k_kg_acre": 0,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                  ]},
    "linseed": {"n_kg_acre": 16, "p_kg_acre": 8, "k_kg_acre": 0,
                "schedule": [
                    {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                    {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                ]},
    "niger": {"n_kg_acre": 8, "p_kg_acre": 8, "k_kg_acre": 0,
              "schedule": [
                  {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
              ]},
    "guar": {"n_kg_acre": 8, "p_kg_acre": 16, "k_kg_acre": 0,
             "schedule": [
                 {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                 {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
             ]},
    "cowpea": {"n_kg_acre": 8, "p_kg_acre": 16, "k_kg_acre": 0,
               "schedule": [
                   {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                   {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
               ]},
    "horsegram": {"n_kg_acre": 4, "p_kg_acre": 8, "k_kg_acre": 0,
                  "schedule": [
                      {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                      {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                  ]},
    "khesari": {"n_kg_acre": 6, "p_kg_acre": 8, "k_kg_acre": 0,
                "schedule": [
                    {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                    {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                ]},
    "sunnhemp": {"n_kg_acre": 4, "p_kg_acre": 8, "k_kg_acre": 0,
                 "schedule": [
                     {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                     {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                 ]},
    "mesta": {"n_kg_acre": 24, "p_kg_acre": 8, "k_kg_acre": 8,
              "schedule": [
                  {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                  {"stage": "Basal (at sowing)", "fertilizer": "MOP", "share": 1.0, "of": "K"},
                  {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                  {"stage": "~30 days after sowing", "fertilizer": "Urea", "share": 0.5, "of": "N"},
              ]},
    "small millets": {"n_kg_acre": 8, "p_kg_acre": 8, "k_kg_acre": 0,
                      "schedule": [
                          {"stage": "Basal (at sowing)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                          {"stage": "Basal (at sowing)", "fertilizer": "Urea", "share": 1.0, "of": "N"},
                      ]},
    "tapioca": {"n_kg_acre": 40, "p_kg_acre": 20, "k_kg_acre": 40,
                "schedule": [
                    {"stage": "Basal (at planting)", "fertilizer": "DAP", "share": 1.0, "of": "P"},
                    {"stage": "Basal (at planting)", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                    {"stage": "Basal (at planting)", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                    {"stage": "~60 days after planting", "fertilizer": "Urea", "share": 0.5, "of": "N"},
                    {"stage": "~60 days after planting", "fertilizer": "MOP", "share": 0.5, "of": "K"},
                ]},
}


def get_fertilizer_plan(crop, area_acres=1.0):
    crop_key = (crop or "").strip().lower()
    plan = CROP_FERTILIZER_PLAN.get(crop_key)
    if not plan:
        return {
            "covered": False, "crop": crop,
            "message": f"No standard fertilizer dose reference for '{crop}' yet. Currently covers: "
                       f"{', '.join(CROP_FERTILIZER_PLAN.keys())}.",
        }

    area_acres = max(0.1, float(area_acres))
    totals_kg = {"N": plan["n_kg_acre"] * area_acres, "P": plan["p_kg_acre"] * area_acres,
                 "K": plan["k_kg_acre"] * area_acres}

    items = []
    for step in plan["schedule"]:
        nutrient_total = totals_kg[step["of"]]
        if nutrient_total <= 0:
            continue
        # Convert a nutrient-share into a physical fertilizer quantity via
        # its approximate nutrient content (Urea ~46% N, DAP ~46% P2O5 basis
        # simplified here as P, MOP ~60% K2O simplified as K) — standard
        # approximations used in these package-of-practices conversions.
        nutrient_content = {"Urea": 0.46, "DAP": 0.46, "MOP": 0.60}.get(step["fertilizer"], 1.0)
        physical_qty_kg = round((nutrient_total * step["share"]) / nutrient_content, 1)
        cost = round((physical_qty_kg / BAG_SIZE_KG) * BAG_PRICE_RS.get(step["fertilizer"], 0), 0)
        items.append({
            "fertilizer": step["fertilizer"], "stage": step["stage"],
            "quantity_kg": physical_qty_kg,
            "quantity_per_acre_kg": round(physical_qty_kg / area_acres, 1),
            "approx_cost_rs": cost,
        })

    total_cost = round(sum(i["approx_cost_rs"] for i in items), 0)
    return {
        "covered": True, "crop": crop_key, "area_acres": area_acres,
        "npk_target_kg": totals_kg, "items": items, "total_approx_cost_rs": total_cost,
        "reference": "Based on standard published package-of-practices N-P-K doses for this crop, "
                     "converted from per-acre nutrient targets to physical fertilizer quantities. "
                     "Costs are approximate representative market prices, not live pricing — confirm "
                     "with your local dealer.",
    }
