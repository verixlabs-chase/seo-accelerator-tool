#!/usr/bin/env bash
set -euo pipefail

DATABASE_URL_DEFAULT='postgresql+psycopg://lsos:lsos@postgres:5432/lsos'
export DATABASE_URL="${DATABASE_URL:-$DATABASE_URL_DEFAULT}"

alembic upgrade head
pytest -q
