.PHONY: backend frontend migrate test lint build acceptance acceptance-real

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

migrate:
	cd backend && .venv/bin/alembic upgrade head

test:
	backend/.venv/bin/pytest backend/tests -q
	cd frontend && npm test

lint:
	backend/.venv/bin/ruff check backend
	backend/.venv/bin/ruff format --check backend
	cd frontend && npm run lint && npm run typecheck

build:
	cd frontend && npm run build

acceptance:
	backend/.venv/bin/python -m app.acceptance.p6_runner

acceptance-real:
	backend/.venv/bin/python -m app.acceptance.p6_runner --execute-real-model
