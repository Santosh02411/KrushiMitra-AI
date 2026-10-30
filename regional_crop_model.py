"""
regional_crop_model.py
-------------------------
A second, complementary crop model — trained on real Indian government
crop-production records (data/crop_yield_data.csv, the same dataset behind
yield_model.py), predicting Crop from State + Season + real climate
(Annual_Rainfall, Avg_Temperature).

Why this exists: the main crop model (ml_models.py) is trained on
Crop_recommendation.csv, which only covers 22 crops and skews heavily
toward pulses and fruit (apple, banana, mango, grapes, orange, papaya,
pomegranate, watermelon, muskmelon...) with no sugarcane, tobacco, jowar,
wheat, potato, onion, groundnut, soyabean, or most other major Indian
field crops — and it has NO location input at all (see regional_crops.py's
docstring). This model fixes both gaps at once: it's trained on 54 real
crop categories with genuine state-level cultivation history, so a
farmer entering their actual state/district gets recommendations that are
directly grounded in what's really grown there — not just soil chemistry
with no geography.

The two models measure different things and are surfaced separately
rather than merged into one ranked list: this one answers "what's
commonly grown in your region," the other answers "what suits your soil
test." A farmer benefits from seeing both, clearly labeled.
"""

import os
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, f1_score

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data", "crop_yield_data.csv")

# Aggregate/catch-all categories in the source data ("Other Cereals",
# "Oilseeds total", etc.) aren't real single crops — dropped rather than
# recommended as if they were. Also drop anything with too few real
# records to train on reliably.
_EXCLUDED_CROPS = {
    "Other Kharif pulses", "Other  Rabi pulses", "Other Cereals",
    "other oilseeds", "Oilseeds total", "Other Summer Pulses",
}
_MIN_SAMPLES = 50

FEATURE_COLS = ["State", "Season", "Annual_Rainfall", "Avg_Temperature"]
CAT_COLS = ["State", "Season"]


class RegionalCropModel:
    def __init__(self):
        raw = pd.read_csv(DATA_PATH)
        for c in ["Crop", "Season", "State"]:
            raw[c] = raw[c].astype(str).str.strip()

        raw = raw[~raw["Crop"].isin(_EXCLUDED_CROPS)]
        counts = raw["Crop"].value_counts()
        keep_crops = counts[counts >= _MIN_SAMPLES].index
        self.df = raw[raw["Crop"].isin(keep_crops)].copy()

        self.model = None
        self.columns = None
        self.test_accuracy = None
        self.test_f1 = None
        self.states = sorted(self.df["State"].unique())
        self.seasons = sorted(self.df["Season"].unique())
        self.n_crops = self.df["Crop"].nunique()
        self._train()

    def _train(self):
        X = pd.get_dummies(self.df[FEATURE_COLS], columns=CAT_COLS)
        y = self.df["Crop"]
        self.columns = X.columns

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )
        eval_model = RandomForestClassifier(n_estimators=300, max_depth=18, random_state=42, n_jobs=-1)
        eval_model.fit(X_train, y_train)
        preds = eval_model.predict(X_test)
        self.test_accuracy = round(accuracy_score(y_test, preds) * 100, 2)
        self.test_f1 = round(f1_score(y_test, preds, average="macro", zero_division=0) * 100, 2)

        self.model = RandomForestClassifier(n_estimators=300, max_depth=18, random_state=42, n_jobs=-1)
        self.model.fit(X, y)

        print(
            f"[regional_crop_model] Trained RandomForest on {len(self.df)} real records across "
            f"{self.n_crops} crops, {len(self.states)} states | "
            f"held-out test accuracy={self.test_accuracy}% macro-F1={self.test_f1}%"
        )

    def get_model_info(self):
        return {
            "algorithm": "RandomForestClassifier (scikit-learn)",
            "training_records": len(self.df),
            "crop_classes": self.n_crops,
            "states_covered": len(self.states),
            "test_accuracy_pct": self.test_accuracy,
            "test_macro_f1_pct": self.test_f1,
            "dataset": "Real Indian government crop-production data (data/crop_yield_data.csv), "
                       "all states, 1997-2020",
            "honesty_note": "Predicts crop identity from State/Season/rainfall/temperature alone — "
                             "many different crops share similar broad climate profiles in the same "
                             "state, so accuracy is naturally lower than a model with real soil "
                             "chemistry input. Use this for 'what's commonly grown here', not as a "
                             "substitute for a soil test.",
        }

    def recommend_by_region(self, state, season=None, rainfall=None, temperature=None, top_n=8):
        if not state or state not in self.states:
            return {"covered": False, "state": state,
                    "message": f"No real cultivation records for '{state}' in this dataset. "
                               f"Covers: {', '.join(self.states)}."}

        subset = self.df[self.df["State"] == state]
        row = {
            "State": state,
            "Season": season if season in self.seasons else subset["Season"].mode().iloc[0],
            "Annual_Rainfall": rainfall if rainfall is not None else float(subset["Annual_Rainfall"].median()),
            "Avg_Temperature": temperature if temperature is not None else float(subset["Avg_Temperature"].median()),
        }
        input_df = pd.get_dummies(pd.DataFrame([row]), columns=CAT_COLS)
        input_df = input_df.reindex(columns=self.columns, fill_value=0)

        probabilities = self.model.predict_proba(input_df)[0]
        classes = self.model.classes_
        ranked = sorted(zip(classes, probabilities), key=lambda x: x[1], reverse=True)[:top_n]

        return {
            "covered": True, "state": state, "season_used": row["Season"],
            "recommendations": [
                {"crop": crop, "confidence": round(float(p) * 100, 2)} for crop, p in ranked
            ],
            "test_accuracy_pct": self.test_accuracy,
            "data_source": "real (Indian govt crop-production records for this state)",
        }
