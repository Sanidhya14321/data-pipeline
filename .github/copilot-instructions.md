# Copilot Instructions for Real-Time Web Data Ingestion Pipeline

## Project Context
This repository implements a production-grade real-time web data ingestion pipeline.

### High-Level Overview
- Ingests live data from 20+ sources including RSS, NewsAPI, SEC EDGAR, GitHub, and scraping workloads.
- Streams events through Apache Kafka across five topics.
- Normalizes content with Groq-hosted LLMs for classification, extraction, summarization, and quality gating.
- Stores metadata in PostgreSQL and vectors in Qdrant.
- Exposes a FastAPI search API and a React monitoring dashboard.
- Runs in Docker Compose for local development and Kubernetes for production.

### Tech Stack
- Backend: Python 3.11
- Frontend: TypeScript + React 18
- Streaming: Apache Kafka 3.7 via confluent-kafka and Faust
- Storage: PostgreSQL 16 (asyncpg + SQLAlchemy async), Qdrant 1.9, Redis 7
- AI: Groq API
  - classify/quality: llama-3.1-8b-instant
  - extract/summarize: llama-3.3-70b-versatile
- Embeddings: sentence-transformers all-MiniLM-L6-v2 (384 dimensions)
- API: FastAPI + uvicorn
- Infra: Docker Compose, Kubernetes, GitHub Actions CI/CD

## Coding Conventions
- Add type hints on every function signature.
- Use async/await for all I/O operations.
- Use structlog for logging.
- Use Pydantic models in API layers and dataclasses in worker layers.
- Use parameterized SQL only.
- Read all secrets from os.getenv or settings models.
- Use NumPy-style docstrings on public functions.
- Use Ruff formatting and linting with 100 character line length.
- For Kafka consumers, commit offsets only after successful processing.

## Anti-Patterns to Avoid
- Do not use requests.get; use aiohttp or httpx.
- Do not use time.sleep in async paths; use asyncio.sleep.
- Do not use bare except clauses.
- Do not hardcode credentials, tokens, or API keys.
- Do not commit Kafka offsets before processing and persistence succeed.
- Do not use non-zero temperature for structured LLM extraction.

## Repository Structure
- connectors/: Source-specific ingestion clients and parsing logic.
- workers/: Streaming workers, normalization, vectorization, dedup, resilience, and prompt logic.
- api/: FastAPI app entrypoint and route handlers.
- scripts/: Orchestration utilities such as connector scheduling runners.
- config/: Settings and source configuration YAML.
- tests/unit/: Isolated unit tests with mocks and fixtures.
- tests/integration/: End-to-end tests across Kafka, Postgres, Qdrant, and API.
- tests/load/: Load and performance scripts.
- docker/: Worker image, Prometheus config, alert rules, and Grafana provisioning.
- k8s/base/: Base Kubernetes manifests for deployments, services, HPAs, and cron jobs.
- frontend/: Monitoring/search dashboard UI.

## Component-Specific Guidance

### When editing connectors/
- Keep fetch paths fully async and resilient.
- Validate and normalize timestamps to UTC.
- Skip malformed records safely and log context with source identifiers.
- Preserve source metadata for downstream auditing.

### When editing workers/
- Follow explicit pipeline step ordering where defined.
- Use retry_with_backoff and circuit breakers for external dependencies.
- Route failed processing to DLQ with reason codes and error context.
- Keep event body and summary lengths bounded for storage/index consistency.
- Commit Kafka offsets only after downstream writes/upserts succeed.

### When editing api/
- Enforce API key authentication where required.
- Keep request/response schemas explicit and typed.
- Return stable, user-safe error payloads.
- Maintain Prometheus instrumentation for request count and latency.

### When editing tests/
- Prefer deterministic tests with mocks over real network calls in unit tests.
- Keep integration tests behind integration markers.
- Ensure fixture data mirrors realistic production payloads.
- Validate both success and failure behavior paths.

## Expected Output Quality
- Favor precise, production-safe changes over broad refactors.
- Preserve existing APIs unless requirements explicitly change.
- Add concise comments only where logic is non-obvious.
- Keep security and reliability controls as first-class constraints.
