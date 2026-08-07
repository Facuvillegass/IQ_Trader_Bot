# MNQ paper trading — single Railway service
# Worker thread + FastAPI + static React dashboard
# Persistent volume must be mounted at /data

FROM node:22-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    TRADING_MODE=PAPER \
    DATABASE_PATH=/data/trading.db \
    LOG_DIR=/data/logs \
    REPORTS_DIR=/data/reports \
    TZ_DISPLAY=America/Argentina/Cordoba \
    API_HOST=0.0.0.0 \
    EMBED_WORKER=true

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libffi-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-databento.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-databento.txt || true

COPY backend ./backend
COPY start.sh stop.sh ./
COPY --from=frontend /frontend/dist ./frontend/dist

RUN mkdir -p /data /app/logs /app/reports \
    && chmod +x start.sh stop.sh

EXPOSE 8010

# Railway sets $PORT. Worker runs inside the API process (HTTP-independent thread).
CMD ["sh", "-c", "mkdir -p /data/logs /data/reports && python -m backend.app.main"]
