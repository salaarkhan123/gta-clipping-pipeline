"""Schema migrations (Alembic, app/migrations). migrate() brings any database to the latest revision.

- New database: runs every revision from the baseline.
- Database from before migrations (tables, no alembic_version): first adds the columns and the index that the
  old startup patch added or missed, so it equals the baseline, then stamps it at the baseline without running
  it, then runs any newer revision.
- Postgres: holds an advisory lock while migrating, so the api and the worker starting together cannot race.

Add a revision: change app/models.py, then
  python -c "from app.migrate import new_revision; new_revision('add uploads.content_hash')"
and review the generated file in app/migrations/versions/ before committing it.
"""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Boolean, Engine, inspect, text

BASELINE = "0001"
LOCK_KEY = 72026111  # pg_advisory_lock key for migrations
log = logging.getLogger("clipapi.migrate")

# Columns added before migrations existed, by the old forward-only patch. Legacy databases only.
LEGACY_COLUMNS = {"jobs": {"result": "JSON"}, "uploads": {"analyzed": "BOOLEAN DEFAULT FALSE"},
                  "clips": {"meta": "JSON"},
                  "accounts": {"plan": "VARCHAR(20) DEFAULT 'free'", "stripe_customer_id": "VARCHAR(64)",
                               "stripe_subscription_id": "VARCHAR(64)"}}

LEGACY_INDEXES = {"ix_accounts_stripe_customer_id": ("accounts", "stripe_customer_id")}
BASELINE_TABLES = {"accounts", "api_keys", "uploads", "jobs", "clips", "credit_ledger", "webhook_deliveries"}


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


def _known(conn, revision: str) -> bool:
    """Whether this code's migration scripts contain `revision`."""
    try:
        return ScriptDirectory.from_config(config(conn)).get_revision(revision) is not None
    except Exception:       # alembic raises ResolutionError / CommandError for an unknown revision
        return False


def _bring_legacy_to_baseline(conn) -> None:
    """Everything here is frozen at revision 0001. It must never read app/models.py: the models move on with
    later revisions, and those revisions (not this step) are what bring an old database further."""
    insp = inspect(conn)
    missing = BASELINE_TABLES - set(insp.get_table_names())
    if missing:
        raise RuntimeError(f"this database has some tables but not {sorted(missing)}: restore or repair it first")
    for table, cols in LEGACY_COLUMNS.items():
        have = {c["name"] for c in insp.get_columns(table)}
        for name, ddl in cols.items():
            if name not in have:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    # The patch added columns without their indexes.
    for name, (table, column) in LEGACY_INDEXES.items():
        if name not in {i["name"] for i in inspect(conn).get_indexes(table)}:
            conn.execute(text(f"CREATE INDEX {name} ON {table} ({column})"))
    # The patch added uploads.analyzed as nullable; the baseline has it NOT NULL. NULL already read as False.
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
            if before is not None and not _known(conn, before):
                # A newer release migrated this database and the code was rolled back. Migrations are additive, so
                # this code runs on the newer schema; never try to "upgrade" to an older head.
                log.warning("database is at revision %s, newer than this code knows (head %s): starting without "
                            "migrating", before, head())
                return before, before
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
