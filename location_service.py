"""
location_service.py
--------------------
Location detection and lookup.

The original version routed every location through a generative language
model (Gemini) and asked it to invent structured agricultural stats for the
area — a bad pattern, since an LLM has no ground truth for a given city's
average rainfall and will happily hallucinate numbers. This version instead:

  1. Detects the visitor's approximate location from their IP via ip-api.com
     (free, no key, real data).
  2. Resolves any place name to coordinates via Open-Meteo's geocoding API
     (free, no key, real data) so weather_service can fetch a real forecast.
  3. Ships a small, honestly-labeled static reference table of agro-climatic
     notes for a handful of major Indian regions, used only as a friendly
     fallback description — never presented as live/measured data.
"""

import requests

IP_GEOLOCATION_URL = "http://ip-api.com/json/"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
REVERSE_GEOCODE_URL = "https://api.bigdatacloud.net/data/reverse-geocode-client"

# Static reference notes -- clearly a fallback, not live data.
REGION_NOTES = {
    "delhi": {"state": "Delhi", "typical_soil": ["alluvial", "loamy"],
              "common_crops": ["wheat", "rice", "sugarcane"], "season": "both"},
    "mumbai": {"state": "Maharashtra", "typical_soil": ["laterite", "alluvial"],
               "common_crops": ["rice", "cotton", "sugarcane"], "season": "kharif"},
    "bangalore": {"state": "Karnataka", "typical_soil": ["red", "laterite"],
                  "common_crops": ["ragi", "maize", "vegetables"], "season": "both"},
    "chennai": {"state": "Tamil Nadu", "typical_soil": ["alluvial", "red"],
                "common_crops": ["rice", "sugarcane", "groundnut"], "season": "both"},
    "kolkata": {"state": "West Bengal", "typical_soil": ["alluvial"],
                "common_crops": ["rice", "jute", "potato"], "season": "kharif"},
    "hyderabad": {"state": "Telangana", "typical_soil": ["red", "black"],
                  "common_crops": ["cotton", "maize", "rice"], "season": "both"},
    "pune": {"state": "Maharashtra", "typical_soil": ["black", "loamy"],
             "common_crops": ["sugarcane", "grapes", "onion"], "season": "both"},
}


class LocationService:
    def get_location_from_ip(self):
        """Best-effort IP geolocation. This is a FALLBACK ONLY — IP address
        geolocation in India is frequently wrong by hundreds of km, because
        mobile carriers and many ISPs route traffic through a regional
        gateway (a user in a small town can show up as their carrier's
        nearest metro hub). Prefer get location via the browser's GPS
        (navigator.geolocation on the frontend) and pass real lat/lon to
        reverse_geocode() below instead. Returns None if unavailable."""
        try:
            resp = requests.get(IP_GEOLOCATION_URL, timeout=5)
            data = resp.json()
            if data.get("status") == "success":
                return {
                    "city": data["city"],
                    "region": data["regionName"],
                    "country": data["country"],
                    "lat": data["lat"],
                    "lon": data["lon"],
                    "location_string": f"{data['city']}, {data['regionName']}",
                }
        except Exception as e:
            print(f"[location_service] IP geolocation failed: {e}")
        return None

    def geocode(self, location_string):
        """Resolve a free-text place name to coordinates via Open-Meteo."""
        try:
            resp = requests.get(
                GEOCODE_URL, params={"name": location_string, "count": 1}, timeout=4
            )
            resp.raise_for_status()
            results = resp.json().get("results")
            if results:
                top = results[0]
                return {"lat": top["latitude"], "lon": top["longitude"],
                        "name": top.get("name"), "country": top.get("country")}
        except Exception as e:
            print(f"[location_service] geocoding failed: {e}")
        return None

    def reverse_geocode(self, lat, lon):
        """Resolve real GPS coordinates (from the browser) to a human-readable
        place name, using a free keyless reverse-geocoding API. This is what
        should back a 'use my location' button — accurate to the device's
        actual GPS/network fix, unlike IP-based lookup."""
        try:
            resp = requests.get(
                REVERSE_GEOCODE_URL,
                params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
                timeout=4,
            )
            resp.raise_for_status()
            data = resp.json()
            city = data.get("city") or data.get("locality") or data.get("localityInfo", {}).get("administrative", [{}])[0].get("name", "")
            state = data.get("principalSubdivision", "")
            return {
                "city": city,
                "state": state,
                "country": data.get("countryName", ""),
                "location_string": f"{city}, {state}".strip(", "),
                "lat": lat,
                "lon": lon,
            }
        except Exception as e:
            print(f"[location_service] reverse geocoding failed: {e}")
            return {"city": "", "state": "", "country": "", "location_string": f"{lat:.4f}, {lon:.4f}",
                    "lat": lat, "lon": lon}

    def get_region_notes(self, location_string):
        """Return static reference notes for a known region, honestly labeled
        as reference info (NOT live measured data)."""
        key = (location_string or "").lower().split(",")[0].strip()
        notes = REGION_NOTES.get(key)
        return {
            "matched": bool(notes),
            "notes": notes or {},
            "disclaimer": "Reference information only, not live data. Enter your own "
                           "soil test (N/P/K/pH) values for an accurate recommendation.",
        }
