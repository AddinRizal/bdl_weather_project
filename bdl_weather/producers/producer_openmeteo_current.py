# bdl_weather/dashboard/app.py
from __future__ import annotations

import sys
from pathlib import Path

# Pastikan root repo masuk ke PYTHONPATH (penting untuk Streamlit Cloud)
ROOT = Path(__file__).resolve().parents[2]  # .../bdl_weather_project
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
import json
import time
from datetime import datetime, timezone

import requests
from kafka import KafkaProducer

from bdl_weather.config import settings
from bdl_weather.cities import CITIES, TIMEZONE

CURRENT_VARS = [
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

def fetch_current(city: dict) -> dict:
    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "current": ",".join(CURRENT_VARS),
        "timezone": TIMEZONE,
    }
    r = requests.get(settings.openmeteo_forecast_url, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    cur = data.get("current")
    if not cur:
        raise ValueError(f"No 'current' in response. keys={list(data.keys())}")

    return {
        "city_id": city["city_id"],
        "city_name": city["city_name"],
        "lat": float(city["lat"]),
        "lon": float(city["lon"]),
        "event_time": cur.get("time"),  # iso8601 local time
        "temperature_2m": cur.get("temperature_2m"),
        "apparent_temperature": cur.get("apparent_temperature"),
        "relative_humidity_2m": cur.get("relative_humidity_2m"),
        "precipitation": cur.get("precipitation"),
        "rain": cur.get("rain"),
        "cloud_cover": cur.get("cloud_cover"),
        "pressure_msl": cur.get("pressure_msl"),
        "wind_speed_10m": cur.get("wind_speed_10m"),
        "weather_code": cur.get("weather_code"),
        "timezone": data.get("timezone", TIMEZONE),
        "ingested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": "open-meteo",
    }

def main():
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka_bootstrap,
        key_serializer=lambda k: k.encode("utf-8"),
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        linger_ms=50,
        acks="all",
    )

    last_time = {}
    print(f"[producer] topic={settings.kafka_topic_weather_raw} poll={settings.poll_seconds}s")

    while True:
        for city in CITIES:
            try:
                msg = fetch_current(city)
                cid = msg["city_id"]
                et = msg["event_time"]
                if last_time.get(cid) == et:
                    continue

                producer.send(settings.kafka_topic_weather_raw, key=cid, value=msg)
                producer.flush(10)

                last_time[cid] = et
                print(f"sent {cid} {et} temp={msg['temperature_2m']} rain={msg['rain']}")
            except Exception as e:
                print(f"[ERROR] {city['city_name']} -> {e}")

        time.sleep(settings.poll_seconds)

if __name__ == "__main__":
    main()
