"""
weather_service.py
-------------------
Real, live weather data with no API key required, using Open-Meteo
(https://open-meteo.com), a free public weather API. If the user supplies
an OPENWEATHER_API_KEY in .env, that is used instead (kept for people who
already have one). If both are unreachable (e.g. no internet in a sandbox),
we fall back to clearly-labeled offline sample data so the app still runs.
"""

import requests
from datetime import datetime

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OWM_BASE_URL = "https://api.openweathermap.org/data/2.5"


class WeatherService:
    def __init__(self, openweather_api_key=None):
        self.owm_api_key = openweather_api_key

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def get_current_weather(self, location):
        if self.owm_api_key:
            data = self._owm_current(location)
            if data:
                return data
        data = self._open_meteo_current(location)
        if data:
            return data
        return self._offline_estimate(location)

    def get_forecast(self, location, days=7):
        if self.owm_api_key:
            data = self._owm_forecast(location, days)
            if data:
                return data
        data = self._open_meteo_forecast(location, days)
        if data:
            return data
        return self._offline_forecast(days, location)

    def get_current_weather_by_coords(self, lat, lon, label=None):
        """Preferred entry point when the browser has supplied real GPS
        coordinates — avoids place-name geocoding mismatches entirely
        (e.g. small towns resolving to the wrong, much larger, nearby city)."""
        if self.owm_api_key:
            data = self._owm_current_by_coords(lat, lon, label)
            if data:
                return data
        data = self._open_meteo_current_by_coords(lat, lon, label)
        if data:
            return data
        return self._offline_estimate(label or f"{lat},{lon}")

    def get_forecast_by_coords(self, lat, lon, days=7):
        if self.owm_api_key:
            data = self._owm_forecast_by_coords(lat, lon, days)
            if data:
                return data
        data = self._open_meteo_forecast_by_coords(lat, lon, days)
        if data:
            return data
        return self._offline_forecast(days, f"{lat},{lon}")

    # ------------------------------------------------------------------ #
    # Open-Meteo (free, no key) - primary source
    # ------------------------------------------------------------------ #
    def _geocode(self, location):
        try:
            resp = requests.get(
                GEOCODE_URL, params={"name": location, "count": 1}, timeout=4
            )
            resp.raise_for_status()
            results = resp.json().get("results")
            if not results:
                return None
            top = results[0]
            return {
                "lat": top["latitude"],
                "lon": top["longitude"],
                "name": top.get("name", location),
                "country": top.get("country", ""),
            }
        except Exception as e:
            print(f"[weather_service] geocoding failed for '{location}': {e}")
            return None

    def _open_meteo_current(self, location):
        geo = self._geocode(location)
        if not geo:
            return None
        try:
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": geo["lat"],
                    "longitude": geo["lon"],
                    "current": "temperature_2m,relative_humidity_2m,precipitation,"
                               "wind_speed_10m,weather_code,uv_index",
                    "timezone": "auto",
                },
                timeout=4,
            )
            resp.raise_for_status()
            cur = resp.json().get("current", {})
            return {
                "location": f"{geo['name']}, {geo['country']}".strip(", "),
                "temperature": cur.get("temperature_2m"),
                "humidity": cur.get("relative_humidity_2m"),
                "pressure": None,
                "weather": self._weather_code_to_text(cur.get("weather_code")),
                "wind_speed": cur.get("wind_speed_10m"),
                "rainfall": cur.get("precipitation", 0),
                "uv_index": cur.get("uv_index"),
                "timestamp": datetime.now().isoformat(),
                "source": "open-meteo.com (live)",
            }
        except Exception as e:
            print(f"[weather_service] Open-Meteo current weather failed: {e}")
            return None

    def _open_meteo_forecast(self, location, days=7):
        geo = self._geocode(location)
        if not geo:
            return None
        try:
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": geo["lat"],
                    "longitude": geo["lon"],
                    "daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
                             "precipitation_sum,weather_code,wind_speed_10m_max,uv_index_max",
                    "forecast_days": days,
                    "timezone": "auto",
                },
                timeout=4,
            )
            resp.raise_for_status()
            daily = resp.json().get("daily", {})
            forecast = []
            dates = daily.get("time", [])
            for i in range(len(dates)):
                tmax = daily.get("temperature_2m_max", [None])[i]
                tmin = daily.get("temperature_2m_min", [None])[i]
                avg_temp = round((tmax + tmin) / 2, 1) if tmax is not None and tmin is not None else None
                forecast.append({
                    "date": dates[i],
                    "temperature": avg_temp,
                    "humidity": daily.get("relative_humidity_2m_mean", [None])[i],
                    "weather": self._weather_code_to_text(daily.get("weather_code", [None])[i]),
                    "rainfall": daily.get("precipitation_sum", [0])[i],
                    "wind_speed": daily.get("wind_speed_10m_max", [None])[i],
                    "uv_index": daily.get("uv_index_max", [None])[i],
                })
            return forecast
        except Exception as e:
            print(f"[weather_service] Open-Meteo forecast failed: {e}")
            return None

    def _open_meteo_current_by_coords(self, lat, lon, label=None):
        try:
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,relative_humidity_2m,precipitation,"
                               "wind_speed_10m,weather_code,uv_index",
                    "timezone": "auto",
                },
                timeout=4,
            )
            resp.raise_for_status()
            cur = resp.json().get("current", {})
            return {
                "location": label or f"{lat:.3f}, {lon:.3f}",
                "temperature": cur.get("temperature_2m"),
                "humidity": cur.get("relative_humidity_2m"),
                "pressure": None,
                "weather": self._weather_code_to_text(cur.get("weather_code")),
                "wind_speed": cur.get("wind_speed_10m"),
                "rainfall": cur.get("precipitation", 0),
                "uv_index": cur.get("uv_index"),
                "timestamp": datetime.now().isoformat(),
                "source": "open-meteo.com (live, GPS coordinates)",
            }
        except Exception as e:
            print(f"[weather_service] Open-Meteo current-by-coords failed: {e}")
            return None

    def _open_meteo_forecast_by_coords(self, lat, lon, days=7):
        try:
            resp = requests.get(
                FORECAST_URL,
                params={
                    "latitude": lat, "longitude": lon,
                    "daily": "temperature_2m_max,temperature_2m_min,relative_humidity_2m_mean,"
                             "precipitation_sum,weather_code,wind_speed_10m_max,uv_index_max",
                    "forecast_days": days,
                    "timezone": "auto",
                },
                timeout=4,
            )
            resp.raise_for_status()
            daily = resp.json().get("daily", {})
            forecast = []
            dates = daily.get("time", [])
            for i in range(len(dates)):
                tmax = daily.get("temperature_2m_max", [None])[i]
                tmin = daily.get("temperature_2m_min", [None])[i]
                avg_temp = round((tmax + tmin) / 2, 1) if tmax is not None and tmin is not None else None
                forecast.append({
                    "date": dates[i],
                    "temperature": avg_temp,
                    "humidity": daily.get("relative_humidity_2m_mean", [None])[i],
                    "weather": self._weather_code_to_text(daily.get("weather_code", [None])[i]),
                    "rainfall": daily.get("precipitation_sum", [0])[i],
                    "wind_speed": daily.get("wind_speed_10m_max", [None])[i],
                    "uv_index": daily.get("uv_index_max", [None])[i],
                })
            return forecast
        except Exception as e:
            print(f"[weather_service] Open-Meteo forecast-by-coords failed: {e}")
            return None

    def _owm_current_by_coords(self, lat, lon, label=None):
        try:
            resp = requests.get(
                f"{OWM_BASE_URL}/weather",
                params={"lat": lat, "lon": lon, "appid": self.owm_api_key, "units": "metric"},
                timeout=4,
            )
            if resp.status_code == 401:
                print("[weather_service] OpenWeatherMap key invalid, falling back")
                return None
            resp.raise_for_status()
            data = resp.json()
            return {
                "location": label or data.get("name", f"{lat:.3f}, {lon:.3f}"),
                "temperature": round(data["main"]["temp"], 1),
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"],
                "weather": data["weather"][0]["description"],
                "wind_speed": round(data["wind"]["speed"], 1),
                "rainfall": data.get("rain", {}).get("1h", 0),
                "uv_index": None,
                "timestamp": datetime.now().isoformat(),
                "source": "openweathermap.org (live, GPS coordinates)",
            }
        except Exception as e:
            print(f"[weather_service] OpenWeatherMap current-by-coords failed: {e}")
            return None

    def _owm_forecast_by_coords(self, lat, lon, days=7):
        try:
            resp = requests.get(
                f"{OWM_BASE_URL}/forecast",
                params={"lat": lat, "lon": lon, "appid": self.owm_api_key, "units": "metric"},
                timeout=4,
            )
            if resp.status_code == 401:
                return None
            resp.raise_for_status()
            data = resp.json()
            forecast, seen_dates = [], set()
            for item in data["list"]:
                dt = datetime.fromtimestamp(item["dt"])
                date_str = dt.strftime("%Y-%m-%d")
                if date_str not in seen_dates and len(forecast) < days:
                    forecast.append({
                        "date": date_str,
                        "temperature": round(item["main"]["temp"], 1),
                        "humidity": item["main"]["humidity"],
                        "weather": item["weather"][0]["description"],
                        "rainfall": item.get("rain", {}).get("3h", 0),
                        "wind_speed": round(item["wind"]["speed"], 1),
                        "uv_index": None,
                    })
                    seen_dates.add(date_str)
            return forecast
        except Exception as e:
            print(f"[weather_service] OpenWeatherMap forecast-by-coords failed: {e}")
            return None

    @staticmethod
    def _weather_code_to_text(code):
        """Map WMO weather codes (used by Open-Meteo) to a short description."""
        if code is None:
            return "unknown"
        mapping = {
            0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
            45: "fog", 48: "depositing rime fog",
            51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
            61: "light rain", 63: "moderate rain", 65: "heavy rain",
            71: "light snow", 73: "moderate snow", 75: "heavy snow",
            80: "light rain showers", 81: "moderate rain showers", 82: "violent rain showers",
            95: "thunderstorm", 96: "thunderstorm with hail", 99: "severe thunderstorm with hail",
        }
        return mapping.get(int(code), "variable conditions")

    @staticmethod
    def get_alerts(forecast):
        """Derive rain and heatwave alerts from a real forecast — rule-based
        thresholds on real data, not a separate 'alerts API' pretending to
        know something the forecast doesn't already say."""
        alerts = []
        for day in (forecast or []):
            date = day.get("date", "")
            rainfall = day.get("rainfall") or 0
            temperature = day.get("temperature")
            if rainfall >= 35:
                alerts.append({"type": "rain", "severity": "high", "date": date,
                                "message": f"Heavy rain expected on {date} (~{rainfall}mm) — delay spraying "
                                           f"and check field drainage."})
            elif rainfall >= 15:
                alerts.append({"type": "rain", "severity": "moderate", "date": date,
                                "message": f"Moderate rain expected on {date} (~{rainfall}mm)."})

            if temperature is not None:
                if temperature >= 42:
                    alerts.append({"type": "heatwave", "severity": "high", "date": date,
                                    "message": f"Heatwave conditions expected on {date} (~{temperature}°C) — "
                                               f"irrigate early morning/evening and watch for crop heat stress."})
                elif temperature >= 38:
                    alerts.append({"type": "heatwave", "severity": "moderate", "date": date,
                                    "message": f"High temperature expected on {date} (~{temperature}°C)."})
        return alerts

    # ------------------------------------------------------------------ #
    # OpenWeatherMap (optional, used only if a key is configured)
    # ------------------------------------------------------------------ #
    def _owm_current(self, location):
        try:
            resp = requests.get(
                f"{OWM_BASE_URL}/weather",
                params={"q": location, "appid": self.owm_api_key, "units": "metric"},
                timeout=4,
            )
            if resp.status_code == 401:
                print("[weather_service] OpenWeatherMap key invalid, falling back")
                return None
            resp.raise_for_status()
            data = resp.json()
            return {
                "location": data["name"],
                "temperature": round(data["main"]["temp"], 1),
                "humidity": data["main"]["humidity"],
                "pressure": data["main"]["pressure"],
                "weather": data["weather"][0]["description"],
                "wind_speed": round(data["wind"]["speed"], 1),
                "rainfall": data.get("rain", {}).get("1h", 0),
                "uv_index": None,
                "timestamp": datetime.now().isoformat(),
                "source": "openweathermap.org (live)",
            }
        except Exception as e:
            print(f"[weather_service] OpenWeatherMap current weather failed: {e}")
            return None

    def _owm_forecast(self, location, days=7):
        try:
            resp = requests.get(
                f"{OWM_BASE_URL}/forecast",
                params={"q": location, "appid": self.owm_api_key, "units": "metric"},
                timeout=4,
            )
            if resp.status_code == 401:
                return None
            resp.raise_for_status()
            data = resp.json()
            forecast, seen_dates = [], set()
            for item in data["list"]:
                dt = datetime.fromtimestamp(item["dt"])
                date_str = dt.strftime("%Y-%m-%d")
                if date_str not in seen_dates and len(forecast) < days:
                    forecast.append({
                        "date": date_str,
                        "temperature": round(item["main"]["temp"], 1),
                        "humidity": item["main"]["humidity"],
                        "weather": item["weather"][0]["description"],
                        "rainfall": item.get("rain", {}).get("3h", 0),
                        "wind_speed": round(item["wind"]["speed"], 1),
                        "uv_index": None,
                    })
                    seen_dates.add(date_str)
            return forecast
        except Exception as e:
            print(f"[weather_service] OpenWeatherMap forecast failed: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Offline fallback (only used if there is truly no network access)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _offline_estimate(location):
        print(f"[weather_service] No network reachable, using offline sample values for {location}")
        return {
            "location": location, "temperature": 26.0, "humidity": 65,
            "pressure": None, "weather": "data unavailable (offline)",
            "wind_speed": None, "rainfall": 0, "uv_index": None, "timestamp": datetime.now().isoformat(),
            "source": "offline sample (no live data available)",
        }

    @staticmethod
    def _offline_forecast(days, location):
        base = datetime.now()
        return [{
            "date": base.strftime("%Y-%m-%d"),
            "temperature": 26.0, "humidity": 65, "weather": "offline sample",
            "rainfall": 0, "wind_speed": None, "uv_index": None,
        } for _ in range(days)]
