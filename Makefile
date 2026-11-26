.PHONY: install dev backend frontend seed test lint build check

install:
	cd backend && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
	cd frontend && npm install

seed:
	cd backend && python3 -m scripts.generate_seed

backend:
	cd backend && (. .venv/bin/activate 2>/dev/null || true) && uvicorn app.main:app --reload --port 8000

frontend:
	cd frontend && npm run dev

# runs both servers; Ctrl-C stops both
dev:
	@python3 scripts/dev.py --no-browser

test:
	cd backend && AI_LATENCY=0 python3 -m pytest
	cd frontend && npm run test --silent

build:
	cd frontend && npx tsc --noEmit && npm run build

check: test build
