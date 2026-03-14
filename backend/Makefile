.PHONY: test test-integration-postgres test-load-postgres

test:
	. .venv/bin/activate && pytest

test-integration-postgres:
	@if [ ! -f .env.test.postgres ]; then \
		echo "Missing backend/.env.test.postgres"; \
		echo "Create it from backend/.env.test.postgres.example before running this target."; \
		exit 1; \
	fi
	. .venv/bin/activate && set -a && . ./.env.test.postgres && set +a && pytest -m "integration or postgres_required"

test-load-postgres:
	@if [ ! -f .env.test.postgres ]; then \
		echo "Missing backend/.env.test.postgres"; \
		echo "Create it from backend/.env.test.postgres.example before running this target."; \
		exit 1; \
	fi
	. .venv/bin/activate && set -a && . ./.env.test.postgres && set +a && pytest -m load
