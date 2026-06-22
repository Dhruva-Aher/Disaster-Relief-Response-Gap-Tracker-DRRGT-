from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import get_settings
from app.models.db import Base

settings = get_settings()

# pool_pre_ping re-checks stale connections before use (handles RDS failover / idle timeouts)
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def init_db() -> None:
    """Create all tables if they do not already exist.

    Used by the seed script and test fixtures. In production, Alembic
    migrations are the authoritative schema manager — this function is only
    a convenience fallback so the seed script doesn't require a running
    Alembic context.
    """
    Base.metadata.create_all(bind=engine)


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
