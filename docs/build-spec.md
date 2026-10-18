devsecops-observability-pipeline: Build Spec for the Coding Agent
Prepared for Antigravity (Gemini). Goal: a working, interview-ready project built in about 60 to 90 minutes, zero cloud cost, designed to run inside a 1.5 GB WSL memory budget.
0. Rules for the agent (read first)
1. Work inside WSL2 Ubuntu, in the project folder. No sudo. Install nothing beyond what Section 2 lists. All security and test tools run as Docker containers, never installed on the host.
2. Follow the phases in order. Every phase ends with a GATE (commands that must pass). If a gate fails: inspect with docker compose logs and docker logs, try at most 3 fixes, then STOP and report the failing command and its full output. Never skip or weaken a gate.
3. No Kubernetes, no extra services, no extra frameworks. The total running stack must stay under about 700 MiB. Every service gets a mem_limit exactly as specified.
4. Use the pinned versions in this doc. Never use the latest tag. If a pinned tag cannot be pulled, choose the nearest existing tag of the same major version and tell the human which one you used.
5. After each passing gate, git commit with the message 'phase-N: short summary'.
6. Makefile recipe lines must start with a TAB.
7. Add a .gitattributes containing '* text=auto eol=lf' so shell scripts never get CRLF endings. Make scripts executable (chmod +x).
8. Use docker compose (v2 plugin), never docker-compose.
9. No real secrets anywhere. Passwords in compose.yaml are local-demo placeholders and the README must say so.
1. What we are building
A small Task API (FastAPI + PostgreSQL) run with Docker Compose, wrapped in a DevSecOps supply-chain pipeline on GitHub Actions: tests, secret scanning, SAST, image vulnerability scanning, SBOM generation, keyless image signing with Cosign, publishing to GHCR, and a deploy script that REFUSES to run any image whose signature does not verify. A lightweight Prometheus + Grafana stack adds SLO burn-rate alerting, plus chaos scripts that break the system on purpose. Interview story: nothing reaches deployment unless it is scanned, signed and verified, and when it runs we can see its health against an SLO.
commit / PR
   -> tests + lint | gitleaks (secrets) | semgrep (SAST)
   -> docker build -> trivy scan (fail on CRITICAL/HIGH fixable)
   -> push to GHCR (main only) -> SBOM (syft, SPDX)
   -> cosign sign + attest (keyless, GitHub OIDC)
   -> deploy script: cosign verify  --> refuse if unsigned
   -> docker compose up: app + postgres + prometheus + grafana
Host ports: 8081 app, 3000 Grafana, 9090 Prometheus, all bound to 127.0.0.1.
2. Prerequisites (the human installs these before the agent starts)
WSL2 Ubuntu, Docker (Desktop with WSL integration, or Docker Engine inside WSL) with the compose v2 plugin, make, git, curl, python3 (standard library only on the host). WSL memory limit 1.5 GB (see the .wslconfig note in the human checklist). Internet access to docker.io, ghcr.io and the Sigstore services.
3. Repo layout
devsecops-observability-pipeline/
  app/          __init__.py config.py storage.py metrics.py main.py healthcheck.py
  tests/        test_api.py
  monitoring/   prometheus.yml rules.yml
  monitoring/grafana/   datasource.yml provider.yml dashboards/task-api.json
  scripts/      loadgen.py smoke.sh chaos.sh verify-image.sh
  docs/         architecture.md slo.md security-pipeline.md
  .github/workflows/ci.yml
  .github/dependabot.yml
  compose.yaml Dockerfile .dockerignore .gitignore .gitattributes Makefile
  requirements.txt requirements-dev.txt README.md SECURITY.md LICENSE
