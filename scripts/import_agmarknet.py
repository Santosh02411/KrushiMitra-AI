"""
import_agmarknet.py - grow the market-price dataset with REAL mandi records.

KrushiMitra only ever shows prices that came from real records. The bundled file
data/market_prices_by_location.csv is small, so this script pulls thousands more
rows from the Government of India's Agmarknet feed on data.gov.in and appends
them. Every crop that appears in the file becomes a covered crop automatically
(no code changes needed).

Usage (needs internet + a free key from https://data.gov.in):
    export MARKET_API_KEY=your_key          # or set it in .env
    python scripts/import_agmarknet.py                       # default crop list, up to 4000 rows
    python scripts/import_agmarknet.py --max-rows 5000 --commodities Rice Maize Onion Soyabean
    python scripts/import_agmarknet.py --dry-run             # show what would be added

Rows are de-duplicated, invalid/zero prices are skipped, and the original file is
backed up to market_prices_by_location.csv.bak before anything is written.
"""
import argparse
import csv
import os
import shutil
import sys
import time

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
except ImportError:
    pass

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
CSV_PATH = os.path.join(BASE, "data", "market_prices_by_location.csv")
RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
URL = f"https://api.data.gov.in/resource/{RESOURCE}"
FIELDS = ["State", "District", "Market", "Variety", "Crop", "Arrivals_Tonnes", "Min_Price", "Max_Price", "Modal_Price"]
DEFAULT_COMMODITIES = ["Rice", "Wheat", "Maize", "Soyabean", "Groundnut", "Cotton", "Gram", "Arhar (Tur/Red Gram)(Whole)",
                       "Onion", "Potato", "Tomato", "Mustard", "Bajra(Pearl Millet/Cumbu)", "Jowar(Sorghum)", "Sugarcane",
                       "Banana", "Mango", "Turmeric", "Dry Chillies", "Garlic", "Ginger(Dry)", "Coriander(Leaves)",
                       "Black Gram (Urd Beans)(Whole)", "Green Gram (Moong)(Whole)", "Lentil (Masur)(Whole)"]


def fetch(key, commodity, offset, limit=500):
    r = requests.get(URL, params={"api-key": key, "format": "json", "limit": limit, "offset": offset,
                                  "filters[commodity]": commodity}, timeout=30)
    r.raise_for_status()
    return r.json().get("records", [])


def to_row(rec):
    try:
        lo, hi, modal = (float(rec[k]) for k in ("min_price", "max_price", "modal_price"))
    except (KeyError, TypeError, ValueError):
        return None
    if modal <= 0 or lo <= 0 or hi < lo or modal > hi * 1.001 or modal < lo * 0.999:
        return None
    name = (rec.get("commodity") or "").split("(")[0].strip() or None
    if not name or not rec.get("state") or not rec.get("market"):
        return None
    return {"State": rec["state"].strip(), "District": (rec.get("district") or "").strip(), "Market": rec["market"].strip(),
            "Variety": (rec.get("variety") or "Other").strip(), "Crop": name.title(), "Arrivals_Tonnes": 0,
            "Min_Price": int(lo), "Max_Price": int(hi), "Modal_Price": int(modal)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--commodities", nargs="*", default=DEFAULT_COMMODITIES)
    ap.add_argument("--max-rows", type=int, default=4000)
    ap.add_argument("--per-commodity", type=int, default=400, help="cap per commodity so one crop can't dominate")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    key = os.getenv("MARKET_API_KEY")
    if not key:
        sys.exit("Set MARKET_API_KEY (free from https://data.gov.in) first.")

    existing = set()
    if os.path.exists(CSV_PATH):
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing.add(tuple(r[k] for k in FIELDS if k != "Arrivals_Tonnes"))
    new_rows = []
    for c in a.commodities:
        got = 0
        for offset in range(0, a.per_commodity, 500):
            try:
                recs = fetch(key, c, offset)
            except Exception as e:
                print(f"  ! {c}: {e}")
                break
            if not recs:
                break
            for rec in recs:
                row = to_row(rec)
                if not row:
                    continue
                sig = tuple(str(row[k]) for k in FIELDS if k != "Arrivals_Tonnes")
                if sig in existing:
                    continue
                existing.add(sig); new_rows.append(row); got += 1
            time.sleep(0.4)
        print(f"  {c}: +{got} rows")
        if len(new_rows) >= a.max_rows:
            break
    new_rows = new_rows[:a.max_rows]
    print(f"Total new real rows: {len(new_rows)}")
    if a.dry_run or not new_rows:
        return
    shutil.copy(CSV_PATH, CSV_PATH + ".bak")
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        for r in new_rows:
            w.writerow(r)
    print("Appended to data/market_prices_by_location.csv - restart the app; new crops are picked up automatically.")


if __name__ == "__main__":
    main()
