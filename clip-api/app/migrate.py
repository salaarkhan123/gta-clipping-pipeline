"""Schema migrations (Alembic, app/migrations). migrate() brings any database to the latest revision.

- New database: runs every revision from the baseline.
- Database from before migrations (tables, no alembic_version): first applies what init_db used to do on every
  start (create missing tables, add the columns added since the first deploy), so it equals the baseline, then
  stamps it at the baseline without running it, then runs any newer revision.
- Postgres: holds an advisory lock while migrating, so the api and the worker starting together cannot race.

Add a revision: change app/models.py, then
  python -c "from app.migrate import new_revision; new_revision('add uploads.content_hash')"
and review the generated file in app/migrations/versions/ before committing it.
"""
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Boolean, Engine, inspect, text

BASELINE = "0001"
LOCK_KEY = 72026111  # pg_advisory_lock key for migrations

# Columns added before migrations existed, by the old forward-only patch. Legacy databases only.
LEGACY_COLUMNS = {"jobs": {"result": "JSON"}, "uploads": {"analyzed": "BOOLEAN DEFAULT FALSE"},
                  "clips": {"meta": "JSON"},
                  "accounts": {"plan": "VARCHAR(20) DEFAULT 'free'", "stripe_customer_id": "VARCHAR(64)",
                               "stripe_subscription_id": "VARCHAR(64)"}}


def config(connection=None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    cfg.attributes["connection"] = connection
    return cfg


def head() -> str:
    return ScriptDirectory.from_config(config()).get_current_head()


def current(engine: Engine) -> str | None:
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _bring_legacy_to_baseline(conn) -> None:
    from . import models  # noqa: F401  (register tables)
    from .db import Base
    Base.metadata.create_all(conn)
    insp = inspect(conn)
    for table, cols in LEGACY_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    # The patch added columns without their indexes (accounts.stripe_customer_id): create any that are missing.
    for table in Base.metadata.sorted_tables:
        have = {i["name"] for i in inspect(conn).get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in have:
                index.create(conn)
    # The patch added uploads.analyzed as nullable; the model has it NOT NULL. NULL already read as False.
    if next(c for c in inspect(conn).get_columns("uploads") if c["name"] == "analyzed")["nullable"]:
        conn.execute(text("UPDATE uploads SET analyzed = FALSE WHERE analyzed IS NULL"))
        with Operations(MigrationContext.configure(conn)).batch_alter_table("uploads") as batch:
            batch.alter_column("analyzed", existing_type=Boolean(), nullable=False)


def migrate(engine: Engine) -> tuple[str | None, str]:
    """Upgrade to head. Returns (revision before, revision after); before is "legacy" for a stamped old database."""
    with engine.connect() as conn:
        pg = conn.dialect.name == "postgresql"
        if pg:
            conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": LOCK_KEY})
            conn.commit()
        try:
            before = MigrationContext.configure(conn).get_current_revision()
            tables = set(inspect(conn).get_table_names())
            if before is None and "accounts" in tables:
                _bring_legacy_to_baseline(conn)
                command.stamp(config(conn), BASELINE)
                before = "legacy"
            command.upgrade(config(conn), "head")
            conn.commit()
            return before, MigrationContext.configure(conn).get_current_revision()
        finally:
            if pg:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": LOCK_KEY})
                conn.commit()


def new_revision(message: str) -> None:
    """Autogenerate a revision from the difference between app/models.py and the configured database."""
    command.revision(config(), message=message, autogenerate=True)
