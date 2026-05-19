#!/bin/sh
set -e

INTERVAL="${CRON_INTERVAL_SECONDS:-86400}"

echo "Starting daily digest worker (interval: ${INTERVAL}s)"

while true; do
  PYTHONPATH=/app python scripts/run_daily_cron.py
  sleep "$INTERVAL"
done
