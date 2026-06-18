# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Faster, quieter Python in containers.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install deps first so this layer is cached unless requirements change.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Then copy the application code.
COPY . .

EXPOSE 8000

# Run as a non-root user for safety.
RUN useradd --create-home appuser \
    && chmod +x /app/docker-entrypoint.sh \
    && chown -R appuser:appuser /app
USER appuser

# Entrypoint runs migrations then launches a SINGLE uvicorn process (the
# in-process APScheduler cron must not be multiplied across workers).
ENTRYPOINT ["/app/docker-entrypoint.sh"]
