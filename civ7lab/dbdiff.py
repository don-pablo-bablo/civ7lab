"""`civ7lab dbdiff`: what changed between two game databases.

The usual case is a game patch: compare a dump taken before it with one taken
after, and see which rows Firaxis added, removed or changed. Rows are paired
by the table's primary key, so a changed row reads as one change naming its
columns rather than as a removal and an addition.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TableChange:
    table: str
    added: int = 0
    removed: int = 0
    changed: int = 0
    columns_added: list[str] = field(default_factory=list)
    columns_removed: list[str] = field(default_factory=list)
    note: str = ""  # "new table" or "table removed"
    # One line per row: `~ KEY: Column old -> new`, and `+ KEY` or `- KEY`,
    # or the whole row where the table has no primary key.
    lines: list[str] = field(default_factory=list)

    @property
    def count(self) -> int:
        return self.added + self.removed + self.changed


def _read(path: Path) -> dict[str, tuple[list[str], list[str], list[tuple]]]:
    """Each table's columns, primary key columns and rows."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        out = {}
        for table in tables:
            info = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
            columns = [row[1] for row in info]
            key = [row[1] for row in sorted(info, key=lambda row: row[5]) if row[5]]
            out[table] = (columns, key, connection.execute(f'SELECT * FROM "{table}"').fetchall())
        return out
    finally:
        connection.close()


def _label(key: tuple) -> str:
    return ", ".join(str(part) for part in key)


def compare(before: str | Path, after: str | Path) -> list[TableChange]:
    """Every table that differs, in name order."""
    old, new = _read(Path(before)), _read(Path(after))
    changes = []
    for table in sorted(set(old) | set(new)):
        if table not in old or table not in new:
            rows = (new if table in new else old)[table][2]
            whole = TableChange(table, note="new table" if table in new else "table removed")
            if table in new:
                whole.added, whole.lines = len(rows), [f"+ {row}" for row in rows]
            else:
                whole.removed, whole.lines = len(rows), [f"- {row}" for row in rows]
            changes.append(whole)
            continue
        old_columns, _, old_rows = old[table]
        new_columns, key, new_rows = new[table]
        change = TableChange(
            table,
            columns_added=[c for c in new_columns if c not in old_columns],
            columns_removed=[c for c in old_columns if c not in new_columns],
        )
        # Compare by column name, so a column added mid-table does not shift
        # every value after it.
        shared = [c for c in new_columns if c in old_columns]
        old_at = {c: i for i, c in enumerate(old_columns)}
        new_at = {c: i for i, c in enumerate(new_columns)}

        def pick(row, at, shared=shared):
            return tuple(row[at[c]] for c in shared)

        old_set = {pick(row, old_at) for row in old_rows}
        new_set = {pick(row, new_at) for row in new_rows}
        gone, came = old_set - new_set, new_set - old_set
        if key and all(k in shared for k in key):
            key_at = [shared.index(k) for k in key]
            gone_by_key = {tuple(r[i] for i in key_at): r for r in gone}
            came_by_key = {tuple(r[i] for i in key_at): r for r in came}
            for k in sorted(set(gone_by_key) & set(came_by_key), key=repr):
                was, now = gone_by_key.pop(k), came_by_key.pop(k)
                diffs = [
                    f"{column} {was[i]!r} -> {now[i]!r}"
                    for i, column in enumerate(shared)
                    if was[i] != now[i]
                ]
                change.lines.append(f"~ {_label(k)}: " + ", ".join(diffs))
                change.changed += 1
            change.lines += [f"+ {_label(k)}" for k in sorted(came_by_key, key=repr)]
            change.lines += [f"- {_label(k)}" for k in sorted(gone_by_key, key=repr)]
            change.added, change.removed = len(came_by_key), len(gone_by_key)
        else:
            change.lines += [f"+ {row}" for row in sorted(came, key=repr)]
            change.lines += [f"- {row}" for row in sorted(gone, key=repr)]
            change.added, change.removed = len(came), len(gone)
        if change.count or change.columns_added or change.columns_removed:
            changes.append(change)
    return changes
