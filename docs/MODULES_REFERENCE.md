# Krushi — data-driven crop, soil, weather & market advisor

Krushi helps a farmer decide what to plant, how healthy their soil is, and
what it might fetch at market — using real trained ML models, real
government datasets, and live weather/location data. Every module states
plainly what is real and what is an explicitly-labeled fallback.

## Structure: separate pages, sign-in required

Every feature is its own page (`/recommend`, `/soil`, `/yield`, `/market`,
`/fertilizer`, `/profit`, `/disease`, `/water`, `/calendar`, `/dashboard`,
`/map`, `/knowledge`, `/chat`, `/about`, `/profile`) rather than one long
scrolling page — there's a persistent nav across all of them
(`templates/base.html`). **Every page and every feature API endpoint
requires a signed-in session** — `/login` is the only public page, and
`auth.page_login_required` / `auth.login_required` redirect or 401
anything else if you're not signed in.

## The 20 feature systems in this build

1. **User authentication** — registration/login, farmer profile, forgot
   password (real 3-step OTP-by-email flow), role-based access
   (farmer/admin), rate-limited login/register/reset endpoints
2. **Crop recommendation** — state/district/soil type/season inputs, top
   recommendation + 5 alternatives, expected yield, suitable season,
   profitability rating
3. **Weather integration** — live temperature/humidity/rainfall/wind/UV,
   today's weather, 7-day forecast, rain alerts, heatwave warnings
4. **Soil health analysis** — N/P/K/pH/organic carbon → health score,
   nutrient deficiency, fertilizer recommendation, improvement suggestions
5. **Market price prediction** — real current mandi prices by market
   (13 crops total: 3 ML-predicted + 10 with a real observed
   median/range), nearest real market to your location
6. **Fertilizer recommendation** — after picking a crop, which fertilizer,
   how much, roughly what it costs, and when to apply it (44 crops)
