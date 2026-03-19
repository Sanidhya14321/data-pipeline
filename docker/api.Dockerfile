FROM python:3.11.9-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY data-pipeline/requirements-api.txt /app/requirements-api.txt
RUN pip install --no-cache-dir --prefer-binary -r /app/requirements-api.txt

RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --ingroup appgroup appuser

COPY --chown=appuser:appgroup data-pipeline/api /app/api
COPY --chown=appuser:appgroup data-pipeline/config /app/config
RUN mkdir -p /app/workers
COPY --chown=appuser:appgroup data-pipeline/workers/db.py /app/workers/db.py

USER appuser

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8080/api/v1/ready >/dev/null || exit 1

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
