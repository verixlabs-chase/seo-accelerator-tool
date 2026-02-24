build:
	docker compose build

up:
	docker compose up

test:
	docker compose run --rm test-runner

lint:
	docker compose run --rm api ruff check backend

validate:
	docker compose run --rm api python backend/scripts/validate_production_config.py
