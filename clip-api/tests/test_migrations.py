"""Alembic: the baseline equals the create_all schema; old databases are stamped, not rebuilt; reruns are no-ops."""
import os
import threading
import uuid

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app import models  # noqa: F401
from app.db import Base, get_engine
from app.migrate import BASELINE, config, current, head, migrate


def diffs(engine):
    with engine.connect() as conn:
        return compare_metadata(MigrationContext.configure(conn, opts={"compare_type": True}), Base.metadata)


def shape(engine):
    insp = inspect(engine)
    return {t: ({c["name"]: (str(c["type"]), c["nullable"]) for c in insp.get_columns(t)},
                sorted((i["name"], tuple(i["column_names"]), bool(i["unique"])) for i in insp.get_indexes(t)),
                sorted(tuple(u["column_names"]) for u in insp.get_unique_constraints(t)),
                sorted((tuple(f["constrained_columns"]), f["referred_table"]) for f in insp.get_foreign_keys(t)))
            for t in insp.get_table_names() if t != "alembic_version"}


PG = os.environ.get("TEST_DATABASE_URL", "").startswith("postgresql")


@pytest.fixture
def db(tmp_path):
    """Fresh empty databases on the suite's dialect: SQLite files, or throwaway Postgres databases in CI."""
    if not PG:
        yield lambda name: create_engine(f"sqlite:///{tmp_path / name}.db")
        return
    base = make_url(os.environ["TEST_DATABASE_URL"])
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    made = []

    def new(name):
        dbname = f"mig_{name}_{uuid.uuid4().hex[:8]}"
        with admin.connect() as c:
            c.execute(text(f'CREATE DATABASE "{dbname}"'))
        made.append(create_engine(base.set(database=dbname)))
        return made[-1]
    yield new
    for e in made:
        e.dispose()
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{e.url.database}" WITH (FORCE)'))
    admin.dispose()


def test_baseline_builds_exactly_the_create_all_schema(db):
    migrated, built = db("migrated"), db("built")
    assert migrate(migrated) == (None, head())
    Base.metadata.create_all(built)
    assert shape(migrated) == shape(built)
    assert diffs(migrated) == []


def test_an_old_database_is_stamped_and_keeps_its_rows(db):
    old = db("old")
    with old.connect() as c:                            # the baseline schema, without the migration bookkeeping
        command.upgrade(config(c), BASELINE)
        c.execute(text("DROP TABLE alembic_version"))
        c.commit()
    with old.begin() as c:                              # as first deployed: before the patched columns existed
        c.execute(text("DROP INDEX ix_accounts_stripe_customer_id"))
        for table, col in (("clips", "meta"), ("uploads", "analyzed"), ("jobs", "result"), ("accounts", "plan"),
                           ("accounts", "stripe_customer_id"), ("accounts", "stripe_subscription_id")):
            c.execute(text(f"ALTER TABLE {table} DROP COLUMN {col}"))
        c.execute(text("INSERT INTO accounts (id, email, password_hash, email_verified, status, webhook_secret,"
                       " created_at) VALUES ('acct_1', 'a@b.c', 'h', TRUE, 'active', 's', '2026-01-01')"))
        c.execute(text("INSERT INTO credit_ledger (account_id, delta, kind, idempotency_key, created_at)"
                       " VALUES ('acct_1', 30, 'grant', 'signup:acct_1', '2026-01-01')"))
    assert migrate(old) == ("legacy", head())
    assert diffs(old) == []
    with old.connect() as c:
        assert c.execute(text("SELECT SUM(delta) FROM credit_ledger")).scalar() == 30
        assert c.execute(text("SELECT email FROM accounts")).scalar() == "a@b.c"


def test_migrate_twice_is_a_no_op(db):
    e = db("twice")
    migrate(e)
    assert migrate(e) == (head(), head()) and current(e) == head()


def test_the_baseline_refuses_to_downgrade(db):
    e = db("down")
    migrate(e)
    with e.connect() as c, pytest.raises(RuntimeError, match="not reversible"):
        command.downgrade(config(c), "base")
    assert current(e) == BASELINE


def test_the_app_database_is_at_head_and_matches_the_models(client):
    # SQLite locally, Postgres 16 in CI (TEST_DATABASE_URL): the same check on the real dialect.
    assert current(get_engine()) == head()
    assert diffs(get_engine()) == []


@pytest.mark.skipif(not PG, reason="the advisory lock is Postgres only (SQLite is dev and tests)")
def test_api_and_worker_starting_together_migrate_once(db):
    e = db("race")
    results, errors = [], []

    def start():
        try:
            results.append(migrate(create_engine(e.url)))
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)
    threads = [threading.Thread(target=start) for _ in range(2)]
    [th.start() for th in threads]
    [th.join() for th in threads]
    assert errors == [] and sorted(results, key=str) == sorted([(None, head()), (head(), head())], key=str)
    assert diffs(e) == []


def test_an_old_database_missing_a_table_is_refused_not_patched(db):
    e = db("partial")
    with e.connect() as c:
        command.upgrade(config(c), BASELINE)
        c.execute(text("DROP TABLE alembic_version"))
        c.execute(text("DROP TABLE webhook_deliveries"))
        c.commit()
    with pytest.raises(RuntimeError, match="webhook_deliveries"):
        migrate(e)
    assert current(e) is None
