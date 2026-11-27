# AI Exam Coach

Source-grounded examination preparation platform built in vertical milestones. See [PRODUCT.md](PRODUCT.md), [ARCHITECTURE.md](ARCHITECTURE.md), and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## Prerequisites

- Python 3.11+
- Node.js 22+ & npm 10+
- Docker Desktop (for local PostgreSQL 16; SQLite works as a zero-config local fallback)

## Local Setup

### 1. Environment Variables

Copy the example environment files (never commit `.env` or `.env.local`):

```powershell
Copy-Item .env.example .env
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.local.example frontend\.env.local
```

Add `GEMINI_API_KEY=...` to `backend\.env` when running AI stages (M3+ or vision OCR).

### 2. Database (PostgreSQL via Docker or SQLite Fallback)

To run PostgreSQL 16 locally:

```powershell
docker compose up -d postgres
```

If using the default `backend\.env.example`, it uses a local SQLite database at `storage/dev.db` until `DATABASE_URL` is pointed at PostgreSQL.

### 3. Backend (FastAPI)

```powershell
cd backend
python -m pip install -e ".[dev]"
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Verify health: `http://localhost:8000/health`

### 4. Frontend (Next.js)

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Running Checks & Tests

```powershell
# Backend
cd backend
python -m ruff check app tests
python -m pytest

# Frontend
cd frontend
npx tsc --noEmit
npm run lint
npm run build
```
