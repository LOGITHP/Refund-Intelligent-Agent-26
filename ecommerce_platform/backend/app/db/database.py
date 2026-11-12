from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# Ensure local SQLite data folder exists if using SQLite
if settings.DATABASE_URL.startswith("sqlite:///"):
    db_path = settings.DATABASE_URL.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

is_sqlite = settings.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if is_sqlite else {}
engine_kwargs = {"connect_args": connect_args, "echo": False}
if not is_sqlite:
    engine_kwargs["pool_pre_ping"] = True

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_schema_columns(target_engine=None) -> None:
    """Idempotently adds new payment/currency columns to pre-existing SQLite/PostgreSQL databases."""
    eng = target_engine or engine
    inspector = inspect(eng)

    migrations = {
        "products": [
            ("sandbox_usd_price", "NUMERIC(12, 2) NOT NULL DEFAULT 10.00"),
        ],
        "orders": [
            ("merchant_id", "INTEGER"),
            ("original_currency", "VARCHAR(8) NOT NULL DEFAULT 'INR'"),
            ("paypal_currency", "VARCHAR(8)"),
            ("paypal_amount", "NUMERIC(12, 2)"),
            ("paypal_create_request_id", "VARCHAR(128)"),
            ("paypal_capture_request_id", "VARCHAR(128)"),
            ("payment_provider_mode", "VARCHAR(64) NOT NULL DEFAULT 'MERCHANT_DIRECT'"),
        ],
        "merchant_payment_preferences": [
            ("paypal_environment", "VARCHAR(16) NOT NULL DEFAULT 'SANDBOX'"),
            ("paypal_client_id", "VARCHAR(255)"),
            ("encrypted_paypal_client_secret", "TEXT"),
            ("paypal_client_secret_last4", "VARCHAR(8)"),
            ("paypal_webhook_id", "VARCHAR(255)"),
            ("credential_verified_at", "TIMESTAMP WITH TIME ZONE"),
        ],
        "return_requests": [
            ("refund_currency", "VARCHAR(8) NOT NULL DEFAULT 'USD'"),
            ("refund_paypal_amount", "NUMERIC(12, 2)"),
        ],
    }

    with eng.begin() as conn:
        for table_name, columns in migrations.items():
            if not inspector.has_table(table_name):
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            for col_name, col_def in columns:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_def}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
