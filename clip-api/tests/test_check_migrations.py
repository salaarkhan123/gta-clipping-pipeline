"""scripts/check_migrations.py: destructive revisions are refused before a deploy runs them."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("check_migrations", ROOT / "scripts" / "check_migrations.py")
cm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cm)

HEADER = 'import sqlalchemy as sa\nfrom alembic import op\nrevision = "{rev}"\ndown_revision = {down!r}\n'
SAFE = 'op.add_column("t", sa.Column("c", sa.Integer(), nullable=True))'


def write(d: Path, rev: str, down: str | None, upgrade: str = SAFE, extra: str = "",
          downgrade: str = 'op.drop_column("t", "c")') -> None:
    body = "\n".join("    " + line for line in upgrade.splitlines())
    (d / f"{rev}_x.py").write_text(HEADER.format(rev=rev, down=down) + extra +
                                   f"\n\ndef upgrade():\n{body}\n\n\ndef downgrade():\n    {downgrade}\n")


def run(d: Path, current: str) -> tuple[int, str]:
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cm.main(["--versions", str(d), "--current", current])
    return rc, buf.getvalue()


def test_every_revision_in_the_repo_is_additive():
    rc, out = run(ROOT / "app" / "migrations" / "versions", "none")
    assert rc == 0, out
    assert "destructive=no" in out


@pytest.mark.parametrize("upgrade", [
    'op.drop_column("t", "c")',
    'op.drop_table("t")',
    'op.drop_index("ix_t_c", table_name="t")',
    'op.drop_constraint("fk", "t")',
    'op.rename_table("t", "u")',
    'op.alter_column("t", "c", new_column_name="d")',
    'op.alter_column("t", "c", type_=sa.String(10))',
    'with op.batch_alter_table("t") as batch_op:\n    batch_op.drop_column("c")',
    'op.execute("DROP TABLE t")',
    'op.execute(sa.text("truncate t"))',
    'op.execute("UPDATE t SET c = 0")',
    'op.execute("delete from t")',
    'op.execute("ALTER TABLE t RENAME COLUMN c TO d")',
    'op.execute("ALTER TABLE t ALTER COLUMN c TYPE bigint")',
    'name = "t"\nop.execute(f"DROP TABLE {name}")',
    'op.get_bind().execute(sa.text(QUERY))',
])
def test_destructive_operations_are_refused(tmp_path, upgrade):
    write(tmp_path, "0001", None)
    write(tmp_path, "0002", "0001", upgrade, extra='QUERY = "select 1"\n')
    rc, out = run(tmp_path, "0001")
    assert rc == 1 and "destructive=yes" in out and "finding=0002_x.py:" in out


def test_a_drop_inside_a_helper_that_upgrade_calls_is_found(tmp_path):
    write(tmp_path, "0001", None)
    write(tmp_path, "0002", "0001", "_cleanup()", extra='\n\ndef _cleanup():\n    op.drop_table("old")\n')
    rc, out = run(tmp_path, "0001")
    assert rc == 1 and "drop_table()" in out


@pytest.mark.parametrize("upgrade", [
    SAFE,
    'op.create_table("u", sa.Column("id", sa.Integer(), primary_key=True))',
    'op.create_index("ix_t_c", "t", ["c"])',
    'op.alter_column("t", "c", nullable=False, existing_type=sa.Integer())',
    'op.execute("CREATE INDEX ix ON t (c)")',
    'op.execute(sa.text("INSERT INTO t (c) VALUES (1)"))',
])
def test_additive_operations_pass(tmp_path, upgrade):
    write(tmp_path, "0001", None)
    write(tmp_path, "0002", "0001", upgrade)
    rc, out = run(tmp_path, "0001")
    assert rc == 0, out
    assert "pending=0002" in out and "destructive=no" in out


def test_downgrade_and_docstrings_do_not_count(tmp_path):
    write(tmp_path, "0001", None)
    (tmp_path / "0002_x.py").write_text('"""Adds c. The downgrade drops it again; DROP TABLE is never used here."""\n'
                                        + HEADER.format(rev="0002", down="0001")
                                        + f"\n\ndef upgrade():\n    {SAFE}\n\n\ndef downgrade():\n"
                                        + '    op.drop_column("t", "c")\n    op.execute("DROP TABLE x")\n')
    rc, out = run(tmp_path, "0001")
    assert rc == 0, out


def test_only_pending_revisions_are_checked(tmp_path):
    write(tmp_path, "0001", None)
    write(tmp_path, "0002", "0001", 'op.drop_column("t", "old")')   # already applied: the owner ran it by hand
    write(tmp_path, "0003", "0002")
    assert run(tmp_path, "0002")[0] == 0
    assert run(tmp_path, "0001")[0] == 1
    assert run(tmp_path, "0003")[1].count("pending=\n") == 1


def test_a_database_ahead_of_the_code_is_refused(tmp_path):
    write(tmp_path, "0001", None)
    rc, out = run(tmp_path, "0002")
    assert rc == 1 and "current_known=no" in out


@pytest.mark.parametrize("files", [
    {"0001_x.py": "def upgrade(:\n"},
    {"0001_x.py": 'revision = "0001"\ndown_revision = None\n'},          # no upgrade()
    {"0001_x.py": HEADER.format(rev="0001", down=None) + "\ndef upgrade():\n    pass\n",
     "0002_x.py": HEADER.format(rev="0002", down=None) + "\ndef upgrade():\n    pass\n"},  # two heads
])
def test_unreadable_revisions_fail_closed(tmp_path, files):
    for name, text in files.items():
        (tmp_path / name).write_text(text)
    assert run(tmp_path, "none")[0] == 1
