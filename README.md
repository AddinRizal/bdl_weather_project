# BDL WeatherPulse — Realtime-ish Weather + ML Forecast (Next 1 Hour)

Aplikasi ini menampilkan **data cuaca per jam** (multi-kota) dan **prediksi suhu 1 jam ke depan**. Mode data ada 2:
1) **Streaming (Cassandra)**: data realtime-ish masuk lewat Kafka → Spark Structured Streaming → Cassandra → Dashboard.
2) **Historical (Archive)**: dashboard langsung ambil data historis dari Open-Meteo Archive (tanpa Kafka/Spark/Cassandra).

---

## 1) Arsitektur Singkat

**Streaming pipeline**
- `producer_openmeteo_current.py` (Producer) → publish JSON cuaca ke **Kafka**
- `spark_kafka_to_cassandra.py` (Consumer) → baca Kafka → tulis ke **Cassandra**
- `dashboard/app.py` → query Cassandra → tampilkan grafik + prediksi

**ML**
- `ml/train_temp_next1h.py` → training model → simpan ke folder `models/` (file `.joblib` + metadata `.json`)
- `dashboard/app.py` akan **load model yang sudah disimpan** untuk prediksi (tidak perlu training ulang setiap buka dashboard)

> **Tempat screenshot untuk laporan**:  
> `[GAMBAR] Diagram arsitektur (Kafka → Spark → Cassandra → Streamlit)`  
> `[GAMBAR] Dashboard tampilan grafik + prediksi`

---

## 2) Struktur Folder Penting

- `bdl_weather/dashboard/app.py`  
  Dashboard Streamlit (UI, grafik, query Cassandra, baca model ML untuk prediksi).

- `bdl_weather/producers/producer_openmeteo_current.py`  
  Producer: polling Open-Meteo lalu kirim ke Kafka topic.

- `bdl_weather/streaming/spark_kafka_to_cassandra.py`  
  Spark job: konsumsi Kafka → simpan ke Cassandra, pakai checkpoint di `checkpoints/`.

- `bdl_weather/ml/train_temp_next1h.py`  
  Script training model suhu 1 jam ke depan. Output ke folder `models/`.

- `models/`  
  Model per kota (`temp_next1h_<CITY>.joblib`) + metadata training (`temp_next1h_<CITY>.json`).

- `scripts/cassandra_init.cql`  
  Query untuk bikin keyspace + tabel Cassandra.

- `scripts/create_kafka_topics.sh`  
  Script untuk bikin Kafka topic (sekali di awal).

- `checkpoints/weather_stream/`  
  Folder checkpoint Spark (jangan dihapus kalau masih pakai streaming).

- `requirements.txt`  
  Dependencies Python.

---

## 3) Prasyarat

### Minimal untuk menjalankan **mode Historical (Archive)**
- Python 3.11+ (disarankan 3.11/3.12 untuk kompatibilitas package)
- `pip` / conda environment
- Koneksi internet (akses Open-Meteo)

### Tambahan untuk menjalankan **mode Streaming (Kafka + Spark + Cassandra)**
- **Java** (Spark butuh Java)
- **Apache Spark** (atau cukup `spark-submit` yang kompatibel dengan PySpark)
- **Kafka** (dan Zookeeper / KRaft sesuai instalasi)
- **Cassandra**

> Kalau kamu pakai Docker, stack Kafka+Cassandra jadi jauh lebih gampang (opsional).

---

## 4) First Time Setup (Sekali di Awal)

### 4.1 Clone repo & masuk folder project
```bash
git clone <repo-url-kamu>
cd bdl_weather_project
```

### 4.2 Buat environment + install dependency
**Opsi A (venv)**
```bash
python -m venv .venv
source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

**Opsi B (conda)**
```bash
conda create -n bdl_weather python=3.11 -y
conda activate bdl_weather
pip install -r requirements.txt
```

### 4.3 Set `PYTHONPATH` (penting)
Project ini import package `bdl_weather`, jadi pastikan root repo masuk PYTHONPATH:
```bash
export PYTHONPATH=$(pwd)
```

> Tips: Biar otomatis tiap buka terminal, kamu bisa taruh export ini di `.bashrc/.zshrc`.

### 4.4 Buat file `.env`
Buat `.env` di root project (selevel `requirements.txt`), contoh isinya:
```env
KAFKA_BOOTSTRAP=localhost:9092
KAFKA_TOPIC_WEATHER_RAW=weather.openmeteo.current.raw
POLL_SECONDS=60

CASSANDRA_HOST=127.0.0.1
CASSANDRA_PORT=9042
CASSANDRA_KEYSPACE=bdl_weather
CASSANDRA_TABLE_OBS=weather_observations_by_city_day
CASSANDRA_TABLE_PRED=weather_temp_pred_by_city_day

SPARK_CHECKPOINT_DIR=./checkpoints/weather_stream
SESSION_TZ=Asia/Jakarta

OPEN_METEO_FORECAST_URL=https://api.open-meteo.com/v1/forecast
OPEN_METEO_ARCHIVE_URL=https://archive-api.open-meteo.com/v1/archive

