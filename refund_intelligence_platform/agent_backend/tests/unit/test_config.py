import os
from unittest.mock import patch

from app.core.config import Settings


SECRET_FIELDS = (
    "BRIDGE_SHARED_SECRET",
    "SERVICE_JWT_SECRET",
    "JWT_SECRET_KEY",
    "NVIDIA_API_KEY",
    "PAYPAL_CLIENT_ID",
    "PAYPAL_CLIENT_SECRET",
    "PAYPAL_WEBHOOK_ID",
    "MINIO_ACCESS_KEY",
    "MINIO_SECRET_KEY",
    "PLATFORM_ADMIN_PASSWORD",
)


def test_settings_defaults_and_urls() -> None:
    """Verify non-secret defaults and local service URL resolution."""
    with patch.dict(os.environ, {}, clear=True):
        cfg = Settings(_env_file=None)

    assert cfg.AGENT_API_PORT == 8100
    assert cfg.DATABASE_URL.startswith("postgresql+psycopg://")
    assert "5433" in cfg.DATABASE_URL
    assert cfg.REDIS_URL == "redis://localhost:6379/0"
    assert cfg.MINIO_ENDPOINT == "localhost:9002"
    assert cfg.SHIPKART_API_URL == "http://localhost:8000"
    assert cfg.ISSUER_SIMULATOR_URL == "http://localhost:8201"
    assert cfg.REGULATORY_SIMULATOR_URL == "http://localhost:8202"
    assert cfg.CARRIER_SIMULATOR_URL == "http://localhost:8203"
    assert cfg.NVIDIA_BASE_URL == "https://integrate.api.nvidia.com/v1"
    assert cfg.NVIDIA_REASONING_MODEL == "nvidia/nemotron-3.5-super-vl-120b-a12b"
    assert cfg.NVIDIA_VISION_MODEL == "nvidia/nemotron-3.5-super-vl-120b-a12b"
    assert cfg.PAYPAL_ENV == "SANDBOX"
    assert cfg.PAYPAL_BASE_URL == "https://api-m.sandbox.paypal.com"
    assert "http://localhost:3002" in cfg.cors_origins_list


def test_no_hardcoded_secrets_in_defaults() -> None:
    """Ensure all secret/credential fields default to empty strings."""
    with patch.dict(os.environ, {}, clear=True):
        cfg = Settings(_env_file=None)

    for field in SECRET_FIELDS:
        assert getattr(cfg, field) == "", f"{field} must not have a hardcoded default"

    assert "@" not in cfg.DATABASE_URL
    assert cfg.is_nvidia_configured is False
    assert cfg.is_paypal_configured is False
    assert cfg.is_bridge_configured is False


def test_paypal_base_url_resolution_live_and_sandbox() -> None:
    """PAYPAL_BASE_URL switches cleanly between Sandbox and Live."""
    sandbox_cfg = Settings(_env_file=None, PAYPAL_ENV="sandbox")
    live_cfg = Settings(_env_file=None, PAYPAL_ENV="LIVE")

    assert sandbox_cfg.PAYPAL_BASE_URL == "https://api-m.sandbox.paypal.com"
    assert live_cfg.PAYPAL_BASE_URL == "https://api-m.paypal.com"


def test_configured_flags_reflect_environment_values() -> None:
    """Configured flags return True only when non-whitespace secrets are provided."""
    blank_cfg = Settings(
        _env_file=None,
        NVIDIA_API_KEY="   ",
        PAYPAL_CLIENT_ID="id-only",
        PAYPAL_CLIENT_SECRET="   ",
        BRIDGE_SHARED_SECRET="bridge-secret",
        SERVICE_JWT_SECRET="   ",
    )
    assert blank_cfg.is_nvidia_configured is False
    assert blank_cfg.is_paypal_configured is False
    assert blank_cfg.is_bridge_configured is False

    ready_cfg = Settings(
        _env_file=None,
        NVIDIA_API_KEY="nvapi-test-key",
        PAYPAL_CLIENT_ID="paypal-client-id",
        PAYPAL_CLIENT_SECRET="paypal-client-secret",
        BRIDGE_SHARED_SECRET="bridge-secret",
        SERVICE_JWT_SECRET="service-jwt-secret",
    )
    assert ready_cfg.is_nvidia_configured is True
    assert ready_cfg.is_paypal_configured is True
    assert ready_cfg.is_bridge_configured is True
