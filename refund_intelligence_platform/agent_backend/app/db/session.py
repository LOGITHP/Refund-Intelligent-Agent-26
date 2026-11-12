from collections.abc import Generator
import re

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
_db_schema = (settings.DB_SCHEMA or "").strip()
if _db_schema and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", _db_schema):
    raise ValueError(f"Invalid DB_SCHEMA: {_db_schema!r}")

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

if _db_schema and not settings.DATABASE_URL.startswith("sqlite"):
    _schema_initialized = False

    @event.listens_for(engine, "connect")
    def _set_postgres_search_path(dbapi_connection, _connection_record) -> None:
        global _schema_initialized
        with dbapi_connection.cursor() as cursor:
            if not _schema_initialized:
                cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{_db_schema}"')
                _schema_initialized = True
            cursor.execute(f'SET search_path TO "{_db_schema}", public')
        dbapi_connection.commit()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Yield a transactional SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
