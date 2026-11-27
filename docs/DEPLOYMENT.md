# Cloud Deployment Guide — AI Exam Coach

AI Exam Coach is a full-stack application (Next.js frontend + FastAPI backend + PostgreSQL + private document storage + server-side `GEMINI_API_KEY`). Because `GEMINI_API_KEY`, private PDFs, and PostgreSQL cannot run safely on static hosting like GitHub Pages, deploy the backend and frontend separately as described below.

---

## 1. Backend + PostgreSQL on Render (Recommended Blueprint)

1. Push this repository to GitHub (never commit `.env` or `backend/.env`).
2. In the Render Dashboard, choose **New → Blueprint** and select your repository. Render reads [render.yaml](../render.yaml), creating:
   - `ai-exam-coach-db` (PostgreSQL)
   - `ai-exam-coach-api` (Docker web service using [backend/Dockerfile](../backend/Dockerfile) with persistent disk mounted at `/var/data/storage`)
3. Set the two `sync: false` environment variables in Render:
   - `GEMINI_API_KEY`: your Google Gemini API key
   - `CORS_ORIGINS`: your Vercel frontend URL (e.g., `https://ai-exam-coach.vercel.app`)
4. Notice `APP_ENV=production`, `AUTH_MODE=jwt`, `JWT_SECRET_KEY` (auto-generated), and automatic rate limiting are enabled by default. On startup, the container runs `alembic upgrade head` and verifies `/health`.

### Alternative Backend Host: Railway

1. Create a Railway project from your GitHub repo with **Root Directory** set to `backend` (reads [backend/railway.toml](../backend/railway.toml) and [backend/Dockerfile](../backend/Dockerfile)).
2. Add a Railway PostgreSQL plugin and attach a persistent volume mounted at `/var/data/storage`.
3. Set environment variables:
   - `APP_ENV=production`
   - `AUTH_MODE=jwt`
   - `STORAGE_ROOT=/var/data/storage`
   - `DATABASE_URL` (use Railway's `postgresql+psycopg://...` connection string — see note below)
   - `JWT_SECRET_KEY` (32+ random characters)
   - `GEMINI_API_KEY`
   - `CORS_ORIGINS=https://<your-vercel-app>.vercel.app`

> **SQLAlchemy Driver Note:** If your host provides a `postgres://` or `postgresql://` URL, convert the scheme to `postgresql+psycopg://` (or update `DATABASE_URL` accordingly) so SQLAlchemy uses `psycopg` v3.

---

## 2. Frontend on Vercel

1. In Vercel, import the same GitHub repository.
2. Set **Root Directory** to `frontend`.
3. Add Environment Variable:
   - `NEXT_PUBLIC_API_BASE_URL=https://<your-render-or-railway-backend-domain>`
4. Deploy. Copy your live Vercel domain (e.g., `https://ai-exam-coach.vercel.app`) back into the backend's `CORS_ORIGINS` setting.

---

## 3. Production Authentication & Security

- When `APP_ENV=production` (or `AUTH_MODE=jwt`), `X-User-Id` header overrides are disabled (`403 Forbidden`), and all user endpoints require a valid `Authorization: Bearer <jwt>` token from `POST /api/v1/auth/register` or `POST /api/v1/auth/login`.
- Open `https://<your-vercel-domain>/register` to create your student account after deploying.
- Auth (`/auth/login`, `/auth/register`) and AI generation routes are automatically rate-limited in production.