MODEL_DIR=./models
HORIZON_HOURS=1
```

---

## 5) First Time Setup untuk MODE STREAMING (Kafka + Cassandra)

> Kalau kamu hanya mau demo cepat tanpa streaming: kamu bisa skip bagian ini dan langsung pakai **mode Historical** (lihat bagian 6).

### 5.1 Jalankan Cassandra & Kafka
Silakan jalankan sesuai cara instalasi kamu (native atau docker).
- Pastikan Kafka listen di `localhost:9092`
- Pastikan Cassandra listen di `127.0.0.1:9042`

### 5.2 Inisialisasi Cassandra (sekali)
Jalankan CQL init:
```bash
cqlsh 127.0.0.1 9042 -f scripts/cassandra_init.cql
```

### 5.3 Buat Kafka topic (sekali)
Jalankan:
```bash
bash scripts/create_kafka_topics.sh
```

---

## 6) Training Model ML (Sekali di awal / kalau mau update model)

Model akan disimpan ke folder `models/`. Setelah ada model, dashboard tinggal load, **tidak training ulang otomatis**.

### Training 1 kota
```bash
python -m bdl_weather.ml.train_temp_next1h --city JKT --days 180
```

### Training semua kota yang ada di `bdl_weather/cities.py`
```bash
python -m bdl_weather.ml.train_temp_next1h --all --days 180
```

> Catatan:
> - `--days 180` artinya ambil 180 hari historis dari Open-Meteo Archive untuk training.
> - Training butuh internet karena fetch data archive.

---

## 7) Menjalankan Aplikasi (RUN PERTAMA KALI)

### 7.1 Mode Historical (paling gampang buat demo)
Cukup jalankan dashboard:
```bash
export PYTHONPATH=$(pwd)
streamlit run bdl_weather/dashboard/app.py
```
Lalu di UI pilih **Historical (Archive)**.

### 7.2 Mode Streaming (Full pipeline)
Jalankan **3 proses** (idealnya 3 terminal berbeda).

**Terminal A — Producer (Open-Meteo → Kafka)**
```bash
export PYTHONPATH=$(pwd)
python -m bdl_weather.producers.producer_openmeteo_current
```

**Terminal B — Spark Streaming (Kafka → Cassandra)**
```bash
export PYTHONPATH=$(pwd)

spark-submit \
  --packages \
org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1,org.apache.spark:spark-token-provider-kafka-0-10_2.12:3.5.1,com.datastax.spark:spark-cassandra-connector_2.12:3.5.1 \
  bdl_weather/streaming/spark_kafka_to_cassandra.py
```

**Terminal C — Dashboard Streamlit**
```bash
export PYTHONPATH=$(pwd)
streamlit run bdl_weather/dashboard/app.py
```
Lalu di UI pilih **Streaming (Cassandra)**.

---

## 8) Menjalankan Aplikasi di Hari-Hari Berikutnya (RUN RUTIN)

Biasanya yang dilakukan cuma ini:

1) Aktifkan environment
```bash
conda activate bdl_weather   # atau source .venv/bin/activate
cd bdl_weather_project
export PYTHONPATH=$(pwd)
```

2) Nyalakan service (kalau pakai streaming)
- Start Kafka
- Start Cassandra

3) Jalankan pipeline (kalau streaming)
- Producer (terminal 1)
- Spark job (terminal 2)
- Streamlit (terminal 3)

**Tidak perlu training ulang** tiap hari, kecuali kamu ingin model lebih update:
- misal 1 minggu sekali / kalau performa prediksi kurang bagus / atau kamu ubah fitur/model.

---

## 9) Quick Commands (Ringkas)

**Dashboard saja (Historical)**
```bash
export PYTHONPATH=$(pwd)
streamlit run bdl_weather/dashboard/app.py
```

**Train semua kota**
```bash
export PYTHONPATH=$(pwd)
python -m bdl_weather.ml.train_temp_next1h --all --days 180
```

---

## 10) Catatan Penting (Biar Tidak Bingung)

- Folder `models/` berisi model jadi. Dashboard hanya **load** model ini untuk prediksi.  
  Jadi **prediksi mengikuti hasil training terakhir yang tersimpan**.

- Folder `checkpoints/` dipakai Spark untuk menyimpan state streaming.  
  Kalau dihapus saat streaming masih jalan, Spark bisa reprocess data dari awal.

- Jika kamu deploy ke **Streamlit Cloud**, koneksi `localhost` ke Kafka/Cassandra **tidak bisa** (karena cloud bukan laptop kamu).  
  Untuk deployment cloud, biasanya demo pakai:
  - Mode **Historical (Archive)** (tanpa Cassandra), atau
  - Pakai Cassandra/Kafka yang benar-benar hosted (server/cloud).

---

## 11) (Opsional) Deploy Streamlit Cloud — Fix Umum

### 11.1 Error `Invalid format: please enter valid TOML` di Secrets
Secrets Streamlit Cloud harus format TOML, contoh:
```toml
KAFKA_BOOTSTRAP="localhost:9092"
KAFKA_TOPIC_WEATHER_RAW="weather.openmeteo.current.raw"
POLL_SECONDS="60"

CASSANDRA_HOST="127.0.0.1"
CASSANDRA_PORT="9042"
CASSANDRA_KEYSPACE="bdl_weather"
CASSANDRA_TABLE_OBS="weather_observations_by_city_day"
CASSANDRA_TABLE_PRED="weather_temp_pred_by_city_day"

SPARK_CHECKPOINT_DIR="./checkpoints/weather_stream"
SESSION_TZ="Asia/Jakarta"

OPEN_METEO_FORECAST_URL="https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL="https://archive-api.open-meteo.com/v1/archive"

MODEL_DIR="./models"
HORIZON_HOURS="1"
```

### 11.2 Error `ModuleNotFoundError: No module named 'bdl_weather'`
Di cloud, `PYTHONPATH` sering tidak otomatis seperti di lokal. Solusi paling aman:
Tambahkan di paling atas `bdl_weather/dashboard/app.py`:
```python
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[2]))
```
Ini akan menambahkan root repo ke path import.

> Tetapi walaupun import sudah beres, **Streaming (Cassandra)** tetap tidak jalan kalau Cassandra kamu masih `localhost`.

---

## 12) Lisensi
Untuk kebutuhan kelas/proyek kampus.
