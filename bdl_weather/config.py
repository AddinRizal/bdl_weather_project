import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    # Kafka
    kafka_bootstrap: str = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
    kafka_topic_weather_raw: str = os.getenv("KAFKA_TOPIC_WEATHER_RAW", "weather.openmeteo.current.raw")
    poll_seconds: float = float(os.getenv("POLL_SECONDS", "60"))

    # Cassandra
    cassandra_host: str = os.getenv("CASSANDRA_HOST", "127.0.0.1")
    cassandra_port: int = int(os.getenv("CASSANDRA_PORT", "9042"))
    keyspace: str = os.getenv("CASSANDRA_KEYSPACE", "bdl_weather")
    table_obs: str = os.getenv("CASSANDRA_TABLE_OBS", "weather_observations_by_city_day")
    table_pred: str = os.getenv("CASSANDRA_TABLE_PRED", "weather_temp_pred_by_city_day")

    # Spark
    checkpoint_dir: str = os.getenv("SPARK_CHECKPOINT_DIR", "./checkpoints/weather_stream")
    session_tz: str = os.getenv("SESSION_TZ", "Asia/Jakarta")

    # Open-Meteo
    openmeteo_forecast_url: str = os.getenv("OPEN_METEO_FORECAST_URL", "https://api.open-meteo.com/v1/forecast")
    openmeteo_archive_url: str = os.getenv("OPEN_METEO_ARCHIVE_URL", "https://archive-api.open-meteo.com/v1/archive")

    # ML
    model_dir: str = os.getenv("MODEL_DIR", "./models")
    horizon_hours: int = int(os.getenv("HORIZON_HOURS", "1"))

settings = Settings()
