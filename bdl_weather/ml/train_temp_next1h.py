# bdl_weather/dashboard/app.py
from __future__ import annotations

import sys
from pathlib import Path

# Pastikan root repo masuk ke PYTHONPATH (penting untuk Streamlit Cloud)
ROOT = Path(__file__).resolve().parents[2]  # .../bdl_weather_project
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# bdl_weather/ml/train_temp_next1h.py
import argparse
import json
import os
from datetime import date, timedelta

import pandas as pd
import requests
from joblib import dump
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

from bdl_weather.config import settings
from bdl_weather.cities import CITIES, TIMEZONE

HOURLY_VARS = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "weather_code",
]

FEATURES = [
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "precipitation",
    "rain",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "weather_code",
    "hour",
    "dow",
]


def get_city(city_id: str) -> dict:
    city_id = city_id.upper()
    for c in CITIES:
        if c["city_id"].upper() == city_id:
            return c
    raise ValueError(f"city_id not found: {city_id}. Available: {[c['city_id'] for c in CITIES]}")


def fetch_hourly_history(city: dict, days: int = 180) -> pd.DataFrame:
    end_d = date.today()
    start_d = end_d - timedelta(days=days)

    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "hourly": ",".join(HOURLY_VARS),
        "timezone": TIMEZONE,
    }
    r = requests.get(settings.openmeteo_archive_url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    hourly = data.get("hourly")
    if not hourly or "time" not in hourly:
        raise ValueError(f"No hourly/time in response. keys={list(data.keys())}")

    df = pd.DataFrame(hourly)
    df["dt"] = pd.to_datetime(df["time"])
    df["hour"] = df["dt"].dt.hour
    df["dow"] = df["dt"].dt.dayofweek
    return df


def time_split(df: pd.DataFrame, train_ratio: float = 0.8):
    split = int(len(df) * train_ratio)
    return df.iloc[:split].copy(), df.iloc[split:].copy()


def train_and_save(city_id: str = "JKT", days: int = 180):
    city_id = city_id.upper()
    os.makedirs(settings.model_dir, exist_ok=True)

    city = get_city(city_id)
    df = fetch_hourly_history(city, days=days)

    # label: temperature 1 jam ke depan
    df["y"] = df["temperature_2m"].shift(-1)
    df = df.dropna().reset_index(drop=True)

    train_df, test_df = time_split(df, 0.8)

    X_train = train_df[FEATURES]
    y_train = train_df["y"]
    X_test = test_df[FEATURES]
    y_test = test_df["y"]

    # baseline: y(t+1) ≈ temperature_2m(t)
    yhat_base = X_test["temperature_2m"].values
    base_mae = mean_absolute_error(y_test, yhat_base)
    base_mse = mean_squared_error(y_test, yhat_base)

    models = {
        "LinearRegression": LinearRegression(),
        "RandomForest": RandomForestRegressor(
            n_estimators=300, random_state=42, n_jobs=-1
        ),
    }

    results = []
    best = None

    for name, model in models.items():
        model.fit(X_train, y_train)
        yhat = model.predict(X_test)
        mae = mean_absolute_error(y_test, yhat)
        mse = mean_squared_error(y_test, yhat)
        results.append({"model": name, "mae": float(mae), "mse": float(mse)})

        if best is None or mae < best["mae"]:
            best = {"name": name, "model": model, "mae": mae, "mse": mse}

    artifact_path = os.path.join(settings.model_dir, f"temp_next1h_{city_id}.joblib")
    dump(best["model"], artifact_path)

    meta = {
        "city_id": city_id,
        "city_name": city["city_name"],
        "features": FEATURES,
        "horizon_hours": settings.horizon_hours,
        "days_history": days,
        "baseline": {"mae": float(base_mae), "mse": float(base_mse)},
        "candidates": results,
        "best": {"model": best["name"], "mae": float(best["mae"]), "mse": float(best["mse"])},
    }

    meta_path = os.path.join(settings.model_dir, f"temp_next1h_{city_id}.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    print(f"[TRAIN DONE] city={city_id} days={days}")
    print("Saved model:", artifact_path)
    print("Saved meta :", meta_path)
    print("Baseline MAE/MSE:", base_mae, base_mse)
    print("Best:", best["name"], "MAE", best["mae"], "MSE", best["mse"])


def main():
    p = argparse.ArgumentParser(description="Train temperature next-1h model per city")
    p.add_argument("--city", default="JKT", help="City ID: JKT/BDG/SBY/MDN")
    p.add_argument("--days", type=int, default=180, help="Days of history to fetch from Open-Meteo archive")
    p.add_argument("--all", action="store_true", help="Train for all cities in bdl_weather.cities.CITIES")
    args = p.parse_args()

    if args.all:
        for c in CITIES:
            train_and_save(c["city_id"], args.days)
    else:
        train_and_save(args.city, args.days)


if __name__ == "__main__":
    main()
