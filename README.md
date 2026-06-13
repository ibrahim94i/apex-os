# APEX OS v2.0 — Railway Deployment Guide

Deploy APEX OS on [Railway.app](https://railway.app) with five services:

| Service | Root Directory | Config File | Dockerfile |
|---------|----------------|-------------|------------|
| **Backend** (FastAPI) | `apex-backend` | `railway.json` | `Dockerfile` |
| **Frontend** (Next.js) | `apex-frontend` | `railway.json` | `Dockerfile` |
| **Celery Worker** | `apex-backend` | `railway.celery.json` | `Dockerfile.celery` |
| **PostgreSQL** | — (Railway plugin) | `deploy/postgresql/railway.json` | — |
| **Redis** | — (Railway plugin) | `deploy/redis/railway.json` | — |

---

## Prerequisites

1. GitHub account with APEX OS pushed to a repository
2. [Railway account](https://railway.app)
3. API keys: **TwelveData**, **OpenAI** (optional: Groq, Telegram)

---

## Step 1 — Create Railway Project

1. Go to [railway.app/new](https://railway.app/new)
2. Choose **Deploy from GitHub repo**
3. Select your APEX OS repository
4. Railway creates an empty project

---

## Step 2 — Add PostgreSQL

1. In the project canvas, click **+ New**
2. Select **Database → PostgreSQL**
3. Wait until status is **Active**
4. Open the PostgreSQL service → **Variables** tab
5. Copy `DATABASE_URL` (Railway generates it automatically)

> Reference config: `deploy/postgresql/railway.json`

---

## Step 3 — Add Redis

1. Click **+ New → Database → Redis**
2. Wait until **Active**
3. Copy `REDIS_URL` from the Redis service variables

> Reference config: `deploy/redis/railway.json`

---

## Step 4 — Deploy Backend (FastAPI)

1. Click **+ New → GitHub Repo** (same repo) or **Empty Service**
2. Rename service to `apex-backend`
3. **Settings → Source → Root Directory** → set to `apex-backend`
4. **Settings → Config-as-code → Railway config file** → `railway.json`
5. **Settings → Networking → Generate Domain** → copy URL (e.g. `https://apex-backend-production.up.railway.app`)

### Backend Variables

In the backend service **Variables** tab, add (use `.env.production` as reference):

```env
ENVIRONMENT=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
REDIS_URL=${{Redis.REDIS_URL}}
CELERY_BROKER_URL=${{Redis.REDIS_URL}}
CELERY_RESULT_BACKEND=${{Redis.REDIS_URL}}
FRONTEND_URL=https://YOUR-FRONTEND.up.railway.app
CORS_ORIGINS=https://YOUR-FRONTEND.up.railway.app
TWELVEDATA_API_KEY=your_key
OPENAI_API_KEY=your_key
OPENAI_MODEL=gpt-4o-mini
LLM_PRIMARY_PROVIDER=openai
TELEGRAM_BOT_TOKEN=optional
TELEGRAM_CHAT_ID=optional
```

> Use Railway **variable references** (`${{Postgres.DATABASE_URL}}`) to link plugins — replace service names if yours differ.

6. Click **Deploy** — backend runs migrations automatically via `docker-entrypoint.sh`
7. Verify: open `https://YOUR-BACKEND.up.railway.app/api/v1/health`

---

## Step 5 — Deploy Celery Worker

1. **+ New → GitHub Repo** (same repo)
2. Rename to `apex-celery`
3. **Root Directory** → `apex-backend`
4. **Config-as-code file** → `railway.celery.json`
5. Add the **same variables** as backend (DATABASE_URL, REDIS_URL, API keys, etc.)
6. Deploy — Celery runs `worker + beat` for scheduled tasks

---

## Step 6 — Deploy Frontend (Next.js)

1. **+ New → GitHub Repo** (same repo)
2. Rename to `apex-frontend`
3. **Root Directory** → `apex-frontend`
4. **Config-as-code file** → `railway.json`
5. **Generate Domain** → copy frontend URL

### Frontend Variables (required at build time)

```env
NEXT_PUBLIC_API_URL=https://YOUR-BACKEND.up.railway.app
NEXT_PUBLIC_WS_URL=wss://YOUR-BACKEND.up.railway.app
```

> **Important:** `NEXT_PUBLIC_*` variables are baked into the Next.js build. After changing them, **redeploy** the frontend.

6. Deploy and open `https://YOUR-FRONTEND.up.railway.app`

---

## Step 7 — Update CORS and Redeploy Backend

After you have the real frontend URL:

1. Backend service → Variables:
   ```env
   FRONTEND_URL=https://YOUR-FRONTEND.up.railway.app
   CORS_ORIGINS=https://YOUR-FRONTEND.up.railway.app
   ```
2. Redeploy backend

---

## Step 8 — Verify Full Stack

| Check | URL / Action |
|-------|----------------|
| Backend health | `GET /api/v1/health` → `"status": "ok"` |
| API docs | `/docs` |
| Dashboard | Frontend home page loads |
| WebSocket | Dashboard shows **مباشر** (green dot) |
| Feeds | Feed status panel shows connected assets |
| Celery | Worker logs show `celery@` ready |

---

## Architecture on Railway

```
┌─────────────────┐     HTTPS/WSS      ┌─────────────────┐
│  apex-frontend  │ ─────────────────► │  apex-backend   │
│  (Next.js)      │                    │  (FastAPI)      │
└─────────────────┘                    └────────┬────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
            ┌──────────────┐          ┌──────────────┐          ┌──────────────┐
            │  PostgreSQL  │          │    Redis     │          │ apex-celery  │
            │  (plugin)    │          │   (plugin)   │          │  (worker)    │
            └──────────────┘          └──────────────┘          └──────────────┘
```

---

## Environment Variables Reference

Full template: [`.env.production`](.env.production)

| Variable | Service | Description |
|----------|---------|-------------|
| `DATABASE_URL` | Backend, Celery | Auto from PostgreSQL plugin |
| `REDIS_URL` | Backend, Celery | Auto from Redis plugin |
| `FRONTEND_URL` | Backend | Frontend public URL for CORS |
| `CORS_ORIGINS` | Backend | Comma-separated extra origins |
| `NEXT_PUBLIC_API_URL` | Frontend | Backend HTTPS URL |
| `NEXT_PUBLIC_WS_URL` | Frontend | Backend WSS URL |
| `TWELVEDATA_API_KEY` | Backend, Celery | Gold/EURUSD data |
| `OPENAI_API_KEY` | Backend, Celery | AI agents (primary) |
| `OPENAI_MODEL` | Backend, Celery | Default: `gpt-4o-mini` |
| `LLM_PRIMARY_PROVIDER` | Backend, Celery | Default: `openai` |
| `GROQ_API_KEY` | Backend | Optional Groq fallback |
| `TELEGRAM_*` | Backend | Optional alerts |

---

## Troubleshooting

### Frontend shows "Failed to fetch"
- Confirm `NEXT_PUBLIC_API_URL` points to backend **HTTPS** domain (not `localhost`)
- Redeploy frontend after changing `NEXT_PUBLIC_*`

### WebSocket not connecting
- Set `NEXT_PUBLIC_WS_URL=wss://YOUR-BACKEND.up.railway.app`
- Or omit it — frontend auto-derives from API URL

### Database connection errors
- Backend auto-converts `postgresql://` → `postgresql+asyncpg://`
- Check `${{Postgres.DATABASE_URL}}` reference is linked

### Celery not running tasks
- Celery service must share same `REDIS_URL` and `DATABASE_URL` as backend
- Check Celery logs for `Connected to redis://`

### Build fails on frontend
- Ensure `NEXT_PUBLIC_API_URL` is set **before** build starts
- Check Railway build logs for missing env vars

---

## Local vs Production

| | Local (`start.bat`) | Railway |
|--|---------------------|---------|
| Backend | `localhost:8000` | `https://*.up.railway.app` |
| Frontend | `localhost:3000` | `https://*.up.railway.app` |
| PostgreSQL | Windows service | Railway plugin |
| Redis | Windows/Memurai | Railway plugin |

---

## Files Created for Railway

```
apex-backend/
  Dockerfile              # Production FastAPI (multi-stage)
  Dockerfile.celery       # Celery worker + beat
  docker-entrypoint.sh    # Migrations + uvicorn
  railway.json            # Backend deploy config
  railway.celery.json     # Celery deploy config
  requirements-prod.txt   # Production Python deps

apex-frontend/
  Dockerfile              # Next.js standalone (multi-stage)
  railway.json            # Frontend deploy config
  .dockerignore

deploy/
  postgresql/railway.json # PostgreSQL plugin reference
  redis/railway.json      # Redis plugin reference

.env.production           # All production variables template
```

---

## Quick Deploy Checklist

- [ ] PostgreSQL plugin added
- [ ] Redis plugin added
- [ ] Backend deployed (`apex-backend` root)
- [ ] Backend domain generated
- [ ] Celery deployed (`railway.celery.json`)
- [ ] Frontend deployed with `NEXT_PUBLIC_API_URL` + `NEXT_PUBLIC_WS_URL`
- [ ] Frontend domain generated
- [ ] `FRONTEND_URL` + `CORS_ORIGINS` updated on backend
- [ ] Health check passes
- [ ] Dashboard loads with live WebSocket
