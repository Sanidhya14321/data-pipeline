"""FastAPI application entrypoint for the pipeline API."""

from __future__ import annotations

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import Counter, Histogram, make_asgi_app

from api.routes import health, search, stats
from config.settings import get_settings
from workers.db import init_schema

log = structlog.get_logger(__name__)
settings = get_settings()

pipeline_http_requests_total = Counter(
    "pipeline_http_requests_total",
    "Total HTTP requests served by the API.",
    ["method", "path", "status"],
)

pipeline_http_duration_seconds = Histogram(
    "pipeline_http_duration_seconds",
    "HTTP request duration in seconds.",
    ["method", "path"],
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize worker schema at API startup."""
    try:
        await init_schema()
    except Exception as exc:
        # Keep API online in degraded mode when backing services are unavailable.
        log.warning("api.startup_schema_init_failed", error=str(exc))
    yield


app = FastAPI(title="Data Pipeline API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def prometheus_http_middleware(request: Request, call_next):
    """Record HTTP request count and duration metrics."""
    start = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        path = request.url.path
        method = request.method
        elapsed = time.perf_counter() - start

        pipeline_http_requests_total.labels(
            method=method,
            path=path,
            status=str(status_code),
        ).inc()
        pipeline_http_duration_seconds.labels(method=method, path=path).observe(elapsed)


app.include_router(health.router, prefix="/api/v1")
app.include_router(search.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.mount("/metrics", make_asgi_app())


@app.get("/")
async def root() -> dict[str, str]:
    """Simple root endpoint for platform health probing."""
    return {"status": "ok", "service": "data-pipeline-api"}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return a generic 500 payload for unexpected exceptions."""
    log.error("api.unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})
