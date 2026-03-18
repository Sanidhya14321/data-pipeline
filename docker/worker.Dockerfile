FROM python:3.11.9-slim AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

RUN set -e; \
        success=0; \
        for attempt in 1 2 3; do \
            if pip install --user --no-cache-dir --default-timeout=120 \
                aiohttp \
                groq \
                asyncpg \
                bleach \
                confluent-kafka \
                faust-streaming \
                fastapi \
                feedparser \
                prometheus-client \
                pydantic \
                pydantic-settings \
                pyyaml \
                qdrant-client \
                redis \
                sentence-transformers \
                sqlalchemy[asyncio] \
                structlog \
                uvicorn; then \
                success=1; \
                break; \
            fi; \
            echo "pip install attempt ${attempt} failed; retrying..."; \
            sleep 5; \
        done; \
        [ "$success" -eq 1 ]

# Pre-download embedding model during build to avoid runtime fetches.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

FROM python:3.11.9-slim AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system --gid 1001 appgroup \
    && adduser --system --uid 1001 --ingroup appgroup appuser

COPY --from=builder /root/.local /home/appuser/.local
COPY --from=builder /root/.cache /home/appuser/.cache
COPY --chown=appuser:appgroup . /app

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV SENTENCE_TRANSFORMERS_HOME=/home/appuser/.cache

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8080/api/v1/ready >/dev/null || exit 1
