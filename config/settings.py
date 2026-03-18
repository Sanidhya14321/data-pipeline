"""Application settings for the real-time ingestion pipeline."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Load and validate environment configuration for all pipeline services."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Kafka
    kafka_brokers: str = Field(..., alias="KAFKA_BROKERS")
    kafka_security_protocol: str = Field("SASL_SSL", alias="KAFKA_SECURITY_PROTOCOL")
    kafka_sasl_mechanism: str = Field("PLAIN", alias="KAFKA_SASL_MECHANISM")
    kafka_username: str = Field("", alias="KAFKA_USERNAME")
    kafka_password: str = Field("", alias="KAFKA_PASSWORD")
    kafka_topic_raw_events: str = Field("raw.events", alias="KAFKA_TOPIC_RAW_EVENTS")
    kafka_topic_normalized_events: str = Field(
        "normalized.events",
        alias="KAFKA_TOPIC_NORMALIZED_EVENTS",
    )
    kafka_topic_embedding_jobs: str = Field("embedding.jobs", alias="KAFKA_TOPIC_EMBEDDING_JOBS")
    kafka_topic_dlq: str = Field("dead.letter.queue", alias="KAFKA_TOPIC_DLQ")

    # PostgreSQL
    database_url: str = Field(..., alias="DATABASE_URL")
    postgres_pool_min_size: int = Field(5, alias="POSTGRES_POOL_MIN_SIZE")
    postgres_pool_max_size: int = Field(20, alias="POSTGRES_POOL_MAX_SIZE")

    # Qdrant
    qdrant_url: str = Field(..., alias="QDRANT_URL")
    qdrant_api_key: str = Field("", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field("pipeline_docs", alias="QDRANT_COLLECTION")

    # Redis
    redis_url: str = Field(..., alias="REDIS_URL")
    redis_db: int = Field(0, alias="REDIS_DB")

    # LLM APIs
    groq_api_key: str = Field(..., alias="GROQ_API_KEY")
    groq_classify_model: str = Field("llama-3.1-8b-instant", alias="GROQ_CLASSIFY_MODEL")
    groq_extract_model: str = Field(
        "llama-3.3-70b-versatile",
        alias="GROQ_EXTRACT_MODEL",
    )
    llm_request_timeout_seconds: int = Field(30, alias="LLM_REQUEST_TIMEOUT_SECONDS")

    # Data source APIs
    news_api_key: str = Field(..., alias="NEWS_API_KEY")
    github_token: str = Field(..., alias="GITHUB_TOKEN")
    sec_user_agent: str = Field(..., alias="SEC_USER_AGENT")
    github_api_base_url: str = Field("https://api.github.com", alias="GITHUB_API_BASE_URL")

    # Composio
    composio_api_key: str = Field(..., alias="COMPOSIO_API_KEY")
    composio_webhook_secret: str = Field(..., alias="COMPOSIO_WEBHOOK_SECRET")

    # App config
    pipeline_api_key: str = Field(..., alias="PIPELINE_API_KEY")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    environment: str = Field("development", alias="ENVIRONMENT")
    app_host: str = Field("0.0.0.0", alias="APP_HOST")
    app_port: int = Field(8080, alias="APP_PORT")
    metrics_port: int = Field(9090, alias="METRICS_PORT")

    @property
    def prometheus_port(self) -> int:
        """Return Prometheus exporter port.

        Returns
        -------
        int
            Port used by Prometheus HTTP exporter.
        """
        return self.metrics_port


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance.

    Returns
    -------
    Settings
        Cached application settings loaded from environment variables.
    """
    return Settings()
