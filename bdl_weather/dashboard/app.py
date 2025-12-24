# bdl_weather/dashboard/app.py
import json
import os
from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st
from cassandra.cluster import Cluster
from cassandra.query import dict_factory
from joblib import load

from bdl_weather.config import settings
from bdl_weather.cities import CITIES, TIMEZONE


def city_options():
    return {c["city_name"]: c["city_id"] for c in CITIES}


def get_session():
    cluster = Cluster([settings.cassandra_host], port=settings.cassandra_port)
    session = cluster.connect(settings.keyspace)
    session.row_factory = dict_factory
    return session


def fetch_timeseries(session, city_id: str, bucket_date: date, limit: int = 200) -> pd.DataFrame:
    q = f"""
    SELECT event_time,
           temperature_2m, apparent_temperature, relative_humidity_2m,
           precipitation, rain, cloud_cover, pressure_msl, wind_speed_10m,
           weather_code
    FROM {settings.table_obs}
    WHERE city_id = %s AND bucket_date = %s
    LIMIT {int(limit)};
    """
    rows = list(session.execute(q, (city_id, bucket_date)))
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["event_time"] = pd.to_datetime(df["event_time"])
    df = df.sort_values("event_time").reset_index(drop=True)
    return df


def load_model_and_meta(city_id: str):
    city_id = city_id.upper()
    model_path = os.path.join(settings.model_dir, f"temp_next1h_{city_id}.joblib")
    meta_path = os.path.join(settings.model_dir, f"temp_next1h_{city_id}.json")

    if not (os.path.exists(model_path) and os.path.exists(meta_path)):
        return None, None

    model = load(model_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    return model, meta


@st.cache_data(ttl=3600)
def fetch_archive_history(city_id: str, days: int = 90) -> pd.DataFrame:
    city_id = city_id.upper()
    city = next(c for c in CITIES if c["city_id"].upper() == city_id)

    end_d = date.today()
    start_d = end_d - timedelta(days=days)

    hourly_vars = [
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

    params = {
        "latitude": city["lat"],
        "longitude": city["lon"],
        "start_date": start_d.isoformat(),
        "end_date": end_d.isoformat(),
        "hourly": ",".join(hourly_vars),
        "timezone": TIMEZONE,
    }

    r = requests.get(settings.openmeteo_archive_url, params=params, timeout=30)
    r.raise_for_status()
    data = r.json()

    df = pd.DataFrame(data["hourly"])
    df["event_time"] = pd.to_datetime(df["time"])
    df = df.sort_values("event_time").reset_index(drop=True)

    # untuk fitur ML
    df["hour"] = df["event_time"].dt.hour
    df["dow"] = df["event_time"].dt.dayofweek
    return df


def add_explainers():
    with st.expander("📌 Cara membaca dashboard", expanded=True):
        st.markdown(
            """
**Apa yang kamu lihat di grafik ini?**

- **Temp (Aktual)** = suhu yang tercatat pada jam tersebut (data asli).
- Garis **Rata-rata 1 hari / 3 hari / 7 hari** = garis yang dibuat untuk **menghaluskan** data agar tren lebih mudah dibaca.

**Kenapa butuh garis rata-rata?**  
Karena suhu per jam itu naik-turun tajam (pagi–siang–malam). Garis rata-rata membantu melihat “arah umumnya”:
- **1 hari**: tren jangka pendek (hari ini vs kemarin)
- **3 hari**: tren beberapa hari
- **7 hari**: tren mingguan (lebih stabil)

**Grafik Prediksi (Next 1 Hour)**
- **Actual (t+1h)**: suhu sebenarnya 1 jam setelah waktu t  
- **Predicted (t+1h)**: hasil prediksi model untuk suhu 1 jam setelah waktu t  
Kalau kedua garis **dekat**, artinya prediksi model cukup bagus.
            """
        )


def plot_temperature_with_ma(df: pd.DataFrame, city_name: str, show_ma24: bool, show_ma72: bool, show_ma168: bool):
    df = df.copy()

    # moving average hourly -> 24 jam, 72 jam, 168 jam
    df["avg_1d"] = df["temperature_2m"].rolling(24, min_periods=3).mean()
    df["avg_3d"] = df["temperature_2m"].rolling(72, min_periods=5).mean()
    df["avg_7d"] = df["temperature_2m"].rolling(168, min_periods=10).mean()

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df["event_time"], y=df["temperature_2m"], name="Temp (Aktual)"))

    if show_ma24:
        fig.add_trace(go.Scatter(x=df["event_time"], y=df["avg_1d"], name="Rata-rata ~1 hari (lebih halus)"))
    if show_ma72:
        fig.add_trace(go.Scatter(x=df["event_time"], y=df["avg_3d"], name="Rata-rata ~3 hari (tren beberapa hari)"))
    if show_ma168:
        fig.add_trace(go.Scatter(x=df["event_time"], y=df["avg_7d"], name="Rata-rata ~7 hari (tren mingguan)"))

    fig.update_layout(
        title=f"Grafik Suhu — {city_name}",
        xaxis_title="Waktu",
        yaxis_title="°C",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    last_temp = float(df["temperature_2m"].iloc[-1])
    cols = st.columns(4)
    cols[0].metric("Suhu terakhir", f"{last_temp:.2f} °C")

    # safe get avg values (mungkin NaN di awal)
    def last_non_nan(s: pd.Series):
        s2 = s.dropna()
        return float(s2.iloc[-1]) if not s2.empty else None

    v1 = last_non_nan(df["avg_1d"])
    v3 = last_non_nan(df["avg_3d"])
    v7 = last_non_nan(df["avg_7d"])
    cols[1].metric("Rata-rata 1 hari", f"{v1:.2f} °C" if v1 is not None else "-")
    cols[2].metric("Rata-rata 3 hari", f"{v3:.2f} °C" if v3 is not None else "-")
    cols[3].metric("Rata-rata 7 hari", f"{v7:.2f} °C" if v7 is not None else "-")


def plot_actual_vs_pred(df: pd.DataFrame, city_id: str):
    model, meta = load_model_and_meta(city_id)
    if model is None:
        st.info(
            f"Model untuk {city_id} belum ada. Jalankan:\n"
            f"`python -m bdl_weather.ml.train_temp_next1h --city {city_id} --days 90`"
        )
        return

    df = df.copy()
    if "hour" not in df.columns:
        df["hour"] = df["event_time"].dt.hour
    if "dow" not in df.columns:
        df["dow"] = df["event_time"].dt.dayofweek

    features = meta["features"]
    df_feat = df.dropna(subset=features + ["temperature_2m"]).copy()
    if df_feat.empty:
        st.warning("Data tidak cukup untuk prediksi (ada nilai kosong/NaN).")
        return

    df_feat["pred_temp_next1h"] = model.predict(df_feat[features])
    df_feat["actual_temp_next1h"] = df_feat["temperature_2m"].shift(-1)

    st.caption(
        f"Model prediksi: {meta['best']['model']} | "
        f"Rata-rata selisih prediksi (MAE): {meta['best']['mae']:.3f} °C | "
        f"Pembanding sederhana (baseline): {meta['baseline']['mae']:.3f} °C"
    )

    with st.expander("ℹ️ Apa itu MAE / baseline?", expanded=False):
        st.markdown(
            """
- **MAE** (Mean Absolute Error) bisa dibaca sebagai **rata-rata selisih** antara prediksi dan nilai sebenarnya.  
  Contoh: MAE 0.43°C artinya rata-rata meleset sekitar 0.43°C.

- **Baseline** adalah pembanding yang sangat sederhana: “suhu 1 jam lagi ≈ suhu sekarang”.  
  Kalau model ML punya MAE lebih kecil dari baseline, berarti model ML **lebih baik** dari tebakan sederhana.
            """
        )

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_feat["event_time"], y=df_feat["actual_temp_next1h"], name="Suhu sebenarnya (1 jam setelah t)"))
    fig.add_trace(go.Scatter(x=df_feat["event_time"], y=df_feat["pred_temp_next1h"], name="Prediksi model (1 jam setelah t)"))
    fig.update_layout(
        title="Perbandingan Suhu Sebenarnya vs Prediksi (1 jam ke depan)",
        xaxis_title="Waktu (t)",
        yaxis_title="°C",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    latest_pred = float(df_feat["pred_temp_next1h"].iloc[-1])
    latest_time = df_feat["event_time"].iloc[-1]
    st.metric(
        "Prediksi suhu 1 jam ke depan (dari data terakhir)",
        f"{latest_pred:.2f} °C",
        help=f"Waktu data terakhir: {latest_time}",
    )


def main():
    st.set_page_config(page_title="BDL WeatherPulse", layout="wide")
    st.title("BDL WeatherPulse — Realtime Weather + ML Forecast (Next 1 Hour)")

    add_explainers()

    city_map = city_options()
    city_name = st.selectbox("Pilih kota", list(city_map.keys()), index=0)
    city_id = city_map[city_name]

    mode = st.radio(
        "Sumber data",
        ["Streaming (Cassandra)", "Historical (Archive)"],
        horizontal=True,
        help="Streaming = data dari pipeline Kafka→Spark→Cassandra. Historical = data historis beberapa hari terakhir dari Open-Meteo (lebih rame untuk analisis).",
    )

    colA, colB, colC = st.columns(3)
    show_ma24 = colA.checkbox("Tampilkan rata-rata 1 hari", value=True)
    show_ma72 = colB.checkbox("Tampilkan rata-rata 3 hari", value=True)
    show_ma168 = colC.checkbox("Tampilkan rata-rata 7 hari", value=True)

    if mode == "Streaming (Cassandra)":
        bucket = st.date_input("Tanggal data (untuk Cassandra)", value=date.today(), help="Cassandra menyimpan data per hari (partition).")
        limit = st.slider("Jumlah titik data (Streaming)", 20, 500, 200, 20)

        session = get_session()
        df = fetch_timeseries(session, city_id, bucket, limit=limit)
    else:
        hist_days = st.slider("Ambil data historis (hari)", 30, 180, 180, 30)
        df = fetch_archive_history(city_id, days=hist_days)

    if df.empty:
        st.warning("Belum ada data. Kalau mode Streaming pastikan producer + Spark consumer berjalan.")
        st.stop()

    plot_temperature_with_ma(df, city_name, show_ma24, show_ma72, show_ma168)

    st.divider()

    plot_actual_vs_pred(df, city_id)

    st.divider()
    st.subheader("Raw Data (contoh)")
    st.dataframe(df.tail(30), use_container_width=True)


if __name__ == "__main__":
    main()
