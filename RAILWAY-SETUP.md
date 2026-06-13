# إعداد Railway — APEX OS (monorepo)

المستودع على GitHub: `ibrahim94i/apex-os`

```
apex-os/                 ← جذر GitHub
├── Dockerfile           ← للـ Backend (يبني من apex-backend/)
├── railway.json         ← إعداد Backend من الجذر
├── apex-backend/        ← كود FastAPI
├── apex-frontend/       ← كود Next.js
└── deploy/
```

---

## ✅ الطريقة 1 — Backend من جذر المستودع (موصى بها)

| الإعداد | القيمة |
|---------|--------|
| **Root Directory** | `/` (فارغ — لا تكتب apex-backend) |
| **Config-as-code** | `railway.json` |
| **Dockerfile** | `Dockerfile` (في الجذر) |

> لا تضع `apex-backend` في Root Directory — الـ Dockerfile في الجذر ينسخ `apex-backend/` تلقائياً.

---

## ✅ الطريقة 2 — Backend من مجلد فرعي

| الإعداد | القيمة |
|---------|--------|
| **Root Directory** | `apex-backend` |
| **Config-as-code** | `railway.json` ← **ليس** `apex-backend/railway.json` |
| **Dockerfile** | `Dockerfile` |

> ⚠️ خطأ شائع: Root Directory = `apex-backend` **و** Config file = `apex-backend/railway.json`  
> Railway يبحث عن `apex-backend/apex-backend/` → **no such file or directory**

---

## Frontend (خدمة `friendly-imagination`)

### الطريقة A — من جذر المستودع (موصى بها إذا Root Directory فارغ)

| الإعداد | القيمة |
|---------|--------|
| **Root Directory** | `/` (فارغ) |
| **Config-as-code** | `railway.frontend.json` |
| **Dockerfile** | `Dockerfile.frontend` |

### الطريقة B — من مجلد فرعي

| الإعداد | القيمة |
|---------|--------|
| **Root Directory** | `apex-frontend` |
| **Config-as-code** | `railway.json` |

> ⚠️ **خطأ شائع:** Root Directory فارغ + `railway.json` (Backend) → Frontend يبني Python backend ويفشل Healthcheck!

**Variables (build time):**
```env
NEXT_PUBLIC_API_URL=https://apex-os-production-9adc.up.railway.app
NEXT_PUBLIC_WS_URL=wss://apex-os-production-9adc.up.railway.app
```

---

## PostgreSQL + Redis

- **PostgreSQL:** + New → Database → PostgreSQL
- **Redis:** على الخطة المجانية قد لا يتوفر — Backend يستخدم Redis مدمج داخل الحاوية

**Variables للـ Backend:**
```env
DATABASE_URL=${{Postgres.DATABASE_URL}}
ENVIRONMENT=production
TWELVEDATA_API_KEY=...
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-4o-mini
LLM_PRIMARY_PROVIDER=openai
```

---

## تحقق سريع

```bash
# من جهازك — رفع Backend
cd apex-os
railway link -p adaptable-prosperity -s apex-os
railway up -s apex-os -d
```
