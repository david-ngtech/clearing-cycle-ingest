ENGINE_PORT ?= 18771
WEB_PORT ?= 43131

.PHONY: install test engine web dev

install:
	cd engine && uv sync --extra dev
	cd web && npm install

test:
	cd engine && uv run pytest -q

engine:
	cd engine && uv run uvicorn clearing_ingest.api:app --host 127.0.0.1 --port $(ENGINE_PORT)

web:
	cd web && npm run dev -- --port $(WEB_PORT) --hostname 127.0.0.1

dev:
	@$(MAKE) -j2 engine web
