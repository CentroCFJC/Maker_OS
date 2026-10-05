.PHONY: setup run test lint docker-up docker-down user

# Local development setup
setup:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

# Run the dev server (http://localhost:8000)
run:
	.venv/bin/uvicorn makeros.main:app --host 0.0.0.0 --port 8000

# Run the test suite
test:
	.venv/bin/pytest

lint:
	.venv/bin/ruff check makeros tests

# Create a user: make user u=jacob r=admin
user:
	.venv/bin/python -m makeros.cli adduser $(u) --role $(r)

# Docker deployment (app + Caddy)
docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
