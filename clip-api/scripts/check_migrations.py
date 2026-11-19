#!/usr/bin/env python3
"""Refuse destructive schema migrations before a deploy runs them.

  python3 scripts/check_migrations.py --versions app/migrations/versions --current 0007

Walks the revision chain from --current (the database's revision; "none" for an empty or pre-migration database)
to head, and reads every pending revision with `ast`, without importing it. Everything outside downgrade() counts,
so helpers that upgrade() calls are covered. It flags:

- any call named drop_* or rename_* (op.drop_column, batch_op.drop_index, op.rename_table, ...)
- alter_column(..., type_=...) or alter_column(..., new_column_name=...)
- SQL text with DROP, TRUNCATE, RENAME, DELETE FROM, UPDATE ... SET or ALTER ... TYPE
- execute() with anything but a literal string, since it cannot be read

Prints key=value lines (current, head, current_known, pending, destructive) and one `finding=` line per hit.
Exit 0: nothing destructive pending. 1: destructive, unreadable, or --current not in the chain. 2: usage.
Standard library only (it runs on the droplet's python3 too). There is no override: a destructive revision is
deployed by hand by the owner, after a backup.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

SQL = re.compile(r"\b(DROP|TRUNCATE|RENAME)\b|\bDELETE\s+FROM\b|\bUPDATE\s+\S+\s+SET\b|\bALTER\b[^;]*\bTYPE\b",
                 re.IGNORECASE)
ALTER_KWARGS = {"type_", "new_column_name"}


def _const(node: ast.AST, name: str) -> str | None:
    """The string in a module-level `name = "..."`, else None."""
    if not (isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)):
        return None
    value = node.value
    return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None


def _call_name(node: ast.Call) -> str:
    return node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")


def _literal_sql(node: ast.AST) -> bool:
    """A literal string, or text("literal") / sa.text("literal")."""
    if isinstance(node, ast.Call) and _call_name(node) == "text" and node.args:
        node = node.args[0]
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def read_revision(path: Path) -> tuple[ast.Module, str, str | None]:
    tree = ast.parse(path.read_text(), filename=str(path))
    rev = down = None
    for node in tree.body:
        rev = _const(node, "revision") or rev
        down = _const(node, "down_revision") or down
    if not rev:
        raise ValueError(f"{path.name}: no literal `revision = \"...\"`")
    return tree, rev, down


def findings(tree: ast.Module, filename: str) -> list[str]:
    hits: list[str] = []
    body = [n for n in tree.body if not (isinstance(n, ast.FunctionDef) and n.name == "downgrade")]
    if not any(isinstance(n, ast.FunctionDef) and n.name == "upgrade" for n in body):
        return [f"{filename}: no upgrade() function"]
    docstrings = {id(n.body[0].value) for n in ast.walk(tree)
                  if isinstance(n, (ast.Module, ast.FunctionDef)) and n.body and isinstance(n.body[0], ast.Expr)
                  and isinstance(n.body[0].value, ast.Constant)}
    for node in (sub for top in body for sub in ast.walk(top)):
        where = f"{filename}:{getattr(node, 'lineno', '?')}"
        if isinstance(node, ast.Call):
            name, kwargs = _call_name(node), {k.arg for k in node.keywords}
            if name.startswith(("drop_", "rename_")):
                hits.append(f"{where}: {name}()")
            elif name == "alter_column" and ALTER_KWARGS & kwargs:
                hits.append(f"{where}: alter_column({', '.join(sorted(ALTER_KWARGS & kwargs))}=...)")
            elif name == "execute" and node.args and not _literal_sql(node.args[0]):
                hits.append(f"{where}: execute() with SQL that is not a literal string")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            m = SQL.search(node.value)
            if m:
                hits.append(f"{where}: SQL {m.group(0).split()[0].upper()}: {node.value.strip()[:80]!r}")
    return hits


def check(versions: Path, current: str) -> tuple[dict[str, str], list[str]]:
    """(summary, findings). Raises ValueError for a broken chain or an unknown current revision."""
    revs: dict[str, tuple[ast.Module, str | None, str]] = {}
    for path in sorted(versions.glob("*.py")):
        tree, rev, down = read_revision(path)
        if rev in revs:
            raise ValueError(f"revision {rev} is defined twice")
        revs[rev] = (tree, down, path.name)
    heads = set(revs) - {down for _, down, _ in revs.values()}
    if len(heads) != 1:
        raise ValueError(f"expected one head, found {sorted(heads) or 'none'}")
    head = heads.pop()
    chain, rev = [], head
    while rev is not None:
        if rev not in revs:
            raise ValueError(f"revision {rev} is referenced but has no file")
        chain.append(rev)
        rev = revs[rev][1]
    chain.reverse()  # baseline first
    if current != "none" and current not in chain:
        return ({"current": current, "head": head, "current_known": "no", "pending": "", "destructive": "unknown"},
                [f"database revision {current} is not in these revision files (database is ahead of this code?)"])
    pending = chain if current == "none" else chain[chain.index(current) + 1:]
    hits = [h for rev in pending for h in findings(revs[rev][0], revs[rev][2])]
    return ({"current": current, "head": head, "current_known": "yes", "pending": ",".join(pending),
             "destructive": "yes" if hits else "no"}, hits)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--versions", type=Path, required=True, help="directory of Alembic revision files")
    p.add_argument("--current", required=True, help='database revision, or "none"')
    a = p.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", a.current) or not a.versions.is_dir():
        print("usage: --current must be a revision id or none, --versions a directory", file=sys.stderr)
        return 2
    try:
        summary, hits = check(a.versions, a.current)
    except (ValueError, SyntaxError) as e:
        print(f"error={str(e).splitlines()[0]}")
        return 1
    for k, v in summary.items():
        print(f"{k}={v}")
    for h in hits:
        print(f"finding={h}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
