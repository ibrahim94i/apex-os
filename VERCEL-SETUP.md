# APEX OS — Frontend على Vercel

Backend يبقى على **Railway** (`apex-os`). Frontend يُرفع على **Vercel**.

## 1) ربط المستودع

1. [vercel.com/new](https://vercel.com/new) → Import Git Repository
2. اختر **`ibrahim94i/apex-os`**
3. **Root Directory** → `apex-frontend` ← **مهم**
4. Framework: **Next.js** (يكتشف تلقائياً من `vercel.json`)

## 2) Environment Variables

| Variable | القيمة |
|----------|--------|
| `NEXT_PUBLIC_API_URL` | `https://apex-os-production-9adc.up.railway.app` |
| `NEXT_PUBLIC_WS_URL` | `wss://apex-os-production-9adc.up.railway.app` |

> غيّر الرابط إذا تغيّر domain الـ Backend على Railway.

## 3) Deploy

اضغط **Deploy** — Vercel يبني `npm ci` + `npm run build` تلقائياً.

## 4) تحديث Backend CORS

بعد حصولك على رابط Vercel (مثل `https://apex-os.vercel.app`):

في Railway → service **apex-os** → Variables:

```env
FRONTEND_URL=https://YOUR-APP.vercel.app
CORS_ORIGINS=https://YOUR-APP.vercel.app
```

ثم **Redeploy** للـ Backend.

## 5) التحقق

- افتح رابط Vercel → الداشبورد يظهر
- نقطة الاتصال **مباشر** (WebSocket)
- لا أخطاء CORS في Console

## الملفات

```
apex-frontend/
  vercel.json       ← إعدادات Vercel
  next.config.js    ← بدون standalone على Vercel
  package.json
  src/
```

## ملاحظات

- **لا تستخدم** Railway لـ Frontend — استخدم Vercel فقط
- `NEXT_PUBLIC_*` تُدمج وقت البناء — أعد Deploy على Vercel بعد تغييرها
- WebSocket يتصل مباشرة من المتصفح إلى Backend على Railway
