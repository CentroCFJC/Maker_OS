.PHONY: setup run serve serve-stop serve-status test lint docker-up docker-down user

# Local development setup
setup:
	python3 -m venv .venv
	.venv/bin/pip install -e ".[dev]"

# Run the dev server (http://localhost:8000)
run:
	.venv/bin/uvicorn makeros.main:app --host 0.0.0.0 --port 8000

# ---- Tailscale serve (lab deployment over HTTPS) ----
# Auto-detected tailnet URL (empty if tailscale is not running).
TS_URL := $(shell tailscale status --json 2>/dev/null | .venv/bin/python -c 'import sys,json; print("https://" + json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null)
# What uvicorn binds to behind `tailscale serve`: 127.0.0.1 = only
# reachable through the tailnet; 0.0.0.0 = also on the university LAN.
SERVE_BIND ?= 127.0.0.1
SERVE_PORT ?= 8000

# Serve MakerOS on https://<machine>.<tailnet>.ts.net (valid HTTPS,
# tailnet-only). Sets base URL and Secure cookies automatically.
serve:
	@if ! command -v tailscale >/dev/null 2>&1; then \
		echo "tailscale no está instalado: https://tailscale.com/download"; exit 1; fi
	@if [ -z "$(TS_URL)" ]; then \
		echo "tailscale no está conectado (prueba: tailscale up)"; exit 1; fi
	@if [ -f .makeros.pid ] && kill -0 $$(cat .makeros.pid) 2>/dev/null; then \
		echo "Ya hay un servidor (make serve-stop primero)."; exit 1; fi
	@echo "Iniciando MakerOS en $(TS_URL) ..."
	@MAKEROS_BASE_URL=$(TS_URL) MAKEROS_COOKIE_SECURE=1 \
		.venv/bin/uvicorn makeros.main:app --host $(SERVE_BIND) --port $(SERVE_PORT) \
		> .makeros.log 2>&1 & echo $$! > .makeros.pid
	@for i in $$(seq 1 40); do \
		curl -s -o /dev/null http://127.0.0.1:$(SERVE_PORT)/login && break; sleep 0.25; done
	@tailscale serve --bg $(SERVE_BIND):$(SERVE_PORT)
	@echo ""
	@echo "  MakerOS:  $(TS_URL)"
	@echo "  Log:      .makeros.log   (make serve-stop para parar)"

serve-stop:
	@tailscale serve reset >/dev/null 2>&1 \
		|| { echo "ADVERTENCIA: 'tailscale serve reset' falló (¿lo iniciaste con sudo?):"; \
		     tailscale serve reset 2>&1 | head -3; }
	@if [ -f .makeros.pid ]; then \
		pid=$$(cat .makeros.pid); \
		kill $$pid 2>/dev/null || true; \
		sleep 1; \
		if kill -0 $$pid 2>/dev/null; then \
			echo "ADVERTENCIA: el proceso $$pid sigue vivo (es de otro usuario: sudo kill $$pid)"; \
		else \
			rm -f .makeros.pid; \
		fi; \
	fi
	@echo "Revisa quedantes con: make serve-status"

# What is actually running: uvicorn processes, pid file, tailscale serve, ports.
serve-status:
	@echo "== uvicorn =="
	@ps aux | grep '[u]vicorn.*makeros' || echo "  nada"
	@echo "== .makeros.pid =="
	@if [ -f .makeros.pid ]; then \
		pid=$$(cat .makeros.pid); \
		kill -0 $$pid 2>/dev/null && echo "  $$pid (vivo)" || echo "  $$pid (muerto; borra el archivo)"; \
	else echo "  no existe"; fi
	@echo "== tailscale serve =="
	@tailscale serve status 2>&1 | head -5
	@echo "== puertos =="
	@ss -tln 2>/dev/null | grep -E ':(8000|8001)\b' || echo "  8000/8001 libres"

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
