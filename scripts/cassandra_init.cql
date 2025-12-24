CREATE KEYSPACE IF NOT EXISTS bdl_weather
WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1};

-- Observations (raw-ish, tapi sudah diparsing timestamp + bucket_date)
CREATE TABLE IF NOT EXISTS bdl_weather.weather_observations_by_city_day (
  city_id text,
  bucket_date date,
  event_time timestamp,

  city_name text,
  lat double,
  lon double,

  temperature_2m double,
  apparent_temperature double,
  relative_humidity_2m double,
  precipitation double,
  rain double,
  cloud_cover double,
  pressure_msl double,
  wind_speed_10m double,
  weather_code int,

  ingested_at timestamp,
  source text,

  PRIMARY KEY ((city_id, bucket_date), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);

-- Prediction results (1 jam ke depan)
CREATE TABLE IF NOT EXISTS bdl_weather.weather_temp_pred_by_city_day (
  city_id text,
  bucket_date date,
  target_time timestamp,

  feature_time timestamp,
  created_at timestamp,

  model_name text,
  model_version text,
  horizon_hours int,
  yhat_temperature_2m double,

  PRIMARY KEY ((city_id, bucket_date), target_time)
) WITH CLUSTERING ORDER BY (target_time DESC);
