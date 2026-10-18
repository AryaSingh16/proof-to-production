.PHONY: test lint build up down clean ps logs mem smoke loadgen chaos-app chaos-db chaos-errors chaos-latency verify deploy-verified scan

test:
	docker run --rm -v $(PWD):/w -w /w python:3.12-slim sh -c 'pip install -q -r requirements-dev.txt && pytest -q'

lint:
	docker run --rm -v $(PWD):/w -w /w python:3.12-slim sh -c 'pip install -q -r requirements-dev.txt && ruff check .'

build:
	docker compose build

up:
	docker compose up -d --build --wait

down:
	docker compose down

clean:
	docker compose down -v

ps:
	docker compose ps

logs:
	docker compose logs -f --tail=100

mem:
	docker stats --no-stream --format '{{.Name}} {{.MemUsage}}'

smoke:
	./scripts/smoke.sh

loadgen:
	python3 scripts/loadgen.py

chaos-app:
	./scripts/chaos.sh app-kill

chaos-db:
	./scripts/chaos.sh db-kill

chaos-errors:
	./scripts/chaos.sh errors

chaos-latency:
	./scripts/chaos.sh latency

verify:
	./scripts/verify-image.sh $(IMAGE)

deploy-verified:
	./scripts/verify-image.sh $(IMAGE)
	APP_IMAGE=$(IMAGE) docker compose pull app
	APP_IMAGE=$(IMAGE) docker compose up -d --no-build --wait

scan:
	@echo "WARNING: Local scan is memory heavy. Ensure stack is stopped on low-memory machines (make down)."
	docker run --rm --memory 256m --user $$(id -u):$$(id -g) -v $(PWD):/repo -w /repo zricethezav/gitleaks:v8.21.2 detect --source . --redact
	docker run --rm --memory 768m -v /var/run/docker.sock:/var/run/docker.sock -v $(HOME)/.cache/trivy:/root/.cache aquasec/trivy:0.57.0 image --severity CRITICAL,HIGH --ignore-unfixed --exit-code 1 task-api:dev
