"""
market_service.py
------------------
Market price data, in priority order:

  1. data.gov.in live Agmarknet feed, if MARKET_API_KEY is set and the
     request succeeds (real, live, any crop the feed covers).
  2. The locally trained MarketPriceModel (real historical mandi data,
     ML-predicted) — currently covers potato, tomato and wheat.
  3. For anything else: an explicit "not covered" response. No invented
     numbers, no silent simulation — the frontend shows this honestly.

A crop recommendation looks up market data for several crops per request.
If data.gov.in is unreachable (blocked network, wrong key, etc.), waiting
out a full timeout on every single one of those lookups adds up fast —
this is what was making recommendations feel slow. A short in-process
circuit breaker fixes that: after one real failure, data.gov.in is
skipped (falling straight to the local model) for a cooldown period,
instead of being retried and re-timed-out on every request.
"""

import time

import requests

from market_model import MarketPriceModel

DATA_GOV_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
DATA_GOV_URL = f"https://api.data.gov.in/resource/{DATA_GOV_RESOURCE_ID}"

REQUEST_TIMEOUT_SECONDS = 4
CIRCUIT_BREAKER_COOLDOWN_SECONDS = 120


class MarketService:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.model = MarketPriceModel()
        self._data_gov_down_until = 0  # epoch time; 0 = not tripped

    def get_model_info(self):
        return self.model.get_model_info()

    def get_price_estimate(self, crop, state=None):
        if self.api_key and time.time() >= self._data_gov_down_until:
            live = self._fetch_data_gov_in(crop, state)
            if live:
                return live

        estimate = self.model.get_price_estimate(crop, state=state)
        if estimate.get("covered"):
            return estimate

        return {
            "covered": False,
            "crop": crop,
            "data_source": "none",
            "message": (
                f"No real market dataset is loaded for '{crop}' yet. Real ML-predicted prices are "
                f"currently available for: {', '.join(self.model.covered_crops)}. Add more Agmarknet "
                f"data to data/market_price_data.csv, or set MARKET_API_KEY for live data.gov.in prices, "
                f"to extend coverage."
            ),
        }

    def get_market_prices(self, crop, state=None):
        result = self.model.get_market_prices(crop, state=state)
        if not result.get("covered"):
            result["message"] = (
                f"No real per-market price records for '{crop}'. Real coverage: "
                f"{', '.join(self.model.get_model_info()['covered_crops'])}."
            )
        return result

    def get_nearby_markets(self, crop, lat, lon, max_results=5):
        result = self.model.get_nearby_markets(crop, lat, lon, max_results=max_results)
        if not result.get("covered"):
            result["message"] = (
                f"No nearby real market data for '{crop}' with a known coordinate. Real coverage: "
                f"{', '.join(self.model.get_model_info()['covered_crops'])}."
            )
        return result

    # ------------------------------------------------------------------ #
    # Real live source (used only if MARKET_API_KEY is configured)
    # ------------------------------------------------------------------ #
    def _fetch_data_gov_in(self, crop, state=None):
        try:
            records = self._query_data_gov_in(crop, state)
            if not records and state:
                # Real record for this crop nationally, just not (yet, in
                # this feed) tagged to this specific state — a genuine
                # broader real result beats no result, and it's still
                # clearly labeled as national rather than state-specific.
                records = self._query_data_gov_in(crop, state=None)
                national_fallback = bool(records)
            else:
                national_fallback = False

            prices = []
            for r in records:
                try:
                    price = float(r.get("modal_price", 0))
                except (TypeError, ValueError):
                    continue
                if price > 0:
                    prices.append(price)
            if not prices:
                return None

            return {
                "covered": True,
                "crop": crop,
                "predicted_modal_price": round(sum(prices) / len(prices), 0),
                "observed_price_range": [min(prices), max(prices)],
                "sample_size": len(prices),
                "data_source": "real (data.gov.in, live, national average — no state-specific "
                                "record found)" if national_fallback else "real (data.gov.in, live)",
            }
        except Exception as e:
            print(f"[market_service] data.gov.in fetch failed ({e}) — skipping it for the next "
                  f"{CIRCUIT_BREAKER_COOLDOWN_SECONDS}s instead of retrying on every request.")
            self._data_gov_down_until = time.time() + CIRCUIT_BREAKER_COOLDOWN_SECONDS
            return None

    def _query_data_gov_in(self, crop, state=None):
        params = {"api-key": self.api_key, "format": "json", "limit": 20,
                  "filters[commodity]": crop.title()}
        if state:
            params["filters[state]"] = state
        resp = requests.get(DATA_GOV_URL, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.json().get("records", [])

    def get_market_news(self, crop=None):
        """Illustrative agri-market news items (static, not a live news feed)."""
        news_items = [
            {"title": "Monsoon outlook watched closely by Kharif growers",
             "summary": "Timely, well-distributed rainfall is the single biggest driver of "
                         "Kharif crop yields and prices.",
             "impact": "neutral"},
            {"title": "Storage and cold-chain access affects perishable crop prices",
             "summary": "Crops like tomato and potato see large price swings where cold "
                         "storage is limited.",
             "impact": "neutral"},
        ]
        if crop:
            matched = [n for n in news_items if crop.lower() in (n["title"] + n["summary"]).lower()]
            return matched or news_items
        return news_items
