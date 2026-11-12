from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or local .env."""

    PROJECT_NAME: str = "Refund Intelligence Platform API"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    AGENT_API_PORT: int = 8100

    # PostgreSQL 16 (host port 5433 locally, postgres:5432 inside Docker)
    DATABASE_URL: str = "postgresql+psycopg://localhost:5433/refund_intelligence"

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str):
            raw = value.strip()
            if raw.startswith("postgres://"):
                return "postgresql+psycopg://" + raw[len("postgres://") :]
            if raw.startswith("postgresql://"):
                return "postgresql+psycopg://" + raw[len("postgresql://") :]
        return value

    # Redis 7 & Celery
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/1"
    CELERY_TASK_ALWAYS_EAGER: bool = False

    # Agent MinIO Object Storage (host ports 9002/9003, minio:9000 inside Docker)
    MINIO_ENDPOINT: str = "localhost:9002"
    MINIO_PUBLIC_URL: str = "http://localhost:9002"
    MINIO_ACCESS_KEY: str = ""
    MINIO_SECRET_KEY: str = ""
    MINIO_SECURE: bool = False
    BUCKET_EVIDENCE: str = "refund-evidence"
    BUCKET_REPORTS: str = "refund-reports"
    MAX_EVIDENCE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # Shipkart Bridge & Auth Secrets (never hardcoded; set via env)
    SHIPKART_API_URL: str = "http://localhost:8000"
    BRIDGE_SHARED_SECRET: str = ""
    SERVICE_JWT_SECRET: str = ""
    JWT_SECRET_KEY: str = ""
    JWT_ALGORITHM: str = "HS256"
    SERVICE_JWT_ISSUER: str = "refund-intelligence-platform"
    SERVICE_JWT_EXPIRE_SECONDS: int = 300
    PLATFORM_ADMIN_EMAIL: str = ""
    PLATFORM_ADMIN_PASSWORD: str = ""
    PLATFORM_JWT_EXPIRE_MINUTES: int = 720

    # NVIDIA NIM LLM Endpoints (free-tier compatible via build.nvidia.com)
    NVIDIA_API_KEY: str = ""
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"
    NVIDIA_REASONING_MODEL: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"
    NVIDIA_VISION_MODEL: str = "nvidia/nemotron-3.5-super-vl-120b-a12b"
    NVIDIA_TIMEOUT_SECONDS: float = 30.0
    NVIDIA_MAX_RETRIES: int = 2

    # PayPal Sandbox / Live REST Credentials
    PAYPAL_ENV: str = "SANDBOX"
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_WEBHOOK_ID: str = ""

    # Simulated Downstream Pipelines
    ISSUER_SIMULATOR_URL: str = "http://localhost:8201"
    REGULATORY_SIMULATOR_URL: str = "http://localhost:8202"
    CARRIER_SIMULATOR_URL: str = "http://localhost:8203"

    CORS_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3002"
    )

    @property
    def PAYPAL_BASE_URL(self) -> str:
        if (self.PAYPAL_ENV or "SANDBOX").strip().upper() == "LIVE":
            return "https://api-m.paypal.com"
        return "https://api-m.sandbox.paypal.com"

    @property
    def is_nvidia_configured(self) -> bool:
        return bool(self.NVIDIA_API_KEY.strip())

    @property
    def is_paypal_configured(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID.strip() and self.PAYPAL_CLIENT_SECRET.strip())

    @property
    def is_bridge_configured(self) -> bool:
        return bool(self.BRIDGE_SHARED_SECRET.strip() and self.SERVICE_JWT_SECRET.strip())

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
