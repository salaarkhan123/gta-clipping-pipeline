"""Alembic: the baseline equals the create_all schema; old databases are stamped, not rebuilt; reruns are no-ops."""
import os
import re
import threading
import uuid
from datetime import datetime

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
import sqlalchemy as sa
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from app import models  # noqa: F401
from app.db import Base, get_engine
from app.migrate import BASELINE, config, current, head, incompatible, migrate


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
    # Never below the baseline. Postgres rolls the whole failed downgrade back; SQLite stops at the baseline.
    assert current(e) in (BASELINE, head()) and "credit_ledger" in inspect(e).get_table_names()


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


def test_a_database_ahead_of_this_code_starts_without_migrating(db, caplog):
    """A code rollback after a newer release migrated the database: the older code must still start. It leaves the
    newer revision alone (migrations are additive, so the old code runs on the newer schema) and says so in the log."""
    engine = db("ahead")
    migrate(engine)
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    caplog.set_level("WARNING", logger="clipapi.migrate")
    assert migrate(engine) == ("9999", "9999")
    assert current(engine) == "9999"
    assert any("newer" in r.getMessage() and "9999" in r.getMessage() for r in caplog.records)


def _apply_future_revision(engine):
    """What a later, additive release could do: a nullable column, a NOT NULL column with a server default, and a
    new table. Then the database says it is at a revision this code has no script for."""
    with engine.begin() as conn:
        ops = Operations(MigrationContext.configure(conn))
        ops.add_column("clips", sa.Column("future_note", sa.String(40), nullable=True))
        ops.add_column("payments", sa.Column("future_flag", sa.Boolean(), nullable=False, server_default=sa.false()))
        ops.create_table("future_things", sa.Column("id", sa.Integer(), primary_key=True),
                         sa.Column("clip_id", sa.String(40), sa.ForeignKey("clips.id"), nullable=False))
        conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))


def test_rolling_back_from_a_newer_additive_release_keeps_this_code_working(db, caplog):
    """A newer release migrated the database additively and its code was rolled back to this one: startup goes on
    without migrating, and this code's models still write and read the tables the newer release changed."""
    engine = db("rollback_future")
    migrate(engine)
    _apply_future_revision(engine)
    assert current(engine) == "9999"

    caplog.set_level("WARNING", logger="clipapi.migrate")
    assert migrate(engine) == ("9999", "9999")
    assert current(engine) == "9999"
    with engine.connect() as conn:
        assert incompatible(conn) == []

    from sqlalchemy.orm import Session

    from app.models import Account, Clip, Job, Payment, Upload
    now = datetime(2026, 11, 18)
    with Session(engine) as s:
        s.add(Account(id="a1", email="rollback@example.com", password_hash="x", webhook_secret="w"))
        s.flush()
        s.add(Upload(id="u1", account_id="a1", filename="v.mp4", storage_key="k", size_bytes=1, duration_sec=1.0,
                     width=1920, height=1080, has_audio=True, expires_at=now))
        s.flush()
        s.add(Job(id="j1", account_id="a1", upload_id="u1", options={}, duration_sec=1.0, credits_reserved=1,
                  expires_at=now))
        s.flush()
        s.add(Clip(id="c1", job_id="j1", idx=0, start_sec=0.0, end_sec=1.0, score=1.0, signals={}, features={},
                   video_key="v"))
        s.add(Payment(account_id="a1", kind="pack", stripe_ref="cs_rollback", credits=10))
        s.commit()
    with Session(engine) as s:
        assert s.get(Clip, "c1").video_key == "v"
        assert s.query(Payment).one().credits == 10
    with engine.connect() as conn:
        assert conn.execute(text("SELECT future_note FROM clips")).one() == (None,)
        assert not conn.execute(text("SELECT future_flag FROM payments")).scalar_one()


@pytest.mark.parametrize("change, problem", [
    ("dropped column", "column clips.reaction is missing"),
    ("required column", "clips.made_required is NOT NULL with no default, and this code never sets it"),
    ("dropped table", "table clip_feedback is missing"),
])
def test_a_newer_schema_this_code_cannot_use_refuses_to_start(db, change, problem):
    """A database newer than the code is only started on when the code can still use it. A newer release that
    dropped something this code reads, or added a column this code cannot fill, stops startup with the reason."""
    engine = db("incompatible_" + change.replace(" ", "_"))
    migrate(engine)
    with engine.begin() as conn:
        ops = Operations(MigrationContext.configure(conn))
        if change == "dropped column":
            ops.drop_column("clips", "reaction")
        elif change == "required column":
            recreate = "always" if conn.dialect.name == "sqlite" else "auto"   # SQLite cannot ALTER in NOT NULL
            with ops.batch_alter_table("clips", recreate=recreate) as batch:
                batch.add_column(sa.Column("made_required", sa.String(10), nullable=False))
        else:
            ops.drop_table("clip_feedback")
        conn.execute(text("UPDATE alembic_version SET version_num = '9999'"))
    with pytest.raises(RuntimeError, match="cannot use its schema: .*" + re.escape(problem)):
        migrate(engine)
    assert current(engine) == "9999"
