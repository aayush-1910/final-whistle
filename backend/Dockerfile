# Final Whistle API: read-only FastAPI service.
# Works on any container host (Render, Railway, Fly.io, ...).  Configuration and
# secrets come from the host's environment settings, never from files in the image.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_ENV=production \
    LOG_FORMAT=json

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY rules ./rules
COPY migrations ./migrations
COPY scripts ./scripts

# Run as an unprivileged user.
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000
# Hosts set $PORT; default 8000 for local `docker run -p 8000:8000`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
