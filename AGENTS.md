# AGENTS.md

## Cursor Cloud specific instructions

APEX OS v2.0 is a single product split into two apps: `apex-backend` (FastAPI + Celery, Python 3.12 venv at `apex-backend/.venv`) and `apex-frontend` (Next.js 14, npm). It depends on **PostgreSQL** and **Redis**.

The update script installs Python + npm dependencies. PostgreSQL and Redis are installed at the system level (persisted in the VM snapshot), but they do **not** auto-start (no systemd in this environment) and must be started manually each session before running the backend/celery.

### Start datastores (run once per session, before the backend)
```
sudo pg_ctlcluster 16 main start            # PostgreSQL on :5432 (user apex / pass apex / db apexdb)
sudo redis-server --daemonize yes --bind 127.0.0.1 --port 6379   # Redis on :6379
```
The `apex` role and `apexdb` database persist in the snapshot; recreate only if missing:
```
sudo -u postgres psql -c "CREATE ROLE apex LOGIN PASSWORD 'apex';"
sudo -u postgres psql -c "CREATE DATABASE apexdb OWNER apex;"
```

### Env files
The backend reads `apex-backend/.env` (and repo-root `.env`); the frontend reads `apex-frontend/.env.local`. These are gitignored and persist in the snapshot. If missing, recreate from the template (defaults already point at the local Postgres/Redis):
```
cp .env.example .env && cp .env apex-backend/.env && cp .env apex-frontend/.env.local
```

### Run the services (from repo root)
- Backend: `cd apex-backend && PYTHONPATH=$PWD .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` — health at `http://localhost:8000/api/v1/health`, docs at `/docs`.
- Celery worker+beat: `cd apex-backend && PYTHONPATH=$PWD .venv/bin/celery -A app.workers.celery_app worker --beat --loglevel=info --pool=solo` (use `--pool=solo` locally).
- Frontend: `cd apex-frontend && npm run dev` — dashboard at `http://localhost:3000` (Arabic UI).
- Migrations: `cd apex-backend && PYTHONPATH=$PWD .venv/bin/alembic upgrade head` (already applied; rerun is a no-op).

### Tests / lint (backend)
- Tests: `cd apex-backend && PYTHONPATH=$PWD .venv/bin/python -m pytest -q`. ~12 tests fail on a clean checkout (e.g. `test_xauusd_readiness`, `test_integration`, `test_selectivity`) due to test-vs-config expectation mismatches that exist with or without `.env` — they are pre-existing and unrelated to environment setup. ~370 pass.

### Known caveats
- No external API keys are configured (TwelveData, Groq/OpenAI, Finnhub, AlphaVantage). The stack runs fine, but live candles/AI signals are skipped — the dashboard shows a "market closed"/no-data state and feed bootstrap logs `api_key_missing`. This is expected without keys; the API, DB, Redis, WebSocket and trading-journal/account features work fully.
- Frontend `npm run lint` (`next lint`) is **not** configured in this repo and launches an interactive ESLint setup prompt; it cannot run non-interactively without adding an ESLint config.
- The original setup automation (`setup.bat`, `start.bat`, `scripts/*.bat`) is Windows-only and not usable here; use the commands above instead.
- The Celery worker starts, connects to Redis, and runs tasks, but the beat-scheduled `evaluate_kill_switch` task throws `Future ... attached to a different loop` on repeat runs. This is a pre-existing code issue: each task builds a new event loop (`_run_async` in `app/workers/tasks.py`) while the module-level async engine pool (`pool_pre_ping=True`) stays bound to the first loop. It is unrelated to environment setup; the worker stays up and other tasks (e.g. `check_feed_staleness`) succeed.