7. **Disease check** — symptom-based reference matching for 35 crops
   (see note below on why this isn't image AI)
8. **Photo/camera capture for disease records** — real upload/camera
   capture, kept for your reference, not analyzed by any model
9. **Irrigation recommendation + crop calendar** — 7-day irrigation
   schedule with a "Water Required / Next Irrigation" headline, plus a
   full sowing→fertilizer→irrigation→harvest calendar (57 crops: 44
   annual + 13 perennial)
10. **Standalone yield prediction** — area/crop/state/season → expected
    total yield in tonnes + the model's real held-out fit (46 crops)
11. **Profit estimation** — your entered expenses (seeds/fertilizer/
    labour/water/pesticides) vs. income from real yield × real price →
    net profit
12. **Farm dashboard** — charts built entirely from your own logged data:
    expenses by category, income vs. expenses, soil health history, water
    usage history
13. **Interactive farm map** — free Leaflet + OpenStreetMap (no API key),
    shows your real GPS location and real nearby markets
14. **Farming knowledge base** — articles, best practices, organic
    farming, pest management, real government scheme links, and an
    eligibility checker (indicative, not authoritative)
15. **Smart notifications** — real, clickable dropdown from the nav bar on
    every page (not just the home page): rain tomorrow, fertilizer due
    today, harvest approaching, and a general fungal-disease-risk weather
    flag, all derived from your saved crop calendars and real weather
16. **AI chatbot** — real Google Gemini API integration, free tier (needs
    your own free API key; says so honestly if unconfigured, doesn't fake
    a reply; automatically falls back through newer model IDs if one gets
    retired)
17. **Farm records** — crops grown, yield history, fertilizer usage,
    expenses, and income — including edit/delete on every entry, not just
    add
18. **Analytics** — monthly/yearly charts for yield, profit, water usage,
    and crop comparison, aggregated from your own real logs
19. **Admin panel** — manage farmers, view real crop/weather/market model
    status, post news announcements, extend the disease database, and a
    dashboard with active users / recommendations generated / disease
    scans (revenue is honestly reported as N/A — no billing system exists)
20. **UI in 6 languages** — English, Hindi, Kannada, Marathi, Tamil,
    Telugu. Navigation, footer, the home page, login/register/reset, and
    every page's heading are translated (116 keys × 6 languages); deeper
    body copy on individual tool pages is still English-only (see "Not in
    this build yet")

Everything auto-fills from your real GPS location where possible.

## What's real vs. labeled fallback

| Module | Data source | Status |
|---|---|---|
| Crop recommendation | [Crop Recommendation Dataset](https://raw.githubusercontent.com/Gladiator07/Harvestify/master/Data-processed/crop_recommendation.csv) — 2,200 real samples, 22 crops. | **Real.** `RandomForestClassifier`, held-out test accuracy shown live. |
| Expected yield | Real Indian government crop-production data, 1997-2020, all states (`data/crop_yield_data.csv`, 19,689 records). | **Real, covers 46 crops** (the dataset actually has 55 — coconut is excluded because it's recorded in nuts/hectare rather than tonnes/hectare like everything else, and 8 catch-all "other/misc" aggregate rows aren't a single identifiable crop). `RandomForestRegressor`, held-out R²=0.94. Other crops return an explicit "not covered" message. |
| Location | Browser GPS → reverse geocoding. | **Real, accurate.** IP-based lookup is kept only as a fallback, with an explicit accuracy warning. |
| Crop recommendation regional relevance | Real Indian government crop-production records (`data/crop_yield_data.csv`) — checked per state for the 12 crops shared with the N/P/K soil-based model. | **Real.** The N/P/K model has no location input at all; a state re-ranks its results using real "is this crop actually grown there" records, but never demotes a crop just because a record is missing — some states (e.g. Rajasthan) are entirely absent from this dataset, a data-completeness gap, not evidence against the crop. |
| "Commonly grown in your state" (49 crops) | Same dataset, full crop list — includes sugarcane, tobacco, jowar, bajra, ragi, groundnut, wheat, onion, and more that the N/P/K model doesn't know at all. | **Real — a ranked list, not a trained model.** I tried training a classifier (state + season + climate → crop) and it scored 2.4% top-1 accuracy on held-out data — the task is nearly non-identifiable from those features alone, since dozens of crops genuinely coexist in the same state/season/climate. Rather than dress up that noise as a confidence score, this ranks crops by real record count instead. See `regional_crops.py`. |
| Password reset email | Real SMTP send if `SMTP_HOST`/`SMTP_USER`/`SMTP_PASSWORD` are set in `.env` (e.g. a Gmail App Password). | **Real once configured.** Without SMTP credentials, the token is returned directly in the API response instead — clearly labeled as the dev-mode fallback, not a silent failure. |
| Weather (current, 7-day forecast, UV index) | [Open-Meteo](https://open-meteo.com), by exact GPS coordinates when available. | **Real, live**, no API key required. |
| Rain alerts / heatwave warnings | Rule-based thresholds applied to the real forecast above. | **Real, transparent logic.** |
| Soil health score / fertilizer guidance | India's Soil Health Card classification bands (published standard, not ML). | **Real reference ranges**, general guidance — not a substitute for a lab test. |
| Market prices (per real market) | Real Agmarknet mandi records (`data/market_prices_by_location.csv`), decoded to real market/state names. | **Real, covers 13 crops**: potato/tomato/wheat across 18 real markets in Haryana/Punjab/UP/Uttarakhand, plus onion/gram/cucumber/brinjal/cluster beans/bottle gourd/amaranthus/carrot/snake gourd/lemon pulled live from the official data.gov.in Agmarknet feed (real, dated records — Odisha/Tamil Nadu/Andhra Pradesh markets). |
| Market price prediction | Same dataset, `RandomForestRegressor`. | **Two honest tiers.** Potato/tomato/wheat get a real ML prediction (held-out R²=0.40, modest, shown honestly). The 10 crops above get a real *observed* median/range instead of an ML prediction — there are only a handful of real records for each, nowhere near enough to train and honestly test a regression on, so `market_model.py` reports the real number without dressing it up as a model output. With `MARKET_API_KEY` set, the market page's "Other" option queries data.gov.in live for **any** crop name — if a state-specific query returns nothing, it retries nationally rather than giving up, clearly labeled as a national (not state-specific) figure when that happens. **Note:** data.gov.in is frequently slow/unreachable from some networks; a request that would otherwise wait out a full timeout on every crop lookup instead trips a short circuit breaker after one failure and falls straight to the local model for the next couple of minutes — see `market_service.py`. |
| Nearest market | Real market coordinates (hardcoded for the confidently-identified towns in the dataset) + haversine distance from your GPS. | **Real**, for the 13 covered crops (where a market's town is confidently identifiable — a couple of ambiguous village names are left out rather than guessed). |
| Profitability rating | Expected yield × predicted price, ranked relative to other recommended crops. | **Real where both a yield estimate and a price estimate exist for a crop** — in practice this means the crop-recommendation set (22 crops), the yield set (46 crops) and the market set (13 crops) still don't fully overlap, so profitability shows "insufficient data" for some crops. See below. |
| Fertilizer plan (quantity/cost/schedule) | Published package-of-practices N-P-K doses for major crops, converted to physical fertilizer quantities and representative bag prices. | **Real reference data, covers 44 crops.** Costs are approximate, not live pricing. Long-duration plantation/spice crops (arecanut, cardamom, black pepper, cashewnut) are deliberately left out — their real fertilizer programs are multi-year and variety/spacing-dependent in a way a single per-acre figure would misrepresent. |
| Irrigation schedule + "Water Required / Next Irrigation" headline | Same rule-based water-balance calculation as before, now with a one-line summary derived from the same schedule. | **Real, transparent logic.** |
| Crop calendar (sowing/fertilizer/irrigation/harvest dates) | Published crop-duration and growth-stage timing references, plus the fertilizer/irrigation data above. | **Real arithmetic on real reference data, covers 44 annual crops + 13 perennial crops** (which get a simpler seasonal-care note instead of a fabricated single harvest date). |
| Disease check | A symptom-matching reference table for common diseases (35 crops), sourced from standard plant-pathology/extension knowledge. | **Real reference data — explicitly NOT image AI.** See below for why. |
| Disease photo / camera capture | Real file upload / browser camera capture. | **Real upload, stored for your own reference — not analyzed.** |
| Standalone yield prediction | Same yield_model.py as the crop advisor, converted to total tonnes for your entered area. | **Real, same 46-crop coverage.** "Accuracy" is the model's R² expressed as a percentage — labeled as such, not classification accuracy. |
| Profit estimation | Real yield × real price (or your entered price) minus your entered expenses. | **Real arithmetic on real/user inputs.** The yield-covered crops (46) and price-covered crops (13) still don't fully overlap, so some crops need you to enter an expected price — the app says so rather than guessing one. |
| Farm dashboard | Your own expense/income entries, plus auto-logged soil health scores, water usage, and yield predictions whenever you're signed in. | **Real, entirely your own data.** A new account's dashboard is empty — there's no demo/seed data. |
| Interactive farm map | Leaflet.js + OpenStreetMap tiles (free, no API key) + real market coordinates. | **Real.** "Nearby weather stations" is deliberately not shown — Open-Meteo is a model-based forecast service with no public physical station location data to show. |
| Knowledge base articles / best practices / organic farming / pest management | General agronomy reference content. | **Real, general knowledge**, not sourced from a live database. |
| Knowledge base government schemes | Real, well-known central government scheme names + official URLs. | **Real names/URLs.** Amounts and eligibility criteria aren't stated, since those change and I can't verify current figures without a live search tool in this build. |
| Knowledge base videos | — | **Deliberately omitted.** I have no web-search/fetch tool in this build to find and verify real video links, and guessing them risks shipping dead or wrong URLs. Each article has a suggested search term instead. |
| Eligibility checker | A coarse rule engine over a few stable, broadly-known factors (land ownership, notified crop, tax/employment status) per scheme. | **Indicative, not authoritative** — exact eligibility rules change and I can't verify today's criteria without a live search tool. Always says to confirm on the official portal. |
| Smart notifications | Real saved crop-calendar events (fertilizer/harvest dates) + real weather forecast + your last real disease-check result. | **Real, derived from data already computed elsewhere in the app** — no separate prediction system. The "disease risk" notification is a general weather-based flag (humidity/temperature thresholds that favor fungal disease), explicitly not a diagnosis. |
| AI chatbot | Real Google Gemini API call (`chat_service.py`, free tier, no credit card), with a system prompt describing what Krushi's own tools actually cover. | **Real, once you add `GEMINI_API_KEY`.** Without a key, the chat page says so plainly — it does not fall back to a scripted fake response. |
| Farm records (crops grown, yield, expenses, income, fertilizer usage) | Each pulled from its own real table — crops grown and yield populate automatically from the Crop Calendar and Yield Prediction tools; fertilizer usage is logged manually. | **Real, entirely your own data.** |
| Analytics (monthly/yearly yield, profit, crop comparison, water usage) | Real aggregation (sums/groupings) of the same logs behind Farm Records and the Farm Dashboard. | **Real arithmetic on real data** — no forecasting, no trend-fitting. |
| Admin: farmers / crops / weather / market panels | Real queries — user list, live model info, a live weather API call, live market model stats. | **Real, live.** |
| Admin: news | A real announcements table — admin posts, everyone sees on the home page. | **Real, but editorial content**, not an external news feed (no search tool available to pull real agri news). |
| Admin: disease database | The static reference table (read-only) plus a real form to add new crop/symptom/treatment entries, which immediately show up in the Disease Check tool. | **Real CRUD**, not a bigger pre-loaded database. |
| Admin dashboard: active users / recommendations / disease scans | Real SQL queries against the app's own tables ("active" = has a real log entry in the last 30 days). | **Real.** |
| Admin dashboard: revenue | — | **Explicitly N/A.** Krushi has no billing/subscription system in this build, so there is no real number to report — the dashboard says so instead of inventing one. |

### Why disease detection isn't an image classifier

I looked for a real, freely-usable pretrained plant-disease image model
before deciding this. I found one — a fastai-exported ResNet34 trained on
the PlantVillage dataset, from `github.com/imskr/Plant_Disease_Detection`
— and deliberately didn't use it: loading that `.pkl` export requires
fastai 1.x, which is unmaintained and doesn't install cleanly on modern
Python. Shipping it would mean either the app breaks on `pip install`, or
the feature silently doesn't work — both worse than not having it.
Training a new model from scratch would need downloading and training on
tens of thousands of PlantVillage images, which isn't realistic to do
honestly in this environment either. So `disease_reference.py` matches
described symptoms against a real reference table instead, and the photo
upload is real but is kept only as your own record, not analyzed. If you
get access to a real plant-disease image API later, it can slot in
alongside this without removing it.

### Why profitability often shows "insufficient data"

The crop-recommendation model, the yield model, and the market-price model
are each trained on a *different* real dataset, and those datasets don't
fully overlap. Profitability needs both a real yield number and a real
price number for the *same* crop — the yield model covers 46 crops and
the market model covers 13, but the crop-recommendation dataset's 22
crops still don't include potato, tomato, or wheat at all, so some
combinations still show "insufficient data" rather than an invented
number.

## Setup

1. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate   # venv\Scripts\activate on Windows
   pip install -r requirements.txt
   ```

2. Copy the environment template (all values are optional — the app runs
   with zero keys):
   ```bash
   cp .env.example .env
   ```

3. Run the app:
   ```bash
   python app.py
   ```

4. Open `http://localhost:5000`. Click **Use my GPS location** and allow
   the browser's location permission — that drives the weather, crop
   climate values, and nearest-market lookup.

5. (Optional) Create an admin account. Admin access is **not** available
   through the public registration form — it can only be granted by
   someone with direct access to the server:
   ```bash
   python scripts/create_admin.py you@example.com "Your Name" yourpassword
   ```

The first startup takes several seconds while all three ML models train on
their bundled real datasets (~40s on a single-core machine; a few seconds
on anything with more cores, since training uses all available):
```
[ml_models] Trained RandomForest on 2200 real samples across 22 crops |
held-out test accuracy=99.3% macro-F1=99.3%
[yield_model] Trained RandomForestRegressor on 17367 real APY records
(46 crops) | held-out R2=0.937 MAE=1.052 tonnes/ha
[market_model] Trained RandomForestRegressor on 6361 real mandi records
(Potato/Tomato/Wheat, 4 states) | held-out R2=0.402 MAE=Rs.474.6/quintal
```

## Project layout

```
krushi/
├── app.py                  # Flask routes for all 5 feature systems
├── auth.py                  # Registration/login/sessions/roles/password reset
├── ml_models.py              # Crop RandomForest + irrigation rule engine
├── yield_model.py            # Expected-yield RandomForestRegressor
├── market_model.py           # Market price model + real per-market lookup + nearest market
├── market_service.py         # Wraps market_model.py, optional live data.gov.in override
├── soil_health.py             # Rule-based soil scoring / fertilizer guidance
├── fertilizer_recommendation.py  # Crop-specific fertilizer quantity/cost/schedule
├── crop_calendar.py           # Sowing/fertilizer/irrigation/harvest date calculator
├── disease_reference.py       # Symptom-matching disease reference (not image AI)
├── weather_service.py        # Open-Meteo / OpenWeatherMap + rain/heatwave alerts
├── location_service.py       # Reverse geocoding (GPS) + IP fallback
├── farm_records.py            # Expense/income/soil/water/yield logs, crop plans, fertilizer usage, analytics
├── admin_tools.py             # Admin panel backend: news, disease DB entries, real usage stats
├── notifications.py           # Rain/fertilizer/harvest/disease-risk alerts, from real saved data
├── chat_service.py            # Real Google Gemini API chatbot integration (free tier)
├── knowledge_base.py          # Articles, schemes, eligibility checker
├── scripts/create_admin.py   # CLI-only admin account creation
├── scripts/test_email.py     # standalone SMTP test, independent of the web app
├── data/
│   ├── Crop_recommendation.csv       # real 2,200-row crop training dataset
│   ├── crop_yield_data.csv           # real 19,689-row national yield dataset
│   ├── market_price_data.csv         # real mandi price records (ML training)
│   ├── market_prices_by_location.csv # same data, decoded to real market names
│   ├── crop_info.json                # season / water need / market demand per crop
│   └── states_districts.json         # Indian states + districts for form dropdowns
├── templates/
│   ├── base.html              # shared nav/footer, extended by every page below
│   ├── login.html             # the only public page
│   ├── home.html, recommend.html, soil.html, yield.html, market.html,
│   │   fertilizer.html, profit.html, disease.html, water.html, calendar.html,
│   │   dashboard.html, records.html, analytics.html, map.html, knowledge.html,
│   │   chat.html, about.html, profile.html, admin.html
│   │   # one page per feature, all login-gated (admin.html: admin role only)
├── static/css/style.css
├── static/js/common.js        # runs on every page: nav logout, notif dropdown, i18n bootstrap
├── static/js/script.js        # all feature logic, one initXPage() per page
├── static/js/i18n.js          # data-i18n translation dictionaries (6 languages)
├── requirements.txt
├── Procfile                   # `web: gunicorn app:app ...` — for Railway/Render/etc.
└── .env.example
```

## API endpoints

**Auth**
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/auth/register` | POST | Create account (always role=farmer) |
| `/api/auth/login` | POST | Session login |
| `/api/auth/logout` | POST | Clear session |
| `/api/auth/me` | GET | Current session user |
| `/api/auth/profile` | PUT | Update farm profile (login required) |
| `/api/auth/forgot-password` | POST | Issues a reset token (returned directly — see note below) |
| `/api/auth/email-status` | GET | Live ✓/✗ whether SMTP is currently configured (no credentials exposed) |
| `/api/auth/forgot-password` | POST | Emails a 6-digit reset code (or returns it directly if SMTP isn't configured) |
| `/api/auth/verify-reset-code` | POST | Checks the code without consuming it — the reset form only unlocks after this succeeds |
| `/api/auth/reset-password` | POST | Consume the code, set a new password |
| `/api/admin/users` | GET | List farmers + usage stats (admin only) |

**Core**
| Endpoint | Method | Purpose |
|---|---|---|
| `/api/model-info` | GET | Real training/evaluation stats for all 3 ML models |
| `/api/reference-data` | GET | States/districts/soil types/seasons/languages for form dropdowns |
| `/api/regional-crops?state=` | GET | Real crops (49 total) grown in a state, ranked by record count |
| `/api/reverse-geocode?lat=&lon=` | GET | Real GPS coordinates → place name (preferred) |
| `/api/detect-location` | GET | IP-based fallback location (labeled as an estimate) |
| `/api/weather-by-coords?lat=&lon=` | GET | Live weather + 7-day forecast + alerts, by GPS |
| `/api/weather/<location>` | GET | Same, by place name |
| `/api/recommend-crops` | POST | Crop recommendations + yield + profitability |
| `/api/soil-health` | POST | Soil score, deficiencies, fertilizer guidance |
| `/api/water-management` | POST | 7-day irrigation schedule |
| `/api/market-trends/<crop>` | GET | ML-predicted price |
| `/api/market-prices/<crop>` | GET | Real per-market current prices |
| `/api/market-nearby/<crop>?lat=&lon=` | GET | Nearest real markets to your GPS location |
| `/api/fertilizer-plan` | POST | Crop-specific fertilizer quantity/cost/schedule |
| `/api/crop-calendar` | POST | Sowing/fertilizer/irrigation/harvest dates |
| `/api/disease-symptoms/<crop>` | GET | Symptom list to choose from for a crop |
| `/api/disease-check` | POST | Match selected symptoms to known diseases |
| `/api/disease-photo` | POST | Upload a photo (stored for reference, not analyzed) |
| `/api/yield-prediction` | POST | Standalone expected-yield tool |
| `/api/profit-estimation` | POST | Income − expenses = net profit |
| `/api/farm/expense` | POST | Log an expense (login required) |
| `/api/farm/expense/<id>` | PUT/DELETE | Edit or remove an expense entry (login required, own records only) |
| `/api/farm/income` | POST | Log income (login required) |
| `/api/farm/income/<id>` | PUT/DELETE | Edit or remove an income entry (login required, own records only) |
| `/api/farm/dashboard` | GET | Your dashboard data (login required) |
| `/api/knowledge-base` | GET | Articles/best practices/schemes/etc. |
| `/api/schemes/eligibility` | POST | Indicative scheme eligibility check |
| `/api/notifications?lat=&lon=` | GET | Rain/fertilizer/harvest/disease-risk alerts — also drives the nav bell dropdown on every page |
| `/api/chat` | POST | Chatbot reply (needs `GEMINI_API_KEY`, rate-limited to 20/hour) |
| `/api/farm/records` | GET | Crops grown / yield / expenses / income / fertilizer usage |
| `/api/farm/fertilizer-usage` | POST | Log a fertilizer application |
| `/api/farm/fertilizer-usage/<id>` | PUT/DELETE | Edit or remove a fertilizer-usage entry (login required, own records only) |
| `/api/farm/analytics?period=` | GET | Monthly/yearly aggregated analytics |
| `/api/news` | GET | Public announcements (read-only) |
| `/api/admin/stats` | GET | Real usage stats (admin only) |
| `/api/admin/crops` | GET | Live model coverage (admin only) |
| `/api/admin/weather-status` | GET | Live weather API check (admin only) |
| `/api/admin/news` | GET/POST | List/post announcements (admin only) |
| `/api/admin/disease-database` | GET/POST | View/add disease reference entries (admin only) |

All of the above (except the `/api/auth/*` endpoints) require a signed-in
session — every page route does too, redirecting to `/login` if you're not
signed in.

`POST /api/recommend-crops` body:
```json
{
  "location": "Belagavi, Karnataka", "state": "Karnataka", "district": "Belagavi",
  "season": "Kharif", "lat": 15.85, "lon": 74.5,
  "n": 90, "p": 42, "k": 43, "ph": 6.5,
  "temperature": 26, "humidity": 80, "rainfall": 220
}
```
`lat`/`lon`/`temperature`/`humidity`/`rainfall` are optional — if omitted,
live weather for the location is fetched and used.

## On the forgot-password flow

This is a real 3-step OTP flow, not a single-step token: (1) request a
code, (2) verify the code — the app calls `/api/auth/verify-reset-code`,
which checks the code WITHOUT consuming it, so a wrong code just fails
cleanly and you can retry — (3) only once verified does the new-password
form unlock, and *that* submission is what actually consumes the code.

`/api/auth/forgot-password` sends a **real 6-digit code by email** via
SMTP if you've set `SMTP_HOST`, `SMTP_USER`, and `SMTP_PASSWORD` in
`.env` (see `.env.example` for Gmail App Password setup — a normal Gmail
password won't work, it needs an App Password from
https://myaccount.google.com/apppasswords). Without SMTP configured,
there is no way to actually deliver an email, so the code is shown
inline instead, clearly labeled as the dev-only fallback — the
verify/consume logic is identical either way, so switching on real SMTP
doesn't change any behavior, just how the code reaches you. See
`auth.send_email()` / `auth.create_password_reset()` in `auth.py`.

### Email not arriving? Debug it in this order

1. **Run `python scripts/test_email.py you@example.com`.** This sends one
   real email completely independent of the web app, and prints the
   exact SMTP error if it fails — much faster than debugging through the
   register/forgot-password flow.
2. **Did you restart the server after editing `.env`?** This is the
   single most common cause of "I set it up and it's still not working."
   Flask reads environment variables once, at startup — saving `.env`
   while `python app.py` is already running does nothing until you stop
   it (Ctrl+C) and start it again.
3. **Check the live status on the login page** — the "About the
   forgot-password flow" card shows a real-time ✓/✗ badge (from
   `/api/auth/email-status`) telling you whether the *running* server
   currently sees SMTP as configured.
4. **Gmail specifically**: you need an **App Password**, not your normal
   Gmail password — Google blocks normal passwords for this. Generate
   one at https://myaccount.google.com/apppasswords, which requires
   2-Step Verification to be turned on first.
5. **Check spam/junk** — a first email from a new sender sometimes lands
   there.

## On admin accounts

Public registration always creates a `farmer` role — there is no way to
self-promote to admin through the API (an earlier draft of this had that
bug; it's fixed). Admin accounts are created only via
`scripts/create_admin.py`, which requires direct access to the server.

## Notes on the models

- **Crop model**: `RandomForestClassifier`, ~99% held-out accuracy — a
  clean, well-separated dataset, so treat this as "fits this dataset very
  well," not a guarantee for every real field.
- **Yield model**: `RandomForestRegressor`, R²=0.94, MAE=1.05 tonnes/ha on
  46 covered crops (150 estimators — trimmed down from 300 with no
  measurable accuracy loss, since the wider crop coverage was making
  startup noticeably slower). The dataset's coconut yield is recorded in
  nuts/hectare (not tonnes/hectare like everything else), so it's
  deliberately excluded from ML coverage rather than silently mixed in.
- **Market model**: `RandomForestRegressor`, R²=0.40 — modest, and shown
  as such, because it predicts price from crop/location/arrivals only
  (not from that day's min/max, since a farmer asking "what will this
  fetch" doesn't already know today's range).
- **Soil health**: intentionally rule-based, not ML — nutrient sufficiency
  bands are a published standard, and dressing up a lookup table as "AI"
  would be dishonest.

## Tech stack

- **Backend**: Flask, session-based auth (`werkzeug.security` password
  hashing, no plaintext storage), Flask-Limiter (rate limiting on
  login/register/password-reset/chat), CORS locked to an explicit origin
  allowlist (`ALLOWED_ORIGINS` in `.env`)
- **ML**: scikit-learn (3 RandomForest models)
- **Frontend**: HTML / CSS / vanilla JavaScript, browser Geolocation API,
  Chart.js (dashboard charts), Leaflet.js + OpenStreetMap (farm map, both
  free/keyless). Every CSS/JS asset is served through an `asset_url()`
  Jinja helper that appends `?v=<file-mtime>` — so a browser that already
  cached the old version of `script.js`/`style.css` is forced to fetch the
  new one the moment the file actually changes, instead of silently
  serving stale UI until someone hard-refreshes.
- **Database**: SQLite (`users`, `password_resets`, `recommendations`,
  `expenses`, `income`, `soil_health_logs`, `water_usage_logs`, `yield_logs`).
  Path is configurable via `DATABASE_PATH` in `.env` (defaults to
  `krushi.db` next to `app.py`) — point it at a mounted persistent volume
  in production, see "Deploying" below.
- **External APIs**: Open-Meteo (weather), a free reverse-geocoding API
  (location), ip-api.com (fallback location), data.gov.in (optional live
  market data), Google Gemini (optional chat)

## Deploying

### Security checklist (do this regardless of platform)

- Set `SECRET_KEY` in your host's environment variables to a real random
  value (`python -c "import secrets; print(secrets.token_hex(32))"`).
  Without it the app still boots (with a per-process random key, so it
  doesn't fail closed on new contributors), but sessions won't survive a
  restart and it's unsafe for more than one worker process.
- Set `ALLOWED_ORIGINS` to your real deployed domain(s) — it defaults to
  `localhost` only.
- Set `COOKIE_SECURE=1` once you're behind HTTPS (every platform below
  gives you HTTPS by default).
- Leave `FLASK_DEBUG` unset/`0` — Flask's debug mode exposes an
  interactive in-browser debugger that allows arbitrary code execution if
  left on for anything public.
- Run behind gunicorn (already in `requirements.txt` and `Procfile`), not
  `python app.py`.
- **Never commit `.env`** — it's in `.gitignore`, but that only stops
  *future* commits. If it was ever committed before `.gitignore` was
  added, it's still sitting in git history regardless — check your
  repo's commit history for it, and if you find it, rotate every
  credential inside it (Gmail App Password, Gemini key) rather than just
  deleting the file, since a deleted file is still recoverable from
  history.

### Why SQLite needs a persistent volume

Most container-based hosts (Render, Railway, Fly.io, etc.) wipe the
filesystem on every redeploy — including `krushi.db`, meaning every
registered user and every logged record disappears each time you push an
update, unless the database file lives on a **persistent volume** the
platform gives you, not the app's own ephemeral folder. `DATABASE_PATH`
in `.env` controls where the file goes — point it at your platform's
mounted volume path (e.g. `/data/krushi.db`), and `init_db()` creates the
directory automatically if it doesn't exist yet.

### Recommended: Railway (free tier realistically covers a low-traffic app)

Chosen over Render/PythonAnywhere free tiers because: Render's free tier
has no persistent disk and sleeps after 15 minutes idle (meaning every
wake-up re-trains all 3 ML models before serving the first request), and
PythonAnywhere's free tier blocks most outbound internet except a small
allowlist — which would silently break real SMTP email and likely the
Gemini chatbot too. Railway restricts neither.

1. Push this repo to GitHub (done) — make sure it includes the `Procfile`
   at the repo root.
2. [railway.app](https://railway.app) → sign up with GitHub → **New
   Project → Deploy from GitHub repo** → select your repo. Railway
   auto-detects Python + the `Procfile`.
3. **Add a volume** so your database survives redeploys: service →
   Settings → Volumes → New Volume → mount path `/data`.
4. **Variables** tab → add:
   ```
   DATABASE_PATH=/data/krushi.db
   SECRET_KEY=<a fresh random value — see checklist above>
   FLASK_DEBUG=0
   COOKIE_SECURE=1
   ALLOWED_ORIGINS=<your Railway URL, added after step 5>
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USER=<your gmail>
   SMTP_PASSWORD=<a Gmail App Password — see the email section above>
   GEMINI_API_KEY=<optional, for the chatbot>
   MARKET_API_KEY=<optional, for live market data beyond the 13 built-in crops>
   ```
5. Railway gives you a live URL (`your-app.up.railway.app`) once deployed.
   Go back to Variables and set `ALLOWED_ORIGINS` to that exact URL
   (with `https://`), then redeploy once more so it takes effect.

Railway's free usage credit (~$5/month at time of writing) realistically
covers an app at this traffic level — but it's not an unconditional
free-forever guarantee, since it's tied to actual usage. If that becomes
a real constraint once you have real users, that's the point to revisit
hosting, not before.

## Not in this build yet

Translated UI covers navigation, footer, the home page, login/register/
password-reset, and every page's heading in Hindi/Kannada/Marathi/Tamil/
Telugu/English (116 keys × 6 languages, backed by a `data-i18n`-attribute
system, `static/js/i18n.js`) — but body copy, form labels, and
JS-rendered results on most individual tool pages are still English-only.
AI disease detection from photos still isn't real (needs a trained CV
model that actually installs — see above); the "News" feature is an
internal admin-posted announcements board, not a live external news feed,
since there's no search tool in this build to source and verify real
articles. There's no automated test suite yet beyond
`scripts/test_email.py`, and the three RandomForest models retrain from
scratch on every app restart rather than being cached to disk (a few
seconds on a multi-core machine; noticeably slower on a single-core one).

