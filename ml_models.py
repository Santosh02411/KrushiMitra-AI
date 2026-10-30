"""
ml_models.py
------------
Machine learning layer for Krushi.

Unlike the original prototype (which trained on randomly generated numbers),
this module trains a real scikit-learn classifier on a real, published
agronomy dataset: the "Crop Recommendation Dataset" (2200 samples, 22 crops,
7 soil/climate features). The CSV ships in data/Crop_recommendation.csv.

Dataset columns: N, P, K, temperature, humidity, ph, rainfall, label
  N, P, K      -> soil nutrient content (kg/ha) from a soil test
  temperature  -> average temperature (deg C)
  humidity     -> relative humidity (%)
  ph           -> soil pH
  rainfall     -> rainfall (mm)
  label        -> recommended crop

On startup we hold out 20% of the data to report a genuine test-set accuracy
(printed to the console and exposed via get_model_info()) so the confidence
numbers shown in the UI are backed by an actual evaluation, not a hard-coded
number.
"""

import os
import json
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "Crop_recommendation.csv")
CROP_INFO_PATH = os.path.join(BASE_DIR, "data", "crop_info.json")

FEATURE_COLUMNS = ["N", "P", "K", "temperature", "humidity", "ph", "rainfall"]


class CropRecommendationModel:
    """RandomForest classifier trained on the real crop recommendation dataset."""

    def __init__(self):
        self.df = pd.read_csv(DATA_PATH)
        self.crop_info = self._load_crop_info()
        self.model = None
        self.test_accuracy = None
        self.test_f1 = None
        self.n_samples = len(self.df)
        self.n_classes = self.df["label"].nunique()
        self._train()

    # ------------------------------------------------------------------ #
    # Training
    # ------------------------------------------------------------------ #
    def _train(self):
        X = self.df[FEATURE_COLUMNS]
        y = self.df["label"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        eval_model = RandomForestClassifier(
            n_estimators=300, max_depth=20, random_state=42, n_jobs=-1
        )
        eval_model.fit(X_train, y_train)
        preds = eval_model.predict(X_test)
        self.test_accuracy = round(accuracy_score(y_test, preds) * 100, 2)
        self.test_f1 = round(f1_score(y_test, preds, average="macro") * 100, 2)

        # Final model is retrained on the full dataset for deployment use.
        self.model = RandomForestClassifier(
            n_estimators=300, max_depth=20, random_state=42, n_jobs=-1
        )
        self.model.fit(X, y)

        print(
            f"[ml_models] Trained RandomForest on {self.n_samples} real samples "
            f"across {self.n_classes} crops | "
            f"held-out test accuracy={self.test_accuracy}% macro-F1={self.test_f1}%"
        )

    def get_model_info(self):
        return {
            "algorithm": "RandomForestClassifier (scikit-learn)",
            "training_samples": self.n_samples,
            "crop_classes": self.n_classes,
            "test_accuracy_pct": self.test_accuracy,
            "test_macro_f1_pct": self.test_f1,
            "dataset": "Crop Recommendation Dataset (N, P, K, temperature, "
                       "humidity, pH, rainfall -> crop), bundled in data/Crop_recommendation.csv",
        }

    # ------------------------------------------------------------------ #
    # Crop metadata (season / water need / market demand / notes)
    # ------------------------------------------------------------------ #
    def _load_crop_info(self):
        with open(CROP_INFO_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------ #
    # Inference
    # ------------------------------------------------------------------ #
    def recommend_crops(self, n, p, k, temperature, humidity, ph, rainfall, top_n=6):
        """Return the top_n crops the trained model considers best suited,
        each with a genuine model confidence (predict_proba), not a fudged
        heuristic score."""

        input_df = pd.DataFrame(
            [[n, p, k, temperature, humidity, ph, rainfall]], columns=FEATURE_COLUMNS
        )
        probabilities = self.model.predict_proba(input_df)[0]
        classes = self.model.classes_

        ranked = sorted(zip(classes, probabilities), key=lambda x: x[1], reverse=True)

        recommendations = []
        for crop, prob in ranked[:top_n]:
            info = self.crop_info.get(crop, {})
            recommendations.append({
                "crop": crop,
                "confidence": round(float(prob) * 100, 2),
                "season": info.get("season", "—"),
                "water_requirement": info.get("water_requirement", "medium"),
                "market_demand": info.get("market_demand", "medium"),
                "description": info.get("description", ""),
                "advice": self._advice_for(crop, temperature, humidity, ph, rainfall),
            })
        return recommendations

    def _advice_for(self, crop, temperature, humidity, ph, rainfall):
        notes = []
        if ph < 5.5:
            notes.append("Soil is acidic — consider liming before sowing.")
        elif ph > 7.5:
            notes.append("Soil is alkaline — gypsum application may help nutrient uptake.")
        if humidity > 85:
            notes.append("High humidity raises fungal disease risk; ensure good airflow/spacing.")
        if rainfall < 40:
            notes.append("Low rainfall — plan supplementary irrigation.")
        if temperature > 35:
            notes.append("High temperatures expected — mulching helps retain soil moisture.")
        return notes


class WaterManagementAdvisor:
    """Rule-based irrigation scheduling using real weather-forecast input.

    This is intentionally rule-based (crop water-balance / simplified ET
    estimation) rather than a black-box model, because irrigation timing
    is a well-understood agronomic calculation, not something that benefits
    from being dressed up as 'AI'.
    """

    def __init__(self):
        self.irrigation_profiles = {
            "rice": {"seasonal_requirement_mm": 1500, "interval_days": 3, "moisture_target_pct": 80,
                     "critical_stages": ["transplanting", "tillering", "flowering"]},
            "wheat": {"seasonal_requirement_mm": 450, "interval_days": 7, "moisture_target_pct": 60,
                      "critical_stages": ["crown root", "tillering", "flowering", "grain filling"]},
            "maize": {"seasonal_requirement_mm": 600, "interval_days": 5, "moisture_target_pct": 70,
                      "critical_stages": ["germination", "tasseling", "grain filling"]},
            "cotton": {"seasonal_requirement_mm": 800, "interval_days": 7, "moisture_target_pct": 65,
                       "critical_stages": ["germination", "flowering", "boll development"]},
            "banana": {"seasonal_requirement_mm": 1800, "interval_days": 4, "moisture_target_pct": 75,
                       "critical_stages": ["shooting", "bunch development"]},
            "mango": {"seasonal_requirement_mm": 900, "interval_days": 10, "moisture_target_pct": 55,
                      "critical_stages": ["flowering", "fruit set"]},
            "coffee": {"seasonal_requirement_mm": 1600, "interval_days": 6, "moisture_target_pct": 70,
                       "critical_stages": ["flowering", "berry development"]},
            "grapes": {"seasonal_requirement_mm": 700, "interval_days": 8, "moisture_target_pct": 55,
                       "critical_stages": ["bud break", "veraison"]},
            "watermelon": {"seasonal_requirement_mm": 500, "interval_days": 4, "moisture_target_pct": 65,
                           "critical_stages": ["vining", "fruit development"]},
            "muskmelon": {"seasonal_requirement_mm": 450, "interval_days": 4, "moisture_target_pct": 60,
                          "critical_stages": ["vining", "fruit development"]},
        }
        self.default_profile = {
            "seasonal_requirement_mm": 550, "interval_days": 6, "moisture_target_pct": 65,
            "critical_stages": ["establishment", "flowering", "maturity"],
        }

    def get_irrigation_advice(self, crop_type, soil_type, weather_forecast):
        crop_key = (crop_type or "").strip().lower()
        profile = self.irrigation_profiles.get(crop_key, self.default_profile)

        schedule = self._build_schedule(profile, weather_forecast)

        return {
            "crop": crop_type or "general",
            "seasonal_requirement_mm": profile["seasonal_requirement_mm"],
            "critical_stages": profile["critical_stages"],
            "soil_moisture_target_pct": profile["moisture_target_pct"],
            "irrigation_schedule": schedule,
            "water_conservation_tips": self._conservation_tips(crop_key, soil_type),
        }

    def _build_schedule(self, profile, weather_forecast):
        schedule = []
        for i, day in enumerate((weather_forecast or [])[:7]):
            rainfall = day.get("rainfall", 0) or 0
            temperature = day.get("temperature", 25)
            humidity = day.get("humidity", 60)

            daily_need_mm = self._estimate_daily_water_need(temperature, humidity, rainfall)
            irrigate = daily_need_mm > 3 and rainfall < 8

            schedule.append({
                "day": i + 1,
                "date": day.get("date", ""),
                "irrigation_needed": irrigate,
                "water_amount_mm": daily_need_mm if irrigate else 0,
                "reason": self._reason(rainfall, temperature, humidity),
            })
        return schedule

    @staticmethod
    def _estimate_daily_water_need(temperature, humidity, rainfall):
        """Simplified Penman-style evapotranspiration proxy: baseline ET
        adjusted for temperature and humidity, minus effective rainfall."""
        base_et = 4.5
        temp_factor = max(0.0, (temperature - 20) * 0.12)
        humidity_factor = max(0.0, (70 - humidity) * 0.04)
        et = base_et + temp_factor + humidity_factor
        return round(max(0.0, et - rainfall), 1)

    @staticmethod
    def _reason(rainfall, temperature, humidity):
        if rainfall > 8:
            return "Rainfall expected to meet crop water needs — skip irrigation."
        if temperature > 32:
            return "High temperature increases evapotranspiration — irrigate."
        if humidity < 45:
            return "Low humidity increases water loss — irrigate."
        return "Standard irrigation interval."

    def _conservation_tips(self, crop_key, soil_type):
        tips = [
            "Drip irrigation typically cuts water use by 30-50% versus flood irrigation.",
            "Irrigate early morning or evening to reduce evaporation losses.",
            "Mulching around the root zone reduces surface evaporation.",
        ]
        crop_specific = {
            "rice": "Alternate wetting and drying (AWD) can cut rice water use substantially "
                    "with minimal yield loss.",
            "wheat": "Furrow irrigation improves water-use efficiency versus flooding.",
            "cotton": "Deeper, less frequent irrigation encourages deeper root growth.",
        }
        if crop_key in crop_specific:
            tips.append(crop_specific[crop_key])

        soil_specific = {
            "sandy": "Sandy soil drains fast — irrigate more often with smaller amounts.",
            "clay": "Clay soil retains water — allow the surface to dry between irrigations "
                    "to avoid waterlogging.",
            "loamy": "Loamy soil has balanced drainage/retention — good for standard schedules.",
        }
        if soil_type in soil_specific:
            tips.append(soil_specific[soil_type])

        return tips
