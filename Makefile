.PHONY: test lint build up down clean ps logs mem

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
