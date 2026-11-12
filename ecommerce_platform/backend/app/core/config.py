from typing import List
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Shipkart E-Commerce API"
    API_V1_STR: str = "/api/v1"

    DATABASE_URL: str = "sqlite:///./data/ecommerce.db"

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

    SECRET_KEY: str = "shipkart-dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # PayPal Sandbox / Live REST App Settings
    PAYPAL_CLIENT_ID: str = ""
    PAYPAL_CLIENT_SECRET: str = ""
    PAYPAL_WEBHOOK_ID: str = ""
    PAYPAL_ENV: str = "SANDBOX"

    # AES-256-GCM Master Key for encrypted stored fields (never committed or stored in DB)
    APP_DATA_ENCRYPTION_KEY: str = ""

    # Inventory reservation time-to-live (minutes)
    RESERVATION_TTL_MINUTES: int = 15

    # Refund Intelligence Platform Bridge Settings
    AGENT_PLATFORM_URL: str = "http://localhost:8100"
    BRIDGE_SHARED_SECRET: str = ""
    SERVICE_JWT_SECRET: str = ""
    SERVICE_JWT_ISSUER: str = "refund-intelligence-platform"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_PUBLIC_URL: str = "http://localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False

    BUCKET_PRODUCT_IMAGES: str = "product-images"
    BUCKET_INVOICES: str = "invoices"
    BUCKET_RETURN_EVIDENCE: str = "return-evidence"

    SEED_SAMPLE_CATALOG: bool = True

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
    def is_paypal_configured(self) -> bool:
        return bool(self.PAYPAL_CLIENT_ID.strip() and self.PAYPAL_CLIENT_SECRET.strip())

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
