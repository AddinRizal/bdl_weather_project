#!/usr/bin/env bash
set -euo pipefail

BOOTSTRAP=${1:-localhost:9092}

TOPICS=(
  "weather.openmeteo.current.raw"
)

for t in "${TOPICS[@]}"; do
  echo "Creating topic: $t"
  kafka-topics --bootstrap-server "$BOOTSTRAP" \
    --create --if-not-exists \
    --topic "$t" --partitions 1 --replication-factor 1
done
