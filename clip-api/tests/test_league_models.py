"""Creators League storage: migration 0012 is additive and reversible, the observation and audit tables refuse
changes, and the status tables in app/league.py name every state."""
import pytest
from sqlalchemy import inspect

from app import league
from app.db import new_session
from app.migrate import head, migrate
from app.models import LeagueEvent
from tests.test_migrations import db, diffs  # noqa: F401

TABLES = {"creator_profiles", "league_competitions", "league_entries", "league_view_observations", "league_events"}


def test_migration_0012_league_is_the_head_and_builds_the_league_tables(db):  # noqa: F811
    e = db("league")
    migrate(e)
    assert head() == "0012_league"
    assert TABLES <= set(inspect(e).get_table_names())
    assert diffs(e) == []
    uniques = {tuple(u["column_names"]) for u in inspect(e).get_unique_constraints("league_entries")}
    assert {("competition_id", "account_id"), ("competition_id", "url_key")} <= uniques


def test_migration_0012_league_downgrades_to_0011_and_leaves_the_older_tables(db):  # noqa: F811
    from alembic import command

    from app.migrate import config, current
    e = db("leaguedown")
    migrate(e)
    with e.connect() as c:
        command.downgrade(config(c), "0011")
        c.commit()
    names = set(inspect(e).get_table_names())
    assert current(e) == "0011" and not (TABLES & names) and {"accounts", "clips", "scheduled_posts"} <= names
    migrate(e)
    assert TABLES <= set(inspect(e).get_table_names())


def test_the_audit_log_refuses_updates_and_deletes(client):
    with new_session() as s:
        ev = LeagueEvent(actor_id="acct_x", action="note", entity_kind="entry", entity_id="lent_x")
        s.add(ev)
        s.commit()
        ev.reason = "rewritten"
        with pytest.raises(RuntimeError, match="append-only"):
            s.commit()
        s.rollback()
        s.delete(ev)
        with pytest.raises(RuntimeError, match="append-only"):
            s.commit()


def test_every_entry_move_starts_and_ends_in_a_known_status():
    statuses = set(league.EntryStatus.__args__)
    assert set(league.ENTRY_RULES) == set(league.EntryAction.__args__)
    for allowed, after, _reason in league.ENTRY_RULES.values():
        assert set(allowed) <= statuses and after in statuses
    assert all("disqualified" not in allowed for allowed, _a, _r in league.ENTRY_RULES.values())   # final


def test_every_competition_move_starts_and_ends_in_a_known_status():
    statuses = set(league.CompetitionStatus.__args__)
    assert set(league.COMPETITION_RULES) == set(league.CompetitionAction.__args__)
    for allowed, after in league.COMPETITION_RULES.values():
        assert set(allowed) <= statuses and after in statuses
    assert all("finalized" not in allowed for allowed, _a in league.COMPETITION_RULES.values())    # final