4. Phases
Phase 0: Preflight
Run and report: docker info, docker compose version, make --version, curl --version, python3 --version, free -m. Ports 8081, 3000 and 9090 must be free: ss -ltn | grep -E ':(8081|3000|9090) ' must print nothing.
GATE: every tool prints a version, docker info succeeds, ports are free.
Phase 1: Application and unit tests
requirements.txt:
fastapi==0.115.0
uvicorn==0.30.6
psycopg[binary,pool]==3.2.3
prometheus-client==0.21.0
requirements-dev.txt: -r requirements.txt, pytest==8.3.3, httpx==0.27.2, ruff==0.6.9.
App spec:
• config.py reads env vars: STORAGE ('postgres' default, or 'memory'), DATABASE_URL, ENABLE_FAULT_INJECTION ('false' default).
• storage.py has MemoryStore and PostgresStore with the same methods: init(), ping(), create(title), list(), get(id), delete(id). Task fields: id, title, done (default false), created_at. PostgresStore uses psycopg_pool.ConnectionPool (min 1, max 4) with dict_row. init() runs CREATE TABLE IF NOT EXISTS tasks (id SERIAL PRIMARY KEY, title TEXT NOT NULL, done BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMPTZ NOT NULL DEFAULT now()) and retries the connection up to 30 times, 2 seconds apart, then raises.
• main.py exposes create_app(store=None) and a module-level app = create_app(). Endpoints: POST /tasks (body {title}, 1 to 200 chars, returns 201), GET /tasks, GET /tasks/{task_id} (404 if missing), DELETE /tasks/{task_id} (204, or 404), GET /healthz (always 200, no DB), GET /readyz (200 if store.ping() works, else 503), GET /metrics (prometheus_client ASGI app).
• Declare the task endpoints with plain def, not async def, because the Postgres pool is synchronous.
• If ENABLE_FAULT_INJECTION is 'true', also register GET /debug/error (returns 500) and GET /debug/slow?ms=N (async sleep, N capped at 5000). Otherwise these routes must not exist (404).
• metrics.py defines at module level: Counter http_requests_total{method,path,status}, Histogram http_request_duration_seconds{method,path} with buckets 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, and Counter tasks_created_total.
• An HTTP middleware records both HTTP metrics. The path label MUST be the route template (for example /tasks/{task_id}), read from request.scope.get('route').path after call_next, falling back to 'unmatched'. Never use the raw URL. Skip /metrics, /healthz and /readyz. If call_next raises, record status 500 and re-raise.
• healthcheck.py: when run as python -m app.healthcheck, it opens http://127.0.0.1:8000/healthz with urllib (timeout 2s) and exits 0 on HTTP 200, otherwise exits 1.
• Run uvicorn with a single worker. Do not add --workers.
tests/test_api.py uses fastapi TestClient with create_app(MemoryStore()). Cover: healthz and readyz return 200; the create, list, get and delete flow; 404 on an unknown id; 422 on an empty title; /metrics contains http_requests_total with a path label of /tasks/{task_id} after a GET on a task; /debug/error returns 404 when fault injection is off and 500 when on (monkeypatch the env, then call create_app()).
Makefile targets (Docker only, no host install): test runs docker run --rm -v $(PWD):/w -w /w python:3.12-slim sh -c 'pip install -q -r requirements-dev.txt && pytest -q'; lint runs the same container with ruff check ..
GATE: make lint and make test both pass.
Phase 2: Image and core stack (app + database)
Dockerfile (the CMD must be valid JSON exec form with double quotes in the real file):
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd --uid 10001 --no-create-home appuser
USER 10001
EXPOSE 8000
CMD ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000']
compose.yaml (start with db and app; Phase 3 adds the monitoring services to the same file):
name: obs
services:
  db:
    image: postgres:16-alpine
    command: postgres -c shared_buffers=32MB -c max_connections=20
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app-demo-pass
      POSTGRES_DB: tasks
    volumes: [pgdata:/var/lib/postgresql/data]
    mem_limit: 160m
    healthcheck:
      test: ['CMD-SHELL', 'pg_isready -U app -d tasks']
      interval: 5s
      timeout: 3s
      retries: 20
    restart: unless-stopped
  app:
    build: .
    image: ${APP_IMAGE:-task-api:dev}
    depends_on:
      db: {condition: service_healthy}
    environment:
      DATABASE_URL: postgresql://app:app-demo-pass@db:5432/tasks
      ENABLE_FAULT_INJECTION: 'true'
    ports: ['127.0.0.1:8081:8000']
    mem_limit: 128m
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: ['no-new-privileges:true']
    healthcheck:
      test: ['CMD', 'python', '-m', 'app.healthcheck']
      interval: 5s
      timeout: 3s
      retries: 12
      start_period: 5s
    restart: unless-stopped
