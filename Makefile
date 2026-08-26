PYTHON := .venv/bin/python

# ── Setup ─────────────────────────────────────────────────────────────────────

.PHONY: venv
venv:
	uv venv --python 3.12 .venv

.PHONY: install
install:
	uv pip install --python .venv/bin/python -r requirements-dev.txt
	cd web && npm install

# ── Lint ──────────────────────────────────────────────────────────────────────

.PHONY: lint
lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .
	cd web && npx eslint src/ && npx prettier --check src/
	cd web && npx tsc -b

# ── Format (auto-fix) ─────────────────────────────────────────────────────────

.PHONY: format
format:
	.venv/bin/ruff check --fix .
	.venv/bin/ruff format .
	cd web && npx prettier --write src/

# ── Check (auto-fix, then typecheck, lint, and test) ──────────────────────────

.PHONY: check
check: format
	cd web && npx eslint --fix src/
	cd web && npx tsc -b
	$(PYTHON) -m pytest tests/
	cd web && npx vitest run

# ── Test ──────────────────────────────────────────────────────────────────────

.PHONY: test
test: test-py test-js

.PHONY: test-py
test-py:
	$(PYTHON) -m pytest tests/ -v

.PHONY: test-js
test-js:
	cd web && npx vitest run

# ── CI (lint + test) ──────────────────────────────────────────────────────────

.PHONY: ci
ci: lint test
