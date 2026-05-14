from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import get_settings
from app.models.db import Base

settings = get_settings()

# statement_timeout kills any single query that runs longer than the configured
# threshold. Without this a pathological full-table scan (e.g. missing index)
# holds a connection open for minutes and starves the pool.
# Only set for PostgreSQL — SQLite (used in tests) doesn't understand the option.
_connect_args: dict = {}
if settings.database_url.startswith("postgresql"):
    _connect_args["options"] = f"-c statement_timeout={settings.db_statement_timeout_ms}"

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    connect_args=_connect_args,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