volumes:
  pgdata:
Makefile targets: build (docker compose build), up (docker compose up -d --build --wait), down (docker compose down), clean (docker compose down -v), ps, logs (docker compose logs -f --tail=100), mem (docker stats --no-stream --format '{{.Name}} {{.MemUsage}}').
GATE: make up succeeds. curl -fsS localhost:8081/readyz returns 200. curl -fsS -X POST localhost:8081/tasks -H 'Content-Type: application/json' -d '{"title":"hello"}' returns a task and curl -fsS localhost:8081/tasks lists it. docker inspect obs-app-1 --format '{{.Config.User}}' prints 10001.
Phase 3: Monitoring and SLOs
Add two services to compose.yaml, and add them to up:
• prometheus: image prom/prometheus:v2.54.1; command list [--config.file=/etc/prometheus/prometheus.yml, --storage.tsdb.path=/prometheus, --storage.tsdb.retention.time=2h, --web.enable-lifecycle]; bind mounts ./monitoring/prometheus.yml to /etc/prometheus/prometheus.yml (read-only) and ./monitoring/rules.yml to /etc/prometheus/rules/rules.yml (read-only); port 127.0.0.1:9090:9090; mem_limit 192m; healthcheck CMD-SHELL wget -qO- http://localhost:9090/-/ready || exit 1 (interval 5s, retries 20); restart unless-stopped.
• grafana: image grafana/grafana:11.2.0; env GF_SECURITY_ADMIN_PASSWORD=admin, GF_AUTH_ANONYMOUS_ENABLED=true, GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer, GF_ANALYTICS_REPORTING_ENABLED=false, GF_ANALYTICS_CHECK_FOR_UPDATES=false; bind mounts (read-only) ./monitoring/grafana/datasource.yml to /etc/grafana/provisioning/datasources/datasource.yml, ./monitoring/grafana/provider.yml to /etc/grafana/provisioning/dashboards/provider.yml, and ./monitoring/grafana/dashboards to /var/lib/grafana-dashboards; port 127.0.0.1:3000:3000; mem_limit 192m; depends_on prometheus; healthcheck CMD-SHELL wget -qO- http://localhost:3000/api/health || exit 1 (interval 5s, retries 30); restart unless-stopped.
monitoring/prometheus.yml:
global:
  scrape_interval: 15s
  evaluation_interval: 15s
