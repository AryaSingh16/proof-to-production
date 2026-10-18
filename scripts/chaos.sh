#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8081}"
PROM_URL="${PROM_URL:-http://localhost:9090}"

subcommand="${1:-}"

case "$subcommand" in
  app-kill)
    echo "==> Running chaos test: app-kill"
    echo "Killing app container..."
    START_TIME=$(date +%s)
    docker compose kill app
    RECOVERED=false
    for i in $(seq 1 30); do
      if curl -s -f -o /dev/null "$APP_URL/readyz" 2>/dev/null; then
        RECOVERED=true
        break
      fi
      sleep 1
    done
    if [ "$RECOVERED" != "true" ]; then
      echo "Restart policy did not bring container back within 30s; running docker compose up -d app"
      docker compose up -d app
      for i in $(seq 1 30); do
        if curl -s -f -o /dev/null "$APP_URL/readyz" 2>/dev/null; then
          RECOVERED=true
          break
        fi
        sleep 1
      done
    fi
    END_TIME=$(date +%s)
    RECOVERY_SECONDS=$((END_TIME - START_TIME))
    echo "app-kill recovered in ${RECOVERY_SECONDS}s"
    ;;

  db-kill)
    echo "==> Running chaos test: db-kill"
    COUNT_BEFORE=$(python3 -c "import urllib.request, json; resp=urllib.request.urlopen('$APP_URL/tasks'); print(len(json.loads(resp.read().decode())))")
    echo "Task count before stopping DB: $COUNT_BEFORE"
    echo "Stopping db container..."
    docker compose stop db
    sleep 2
    STATUS_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$APP_URL/readyz" || true)
    echo "/readyz HTTP status while db is stopped: $STATUS_CODE"
    echo "Starting db container..."
    docker compose start db
    echo "Waiting for readyz to return 200..."
    for i in $(seq 1 30); do
      if curl -s -f -o /dev/null "$APP_URL/readyz" 2>/dev/null; then
        break
      fi
      sleep 1
    done
    COUNT_AFTER=$(python3 -c "import urllib.request, json; resp=urllib.request.urlopen('$APP_URL/tasks'); print(len(json.loads(resp.read().decode())))")
    echo "Task count after DB recovery: $COUNT_AFTER"
    if [ "$COUNT_BEFORE" -ne "$COUNT_AFTER" ]; then
      echo "FAIL: Task count mismatch ($COUNT_BEFORE vs $COUNT_AFTER)"
      exit 1
    fi
    echo "PASS: db-kill recovered and task count is unchanged ($COUNT_AFTER tasks)"
    ;;

  errors)
    echo "==> Running chaos test: errors (generating 30% errors for 150s)..."
    python3 scripts/loadgen.py --url "$APP_URL" --duration 150 --rps 15 --error-rate 0.3
    echo "Polling Prometheus alerts API for up to 60s for AvailabilityFastBurn..."
    ALERT_STATE="not_found"
    for i in $(seq 1 30); do
      ALERTS_JSON=$(curl -s "$PROM_URL/api/v1/alerts" 2>/dev/null || true)
      if echo "$ALERTS_JSON" | grep -q "AvailabilityFastBurn"; then
        ALERT_STATE=$(echo "$ALERTS_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for a in data.get('data', {}).get('alerts', []):
        if a.get('labels', {}).get('alertname') == 'AvailabilityFastBurn':
            print(a.get('state', 'unknown'))
            sys.exit(0)
    print('unknown')
except Exception:
    print('unknown')
")
        break
      fi
      sleep 2
    done
    echo "State of AvailabilityFastBurn: $ALERT_STATE"
    ;;

  latency)
    echo "==> Running chaos test: latency (generating 50% slow requests for 150s)..."
    python3 scripts/loadgen.py --url "$APP_URL" --duration 150 --rps 15 --slow-rate 0.5
    echo "Polling Prometheus alerts API for up to 60s for LatencyBudgetBurn..."
    ALERT_STATE="not_found"
    for i in $(seq 1 30); do
      ALERTS_JSON=$(curl -s "$PROM_URL/api/v1/alerts" 2>/dev/null || true)
      if echo "$ALERTS_JSON" | grep -q "LatencyBudgetBurn"; then
        ALERT_STATE=$(echo "$ALERTS_JSON" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for a in data.get('data', {}).get('alerts', []):
        if a.get('labels', {}).get('alertname') == 'LatencyBudgetBurn':
            print(a.get('state', 'unknown'))
            sys.exit(0)
    print('unknown')
except Exception:
    print('unknown')
")
        break
      fi
      sleep 2
    done
    echo "State of LatencyBudgetBurn: $ALERT_STATE"
    ;;

  *)
    echo "Usage: $0 {app-kill|db-kill|errors|latency}"
    exit 1
    ;;
esac
