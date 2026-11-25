# Run from demo/. `make help` lists the targets.
# Written for GNU Make 3.81 (macOS) and later: a recipe that needs several commands to
# succeed together is one shell line with `set -e`; every other recipe line fails on its own.

.DEFAULT_GOAL := help

# Values that differ per machine: .env, then these defaults (see .env.example).
-include .env
DB_PORT ?= 5440
API_PORT ?= 8100
WEB_PORT ?= 4400
OTP_PORT ?= 8080
E2E_WEB_PORT ?= 14400
INTEGRATION_DB_PORT ?= 5441
ADAPTERS ?= real
PLAYWRIGHT_ARGS ?= chromium

DB_URL = postgresql+psycopg://pricing_demo:pricing_demo@localhost:$(DB_PORT)/pricing_demo
INTEGRATION_DB_URL = postgresql+psycopg://pricing_demo:pricing_demo@localhost:$(INTEGRATION_DB_PORT)/pricing_demo
E2E = docker compose -f compose.e2e.yaml
E2E_LOG = e2e/test-results/stack.log

# A shell ended by Ctrl-C or a termination signal runs its EXIT trap only if the signal makes
# it exit (dash does not otherwise), so every recipe that cleans up in an EXIT trap starts
# with this.
ON_SIGNAL = trap 'exit 130' INT; trap 'exit 143' TERM

.PHONY: help install check test test-integration e2e contract format dev up down live-smoke

help: ## Show this list
	@awk 'BEGIN {FS = ":.*## "} /^[a-z-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install the API, the web app, the e2e suite and the Playwright browser (PLAYWRIGHT_ARGS= skips it)
	uv --directory api sync --locked
	npm --prefix web ci
	npm --prefix e2e ci
	@if [ -n "$(strip $(PLAYWRIGHT_ARGS))" ]; then \
		set -x; npm --prefix e2e exec -- playwright install $(PLAYWRIGHT_ARGS); \
	fi

check: ## The quality gate: formats, lint, types, layers, tests, contract freshness, web build
	uv --directory api run ruff format --check
	uv --directory api run ruff check
	uv --directory api run mypy
	uv --directory api run lint-imports
	uv --directory api run pytest
	@set -e; \
	$(ON_SIGNAL); \
	tmp=$$(mktemp -d); trap 'rm -rf "$$tmp"' EXIT; \
	uv --directory api run python -m pricing_demo.export_openapi "$$tmp/openapi.json"; \
	npm --prefix web exec -- openapi-typescript "$$tmp/openapi.json" -o "$$tmp/schema.d.ts" > /dev/null; \
	if ! cmp -s "$$tmp/openapi.json" contracts/openapi.json \
	  || ! cmp -s "$$tmp/schema.d.ts" web/src/infrastructure/api/generated/schema.d.ts; then \
		echo "The API contract is stale: contracts/openapi.json or the web API types differ from what the API generates. Run 'make contract'." >&2; \
		exit 1; \
	fi; \
	echo "Contract is fresh."
	npm --prefix web run check
	npm --prefix web run lint
	npm --prefix web run format:check
	npm --prefix web run test
	npm --prefix web run build
	npm --prefix e2e run typecheck
	npm --prefix e2e run lint
	npm --prefix e2e run format:check

test: ## Unit and contract tests of the API and the web app
	uv --directory api run pytest
	npm --prefix web run test

test-integration: ## API tests against a throwaway PostgreSQL in Docker (port INTEGRATION_DB_PORT)
	@set -e; \
	$(ON_SIGNAL); \
	name=pricing-demo-integration-$$$$; \
	docker run -d --name $$name \
		-e POSTGRES_USER=pricing_demo -e POSTGRES_PASSWORD=pricing_demo -e POSTGRES_DB=pricing_demo \
		-p 127.0.0.1:$(INTEGRATION_DB_PORT):5432 postgres:17 > /dev/null; \
	trap 'docker rm -f -v $$name > /dev/null' EXIT; \
	for attempt in $$(seq 1 60); do \
		docker exec $$name pg_isready -h 127.0.0.1 -U pricing_demo -d pricing_demo -q && break; \
		sleep 1; \
	done; \
	docker exec $$name pg_isready -h 127.0.0.1 -U pricing_demo -d pricing_demo; \
	PRICING_DEMO_TEST_DATABASE_URL=$(INTEGRATION_DB_URL) uv --directory api run pytest -m integration --no-cov

e2e: ## Build the e2e stack, run the Playwright scenarios, remove the stack (its logs stay in e2e/test-results/stack.log)
	@set -e; \
	$(ON_SIGNAL); \
	trap 'mkdir -p e2e/test-results; $(E2E) logs --no-color --timestamps > $(E2E_LOG) 2>&1 || true; $(E2E) down --volumes --remove-orphans' EXIT; \
	$(E2E) up --build --detach --wait --wait-timeout 300; \
	E2E_BASE_URL=http://localhost:$(E2E_WEB_PORT) npm --prefix e2e test

contract: ## Regenerate contracts/openapi.json and the web API types
	uv --directory api run python -m pricing_demo.export_openapi ../contracts/openapi.json
	npm --prefix web run generate:api

format: ## Rewrite files to the formatters' output (ruff format, prettier)
	uv --directory api run ruff format
	npm --prefix web run format
	npm --prefix e2e run format

# --ignore-lock: Astro detaches itself when an AI agent runs it, which would end this recipe.
dev: ## PostgreSQL in Docker; API and web dev server on the host; Ctrl-C stops those two, PostgreSQL runs until make down
	@set -e; \
	$(ON_SIGNAL); \
	docker compose up --detach --wait db; \
	export PRICING_DEMO_DATABASE_URL=$(DB_URL) PRICING_DEMO_ADAPTERS=$(ADAPTERS) \
		PRICING_DEMO_OTP_URL=http://localhost:$(OTP_PORT)/otp/gtfs/v1 \
		API_PROXY_TARGET=http://localhost:$(API_PORT); \
	uv --directory api run alembic upgrade head; \
	uv --directory api run uvicorn pricing_demo.asgi:app --reload --reload-dir src --port $(API_PORT) & \
	api=$$!; \
	trap 'kill $$api 2> /dev/null || true' EXIT; \
	npm --prefix web run dev -- --port $(WEB_PORT) --ignore-lock

up: ## The whole stack in Docker; OpenTripPlanner too when otp/data/graph.obj exists
	@set -e; \
	services="db api web"; \
	if [ -f otp/data/graph.obj ]; then \
		services="$$services otp"; \
	else \
		echo "Trip planner not started: otp/data/graph.obj does not exist (see otp/README.md)."; \
	fi; \
	docker compose up --build --detach --wait $$services

down: ## Stop the Docker stack; the database volume is kept
	docker compose --profile otp down --remove-orphans

live-smoke: ## Check the real package, solver and trip planner (Gurobi licence, running OpenTripPlanner)
	uv --directory api run pytest -m live --no-cov
