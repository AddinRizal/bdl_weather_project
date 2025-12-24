# bdl_weather/dashboard/app.py
from __future__ import annotations

import sys
from pathlib import Path

# Pastikan root repo masuk ke PYTHONPATH (penting untuk Streamlit Cloud)
ROOT = Path(__file__).resolve().parents[2]  # .../bdl_weather_project
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, from_json, to_timestamp, to_date
from pyspark.sql.types import StructType, StructField, StringType, DoubleType, IntegerType

from bdl_weather.config import settings

schema = StructType([
    StructField("city_id", StringType()),
    StructField("city_name", StringType()),
    StructField("lat", DoubleType()),
    StructField("lon", DoubleType()),
    StructField("event_time", StringType()),

    StructField("temperature_2m", DoubleType()),
    StructField("apparent_temperature", DoubleType()),
    StructField("relative_humidity_2m", DoubleType()),
    StructField("precipitation", DoubleType()),
    StructField("rain", DoubleType()),
    StructField("cloud_cover", DoubleType()),
    StructField("pressure_msl", DoubleType()),
    StructField("wind_speed_10m", DoubleType()),
    StructField("weather_code", IntegerType()),

    StructField("timezone", StringType()),
    StructField("ingested_at", StringType()),
    StructField("source", StringType()),
])

def main():
    spark = (
        SparkSession.builder
        .appName("bdl_weather_stream")
        .config("spark.sql.session.timeZone", settings.session_tz)
        .config("spark.cassandra.connection.host", settings.cassandra_host)
        .config("spark.cassandra.connection.port", str(settings.cassandra_port))
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    df = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka_bootstrap)
        .option("subscribe", settings.kafka_topic_weather_raw)
        .option("startingOffsets", "latest")
        .load()
    )

    parsed = (
        df.selectExpr("CAST(value AS STRING) AS json_str")
        .select(from_json(col("json_str"), schema).alias("d"))
        .select("d.*")
    )

    enriched = (
        parsed
        .withColumn("event_time", to_timestamp(col("event_time"), "yyyy-MM-dd'T'HH:mm"))
        .withColumn("bucket_date", to_date(col("event_time")))
        .withColumn("ingested_at", to_timestamp(col("ingested_at"), "yyyy-MM-dd'T'HH:mm:ssX"))
    )

    out_cols = [
        "city_id", "bucket_date", "event_time",
        "city_name", "lat", "lon",
        "temperature_2m", "apparent_temperature", "relative_humidity_2m",
        "precipitation", "rain", "cloud_cover", "pressure_msl", "wind_speed_10m", "weather_code",
        "ingested_at", "source"
    ]
    final_df = enriched.select(*out_cols)

    def write_batch(batch_df, batch_id: int):
        (batch_df.write
         .format("org.apache.spark.sql.cassandra")
         .mode("append")
         .options(keyspace=settings.keyspace, table=settings.table_obs)
         .save())

    q = (
        final_df.writeStream
        .foreachBatch(write_batch)
        .option("checkpointLocation", settings.checkpoint_dir)
        .start()
    )
    q.awaitTermination()

if __name__ == "__main__":
    main()