rule_files:
  - /etc/prometheus/rules/*.yml
scrape_configs:
  - job_name: task-api
    static_configs:
      - targets: ['app:8000']
  - job_name: prometheus
    static_configs:
      - targets: ['localhost:9090']
SLOs: availability 99.5% (error budget 0.5%, about 3h36m per 30 days) and latency 95% of requests under 500 ms (budget 5%). Burn rate is the bad-request ratio divided by the budget. Each burn alert needs BOTH a long and a short window above the threshold: the long window proves the problem is real, the short one proves it is still happening. The windows here are scaled down for the demo because Prometheus keeps only 2 hours; the README must say production would use 1h/5m for the 14.4x alert and 6h/30m for the 6x alert.
monitoring/rules.yml:
groups:
  - name: task-api
    rules:
      - record: task_api:error_ratio:rate1m
        expr: sum(rate(http_requests_total{job='task-api',status=~'5..'}[1m])) / sum(rate(http_requests_total{job='task-api'}[1m]))
      - record: task_api:error_ratio:rate5m
        expr: sum(rate(http_requests_total{job='task-api',status=~'5..'}[5m])) / sum(rate(http_requests_total{job='task-api'}[5m]))
      - record: task_api:error_ratio:rate30m
        expr: sum(rate(http_requests_total{job='task-api',status=~'5..'}[30m])) / sum(rate(http_requests_total{job='task-api'}[30m]))
      - record: task_api:latency_bad_ratio:rate1m
        expr: 1 - (sum(rate(http_request_duration_seconds_bucket{job='task-api',le='0.5'}[1m])) / sum(rate(http_request_duration_seconds_count{job='task-api'}[1m])))
      - record: task_api:latency_bad_ratio:rate5m
        expr: 1 - (sum(rate(http_request_duration_seconds_bucket{job='task-api',le='0.5'}[5m])) / sum(rate(http_request_duration_seconds_count{job='task-api'}[5m])))
      - alert: TaskApiDown
        expr: up{job='task-api'} == 0
        for: 30s
        labels: {severity: page}
        annotations: {summary: 'task-api is down'}
      - alert: AvailabilityFastBurn
        expr: task_api:error_ratio:rate5m > (14.4 * 0.005) and task_api:error_ratio:rate1m > (14.4 * 0.005)
        for: 1m
        labels: {severity: page, slo: availability}
        annotations: {summary: 'Availability error budget burning at more than 14.4x'}
      - alert: AvailabilitySlowBurn
        expr: task_api:error_ratio:rate30m > (6 * 0.005) and task_api:error_ratio:rate5m > (6 * 0.005)
        for: 2m
        labels: {severity: ticket, slo: availability}
        annotations: {summary: 'Availability error budget burning at more than 6x'}
      - alert: LatencyBudgetBurn
        expr: task_api:latency_bad_ratio:rate5m > (6 * 0.05) and task_api:latency_bad_ratio:rate1m > (6 * 0.05)
        for: 1m
        labels: {severity: ticket, slo: latency}
        annotations: {summary: 'Latency error budget burning at more than 6x'}
The le value '0.5' must match an existing histogram bucket exactly (it does).
Grafana: datasource.yml provisions one Prometheus datasource (apiVersion 1, name Prometheus, type prometheus, uid prometheus, url http://prometheus:9090, access proxy, isDefault true). provider.yml is a file provider reading /var/lib/grafana-dashboards (apiVersion 1, one provider named default, type file, options path). dashboards/task-api.json is a valid Grafana dashboard titled 'Task API Overview', uid task-api-overview, every panel using the datasource {type: prometheus, uid: prometheus}. Panels: request rate by path; 5xx error ratio; latency p50/p95/p99; service up (up{job='task-api'}); requests by status code; tasks created per minute; then a row 'SLOs' with availability SLI (1 - task_api:error_ratio:rate5m, stat), availability burn rate (task_api:error_ratio:rate5m / 0.005, time series with threshold lines at 6 and 14.4), latency SLI (1 - task_api:latency_bad_ratio:rate5m, stat) and latency burn rate (task_api:latency_bad_ratio:rate5m / 0.05, time series with a threshold line at 6). 'No data' while there is no traffic is acceptable. Validate the JSON with python3 -m json.tool before starting.
GATE: make up succeeds with all four services healthy; curl -fsS localhost:9090/api/v1/targets | grep -q 'health.:.up'; curl -fsS localhost:9090/api/v1/rules | grep -q AvailabilityFastBurn; curl -fsS 'localhost:3000/api/search?query=Task' | grep -q 'Task API Overview'; curl -fsS -u admin:admin 'localhost:3000/api/datasources/proxy/uid/prometheus/api/v1/query?query=up' | grep -q success; make mem output reported to the human, with the sum of the four containers under about 700 MiB at idle.
Phase 4: Load, chaos and smoke tests
scripts/loadgen.py: standard library only (urllib, threading, argparse). Flags --url (default http://localhost:8081), --duration (default 60), --rps (default 10), --error-rate (default 0), --slow-rate (default 0). Traffic mix: about 60% POST /tasks, 30% GET /tasks, 10% GET or DELETE by id. error-rate sends that fraction of requests to /debug/error, slow-rate to /debug/slow?ms=800. Print counts by status at the end and tolerate connection errors without crashing. Keep it to 4 threads at most.
scripts/smoke.sh (set -euo pipefail, curl -fsS, retries up to 60s where noted): healthz and readyz return 200; create then list a task; /metrics contains http_requests_total; the Prometheus target for task-api is up (retry); rules are loaded (retry); the Grafana dashboard exists (retry). Exit non-zero with a clear message on any failure.
scripts/chaos.sh subcommands (print what it does and the result):
• app-kill: run docker compose kill app, wait up to 30s for the restart policy to bring it back (if it does not, run docker compose up -d app and say so), poll /readyz until 200, print the recovery seconds.
• db-kill: record the task count, docker compose stop db, show /readyz returning 503, docker compose start db, wait for recovery, confirm the task count is unchanged (named volume persistence).
• errors: loadgen with --error-rate 0.3 for 150s, then poll the alerts API for up to 60s and print the state of AvailabilityFastBurn.
• latency: loadgen with --slow-rate 0.5 for 150s, then print the state of LatencyBudgetBurn.
Makefile targets: smoke, loadgen, chaos-app, chaos-db, chaos-errors, chaos-latency.
GATE: make smoke passes. make chaos-app and make chaos-db report recovery and an unchanged task count. After make chaos-errors, curl -s localhost:9090/api/v1/alerts | grep -q AvailabilityFastBurn (pending or firing is accepted). make mem still shows the total under about 700 MiB.
Phase 5: Supply-chain scripts (verify before deploy)
scripts/verify-image.sh IMAGE: requires env REPO_SLUG in the form owner/repo (exit 2 with a usage message if unset). It runs Cosign through Docker (gcr.io/projectsigstore/cosign:v2.4.1) with verify --certificate-identity https://github.com/$REPO_SLUG/.github/workflows/ci.yml@refs/heads/main --certificate-oidc-issuer https://token.actions.githubusercontent.com IMAGE. On failure it prints 'REFUSING TO DEPLOY: signature verification failed' and exits non-zero. On success it prints 'signature verified' and exits 0. Use the exact identity flag, not a regex.
Makefile targets:
• verify IMAGE=... REPO_SLUG=... runs the script.
• deploy-verified IMAGE=... REPO_SLUG=... runs verify first, then APP_IMAGE=$(IMAGE) docker compose pull app and APP_IMAGE=$(IMAGE) docker compose up -d --no-build --wait. If verify fails, nothing is deployed.
• scan (optional local scans; print a warning to run make down first on low-memory machines): gitleaks via docker run --rm --memory 256m --user $(id -u):$(id -g) -v $(PWD):/repo -w /repo zricethezav/gitleaks:v8.21.2 detect --source . --redact, then Trivy via docker run --rm --memory 768m -v /var/run/docker.sock:/var/run/docker.sock -v $(HOME)/.cache/trivy:/root/.cache aquasec/trivy:0.57.0 image --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 task-api:dev. Use $$ escaping inside the Makefile where needed.
GATE: REPO_SLUG=someone/somerepo make verify IMAGE=python:3.12-slim MUST fail with the REFUSING message and a non-zero exit code (an image with no signature is rejected). Report that result. Do not try to make it pass.
Phase 6: CI/CD pipeline
Create .github/workflows/ci.yml exactly as below, then adapt only if actionlint reports a real problem:
name: ci
on:
  push:
    branches: [main]
  pull_request:
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: '3.12'}
      - run: pip install -r requirements-dev.txt
      - run: ruff check .
      - run: pytest -q
  secret-scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: read
    steps:
      - uses: actions/checkout@v4
        with: {fetch-depth: 0}
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  sast:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker run --rm -v ${{ github.workspace }}:/src -w /src semgrep/semgrep:1.90.0 semgrep scan --config p/python --config p/dockerfile --error
  e2e:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker compose up -d --build --wait
      - run: ./scripts/smoke.sh
      - if: failure()
        run: docker compose logs --no-color
      - if: always()
        run: docker compose down -v
  image:
    needs: [test, secret-scan, sast]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
      id-token: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/build-push-action@v6
        with:
          context: .
          load: true
          tags: task-api:ci
          provenance: false
      - uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: task-api:ci
          severity: CRITICAL,HIGH
          ignore-unfixed: true
          exit-code: '1'
      - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: echo IMAGE=ghcr.io/${GITHUB_REPOSITORY,,} >> $GITHUB_ENV
      - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        id: push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          provenance: false
      - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: anchore/sbom-action@v0.17.7
        with:
          image: ${{ env.IMAGE }}@${{ steps.push.outputs.digest }}
          format: spdx-json
          output-file: sbom.spdx.json
      - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        uses: sigstore/cosign-installer@v3.7.0
      - if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        run: |
          cosign sign --yes ${IMAGE}@${{ steps.push.outputs.digest }}
          cosign attest --yes --type spdxjson --predicate sbom.spdx.json ${IMAGE}@${{ steps.push.outputs.digest }}
Note on the push step: docker/metadata-action is not used, so the image tag uses github.repository directly; GHCR requires lowercase, so if the repository owner or name contains capitals, compute the lowercase name once into the IMAGE variable and use ${{ env.IMAGE }} in the tags line instead.
.github/dependabot.yml: weekly updates for the pip, docker and github-actions ecosystems, all at directory '/'.
GATE: lint the workflows with docker run --rm -v $(PWD):/repo -w /repo rhysd/actionlint:1.7.3 -color and fix every real finding; the dependabot file parses as YAML. Tell the human CI cannot run locally and that the first push is the real test.
Phase 7: Documentation
README.md: a one-paragraph pitch; badges placeholder for the CI status; the mermaid pipeline diagram from Section 1; quickstart (make up, URLs, make smoke, make down); a demo script (loadgen, then chaos-errors, watch the Grafana SLO row and the Prometheus Alerts page, then chaos-db); the supply-chain flow, including how to run make deploy-verified with a CI-built image and how the refusal demo works (make verify IMAGE=python:3.12-slim REPO_SLUG=...); a Design decisions section (route-template metric labels to avoid cardinality explosion, single uvicorn worker, healthchecks with depends_on, non-root and read-only container, capability drop, memory limits, keyless signing instead of long-lived keys, exact cosign identity pinning, multi-window burn-rate alerts); a Limitations section (demo-scaled alert windows, 100% fixed credentials are demo-only, no Kubernetes, no Alertmanager, no SLSA provenance, local scans need the stack stopped on low-memory machines); a screenshots section with placeholder paths in docs/img/; a credits line saying the idea was inspired by the open-source Caesarsage/DevOps-Cloud-Projects repo. Add an MIT LICENSE and a short SECURITY.md (how to report a vulnerability).
docs/security-pipeline.md: the pipeline stages and a table of what each control catches (secrets in history, insecure code patterns, vulnerable packages, tampered or unsigned images) and what it does not. docs/slo.md: the SLIs, the SLOs, the error budget arithmetic, the alert table with demo versus production windows, and why multi-window multi-burn-rate beats a simple threshold alert. docs/architecture.md: a longer mermaid diagram and the request and data flow.
GATE: every command in the README works as written.
Phase 8: Clean-room verification
Run make clean && make up && make smoke && make test && make lint && make mem. git status must be clean and git log --oneline must show one commit per phase.
5. Known pitfalls
• mem_limit works in compose v2 outside swarm; do not replace it with deploy.resources.
• After editing monitoring/prometheus.yml or rules.yml, reload with curl -X POST localhost:9090/-/reload (the lifecycle flag is on).
• Bind-mounted files must exist before docker compose up, otherwise Docker creates a directory in their place.
• The app container is read-only; anything that writes must use the /tmp tmpfs.
• Rebuilding: make up rebuilds the image because compose.yaml has a build section.
• Cosign verification needs the image to be PUBLIC on GHCR (package visibility is a human step) and network access to Sigstore.
• If Trivy fails to download its database because of rate limiting, re-run the job; if it fails on unfixable base-image findings, keep ignore-unfixed on and relax severity to CRITICAL, and document that in the README.
• If a gate needs more than 3 attempts, stop and report. Do not improvise a different architecture.
6. Definition of done
make up from a clean state produces four healthy containers using under about 700 MiB; make smoke, make test and make lint pass; the Grafana dashboard shows live traffic and the SLO row; make chaos-errors triggers AvailabilityFastBurn; make verify rejects an unsigned image; the workflow file passes actionlint; the README and docs are complete; the git history has one commit per phase.
7. Stretch goals (only if the human asks after Phase 8)
Alertmanager with a webhook receiver, SLSA provenance attestations, Cosign policy enforcement with a policy file, OpenTelemetry tracing with Jaeger (needs about 300 MB more), a k3d Kubernetes variant.
