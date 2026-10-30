"""
profit_estimation.py
----------------------
Net profit = income - expenses. That's it — this module doesn't predict
anything itself; it combines numbers that are each already real:
  - expenses: whatever the farmer enters (seeds, fertilizer, labour,
    water, pesticides)
  - income: area x expected yield x price, where yield comes from
    yield_model.py (real, ML) and price comes from market_model.py (real,
    ML) when the crop is covered — otherwise the farmer supplies their own
    expected price, and the app says so rather than guessing one.
"""

ACRE_TO_HECTARE = 0.404686


def estimate_profit(area_acres, expenses, yield_estimate, price_estimate, manual_price_rs_per_quintal=None):
    """expenses: dict with any of seeds/fertilizer/labour/water/pesticides -> Rs.
    yield_estimate: result of yield_model.get_expected_yield()
    price_estimate: result of market_model.get_price_estimate()"""
    total_expenses = round(sum(float(v) for v in (expenses or {}).values() if v), 2)

    price_per_quintal = None
    price_source = None
    if price_estimate and price_estimate.get("covered"):
        price_per_quintal = price_estimate["predicted_modal_price"]
        price_source = "real ML price prediction"
    elif manual_price_rs_per_quintal:
        price_per_quintal = float(manual_price_rs_per_quintal)
        price_source = "your entered price"

    income = None
    yield_tonnes = None
    if yield_estimate and yield_estimate.get("covered") and price_per_quintal is not None:
        area_ha = area_acres * ACRE_TO_HECTARE
        yield_tonnes = round(yield_estimate["predicted_yield_tonnes_per_ha"] * area_ha, 2)
        income = round(yield_tonnes * 10 * price_per_quintal, 2)  # 1 tonne = 10 quintals

    if income is None:
        return {
            "covered": False, "total_expenses_rs": total_expenses,
            "message": (
                "Income needs both a real yield estimate and a price (real ML prediction or your "
                "own entered price) for this crop — " +
                ("no real yield data for this crop yet." if not (yield_estimate and yield_estimate.get("covered"))
                 else "enter an expected price to estimate income for this crop.")
            ),
        }

    return {
        "covered": True, "area_acres": area_acres, "expected_yield_tonnes": yield_tonnes,
        "price_per_quintal_rs": price_per_quintal, "price_source": price_source,
        "income_rs": income, "total_expenses_rs": total_expenses,
        "net_profit_rs": round(income - total_expenses, 2),
    }
