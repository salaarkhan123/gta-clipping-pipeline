from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


@lru_cache
def get_engine():
    url = get_settings().database_url
    if url.startswith("sqlite"):
        Path(get_settings().data_dir).mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False, "timeout": 30})
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=10)


@lru_cache
def _factory():
    return sessionmaker(get_engine(), expire_on_commit=False)


def new_session():
    return _factory()()


def get_db():
    db = new_session()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)


def _add_missing_columns(engine) -> None:
    """Forward-only migration for columns added after the first deploy. Replace with Alembic when this grows."""
    from sqlalchemy import inspect, text
    wanted = {"jobs": {"result": "JSON"}, "uploads": {"analyzed": "BOOLEAN DEFAULT FALSE"},
              "clips": {"meta": "JSON"},
              "accounts": {"plan": "VARCHAR(20) DEFAULT 'free'", "stripe_customer_id": "VARCHAR(64)",
                           "stripe_subscription_id": "VARCHAR(64)"}}
    insp = inspect(engine)
    for table, cols in wanted.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
