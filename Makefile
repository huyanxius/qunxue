UV_CACHE_DIR ?= .cache/uv

.PHONY: bootstrap bootstrap-backend bootstrap-frontend contract check check-backend check-contract check-frontend dev-api dev-web

bootstrap: bootstrap-backend bootstrap-frontend

bootstrap-backend:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) sync

bootstrap-frontend:
	cd frontend && npm ci --ignore-scripts

contract:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run python scripts/export_openapi.py
	cd frontend && npm run generate:api

check: check-contract check-backend check-frontend

check-backend:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run ruff check .
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run pytest

check-contract: contract
	git diff --exit-code -- backend/openapi.json frontend/src/api/generated

check-frontend:
	cd frontend && npm run check:boundaries
	cd frontend && npm run lint
	cd frontend && npm run test
	cd frontend && npm run build

dev-api:
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run alembic upgrade head
	cd backend && uv --cache-dir $(UV_CACHE_DIR) run uvicorn qunxue_api.main:app --reload

dev-web:
	cd frontend && npm run dev
