FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Create non-root user and private storage directory
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser \
    && mkdir -p /var/data/storage && chown -R appuser:appgroup /var/data/storage

COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app

RUN chown -R appuser:appgroup /app
USER appuser

ENV STORAGE_ROOT=/var/data/storage \
    APP_ENV=production \
    AUTH_MODE=jwt \
    PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
