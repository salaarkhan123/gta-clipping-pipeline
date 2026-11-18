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
    """Bring the schema to the latest migration (app/migrate.py). Safe to call from every process at start."""
    from .migrate import migrate
    migrate(get_engine())
