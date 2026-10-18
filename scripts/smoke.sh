#!/usr/bin/env bash
set -euo pipefail

APP_URL="${APP_URL:-http://localhost:8081}"
PROM_URL="${PROM_URL:-http://localhost:9090}"
GRAFANA_URL="${GRAFANA_URL:-http://localhost:3000}"

echo "==> Checking healthz and readyz..."
curl -fsS "$APP_URL/healthz" > /dev/null || { echo "FAIL: healthz check failed"; exit 1; }
curl -fsS "$APP_URL/readyz" > /dev/null || { echo "FAIL: readyz check failed"; exit 1; }
echo "PASS: healthz and readyz return 200"

echo "==> Creating and listing a task..."
TASK=$(curl -fsS -X POST "$APP_URL/tasks" -H 'Content-Type: application/json' -d '{"title":"smoke test task"}')
TASK_ID=$(echo "$TASK" | grep -o '"id":[0-9]*' | cut -d: -f2)
if [ -z "$TASK_ID" ]; then
  echo "FAIL: could not parse task id from response"
  exit 1
fi
curl -fsS "$APP_URL/tasks" | grep -q "smoke test task" || { echo "FAIL: task not in task list"; exit 1; }
echo "PASS: create and list task succeeded (id: $TASK_ID)"

echo "==> Checking /metrics endpoint..."
curl -fsS "$APP_URL/metrics" | grep -q "http_requests_total" || { echo "FAIL: /metrics does not contain http_requests_total"; exit 1; }
echo "PASS: /metrics contains http_requests_total"

echo "==> Checking Prometheus target for task-api (retrying up to 60s)..."
TARGET_UP=false
for i in $(seq 1 30); do
  if curl -fsS "$PROM_URL/api/v1/targets" 2>/dev/null | grep -q 'task-api.*health.:.up'; then
    TARGET_UP=true
    break
  fi
  sleep 2
done
if [ "$TARGET_UP" != "true" ]; then
  echo "FAIL: Prometheus target task-api not up after 60s"
  exit 1
fi
echo "PASS: Prometheus target for task-api is up"

echo "==> Checking Prometheus rules are loaded (retrying up to 60s)..."
RULES_LOADED=false
for i in $(seq 1 30); do
  if curl -fsS "$PROM_URL/api/v1/rules" 2>/dev/null | grep -q "AvailabilityFastBurn"; then
    RULES_LOADED=true
    break
  fi
  sleep 2
done
if [ "$RULES_LOADED" != "true" ]; then
  echo "FAIL: Prometheus rules not loaded after 60s"
  exit 1
fi
echo "PASS: Prometheus rules loaded"

echo "==> Checking Grafana dashboard exists (retrying up to 60s)..."
DASHBOARD_EXISTS=false
for i in $(seq 1 30); do
  if curl -fsS "$GRAFANA_URL/api/search?query=Task" 2>/dev/null | grep -q "Task API Overview"; then
    DASHBOARD_EXISTS=true
    break
  fi
  sleep 2
done
if [ "$DASHBOARD_EXISTS" != "true" ]; then
  echo "FAIL: Grafana dashboard Task API Overview not found after 60s"
  exit 1
fi
echo "PASS: Grafana dashboard exists"

echo "All smoke tests passed successfully!"
