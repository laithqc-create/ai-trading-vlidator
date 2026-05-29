.PHONY: dev test build-ext deploy migrate logs clean

# ── Local development ─────────────────────────────────────────────────────────
dev:
	uvicorn main:app --reload --host 0.0.0.0 --port 8000

# ── Run tests ─────────────────────────────────────────────────────────────────
test:
	pytest tests/ -v

# ── Build extension zip ───────────────────────────────────────────────────────
build-ext:
	python scripts/build_extension.py

# ── Full production deploy ────────────────────────────────────────────────────
deploy: build-ext
	docker compose build --pull
	docker compose up -d --remove-orphans
	@echo "✓ Deployed. API at http://localhost:8000/health"

# ── Run DB migrations only ────────────────────────────────────────────────────
migrate:
	docker compose run --rm migrate

# ── Tail all logs ────────────────────────────────────────────────────────────
logs:
	docker compose logs -f api worker

# ── Stop everything ──────────────────────────────────────────────────────────
down:
	docker compose down

# ── Clean build artefacts ─────────────────────────────────────────────────────
clean:
	rm -rf dist/ miniapp/static/extension.zip __pycache__ .pytest_cache
	find . -name "*.pyc" -delete
