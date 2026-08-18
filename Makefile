UV_CACHE_DIR ?= .cache/uv

.PHONY: bootstrap contract check dev-api dev-web e2e-install e2e

bootstrap:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) sync
	cd frontend && npm ci --ignore-scripts

contract:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run python scripts/export_openapi.py
	cd frontend && npm run generate:api

check: contract
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run ruff check .
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run pytest
	cd frontend && npm run check:boundaries
	cd frontend && npm run lint
	cd frontend && npm run typecheck
	cd frontend && npm run test
	cd frontend && npm run build
	git diff --exit-code -- backend/openapi.json frontend/src/api/generated

dev-api:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run alembic upgrade head
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run uvicorn qunxue_api.main:app --reload

dev-web:
	cd frontend && npm run dev

e2e-install:
	cd frontend && npx playwright install chromium

e2e:
	cd frontend && npx playwright test