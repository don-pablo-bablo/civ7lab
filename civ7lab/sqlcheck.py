"""`civ7lab sql`: apply a mod's database files to a copy of the game's
database and report which rows each table gained or lost.

The game dumps its database to Debug/gameplay-copy.sqlite. A copy of that,
with foreign keys on, takes a mod's SQL and XML in under a second.

* **Foreign keys**: `INSERT OR IGNORE` does not cover them. An insert that
  names a row this age does not load fails here, as it would in the game.
* **Dirty baseline**: a dump taken with the mod loaded already holds its
  rows. `prefix` deletes tags and types starting with it first, and counts
  them.
* **Order and age**: files apply in the modinfo's order for the age given, so
  a delete that undoes an earlier insert shows as a missing row.

GameEffects XML is read by the engine's effects system, which is not
reproduced here. Those files are checked for structure and for modifier ids
that nothing defines.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
import tempfile
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path

from . import modinfo, paths

# --------------------------------------------------------------------------
# The database workspace
# --------------------------------------------------------------------------


def _make_hash(value) -> int:
    """A stand-in for the engine's Make_Hash. The values differ from the
    game's; only equal text giving equal hashes matters here."""
    if value is None:
        return 0
    text = str(value).encode("utf-8")
    # FNV-1a, 32 bit, signed the way the database stores it.
    hashed = 0x811C9DC5
    for byte in text:
        hashed = ((hashed ^ byte) * 0x01000193) & 0xFFFFFFFF
    return hashed - 0x100000000 if hashed >= 0x80000000 else hashed


def default_db() -> Path | None:
    """The game's own dump, if there is one. A dump written at the main menu
    holds no age's data; `describe()` shows that."""
    game = paths.game()
    if game.debug_dumps and (game.debug_dumps / "gameplay-copy.sqlite").is_file():
        return game.debug_dumps / "gameplay-copy.sqlite"
    return None


def describe(db_path: Path) -> dict:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:

        def count(table):
            try:
                return connection.execute(f'select count(*) from "{table}"').fetchone()[0]
            except sqlite3.Error:
                return 0

        # The age the dump was taken in. Only that age's buildings are in it.
        active = None
        try:
            row = connection.execute("select AgeType from Ages where Active = 1").fetchone()
            active = row[0] if row else None
        except sqlite3.Error:
            pass
        return {
            "path": str(db_path),
            "active_age": active,
            "constructibles": count("Constructibles"),
            "types": count("Types"),
            "tables": count("sqlite_master"),
        }
    finally:
        connection.close()


# --------------------------------------------------------------------------
# XML that is really table data
# --------------------------------------------------------------------------


def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def xml_to_statements(path: Path) -> tuple[list[tuple[str, tuple]], list[str]]:
    """Translate a <Database> document into statements.

    Covers the shapes Firaxis' own data uses: <Row>, <Replace>, <Delete> and
    <Update><Where/><Set/></Update>. Anything else comes back as a note.
    """
    statements: list[tuple[str, tuple]] = []
    notes: list[str] = []
    root = ElementTree.parse(path).getroot()
    if _localname(root.tag) != "Database":
        return [], [f"{path.name}: root is <{_localname(root.tag)}>, not <Database>"]

    for table in root:
        table_name = _localname(table.tag)
        if table_name in ("Comment",) or not isinstance(table.tag, str):
            continue
        for element in table:
            kind = _localname(element.tag)
            if kind in ("Row", "Replace"):
                columns = list(element.attrib)
                verb = "INSERT OR REPLACE" if kind == "Replace" else "INSERT"
                if not columns:
                    notes.append(f"{path.name}: <{kind}> in {table_name} has no columns")
                    continue
                placeholders = ", ".join("?" for _ in columns)
                quoted = ", ".join(f'"{column}"' for column in columns)
                statements.append(
                    (
                        f'{verb} INTO "{table_name}" ({quoted}) VALUES ({placeholders})',
                        tuple(element.attrib[column] for column in columns),
                    )
                )
            elif kind == "Delete":
                where = " AND ".join(f'"{column}" = ?' for column in element.attrib)
                clause = f" WHERE {where}" if where else ""
                statements.append(
                    (f'DELETE FROM "{table_name}"{clause}', tuple(element.attrib.values()))
                )
            elif kind == "Update":
                where_node = element.find("Where") if element.find("Where") is not None else None
                set_node = element.find("Set") if element.find("Set") is not None else None
                if set_node is None:
                    notes.append(f"{path.name}: <Update> in {table_name} has no <Set>")
                    continue
                assignments = ", ".join(f'"{column}" = ?' for column in set_node.attrib)
                values = list(set_node.attrib.values())
                clause = ""
                if where_node is not None and where_node.attrib:
                    clause = " WHERE " + " AND ".join(f'"{c}" = ?' for c in where_node.attrib)
                    values += list(where_node.attrib.values())
                statements.append(
                    (f'UPDATE "{table_name}" SET {assignments}{clause}', tuple(values))
                )
            else:
                notes.append(f"{path.name}: unhandled <{kind}> in {table_name}")
    return statements, notes


def game_effects_report(paths_in: list[Path]) -> list[str]:
    """Structural checks for GameEffects files, which are not applied here.

    Catches a <GameModifiers> row naming a modifier no file defines. The game
    reports no error for that; the modifier just does nothing.
    """
    defined: set[str] = set()
    referenced: dict[str, Path] = {}
    notes: list[str] = []
    for path in paths_in:
        try:
            root = ElementTree.parse(path).getroot()
        except ElementTree.ParseError as error:
            notes.append(f"{path.name}: will not parse: {error}")
            continue
        for element in root.iter():
            name = _localname(element.tag)
            if name == "Modifier" and element.get("id"):
                identifier = element.get("id")
                if identifier in defined:
                    notes.append(f"{path.name}: modifier {identifier} defined twice")
                defined.add(identifier)
            elif name == "Row" and element.get("ModifierId"):
                referenced[element.get("ModifierId")] = path
    for identifier, path in referenced.items():
        if identifier not in defined:
            notes.append(
                f"{path.name}: GameModifiers names {identifier}, "
                "which no GameEffects file in this mod defines"
            )
    return notes


# --------------------------------------------------------------------------
# Applying, and seeing what changed
# --------------------------------------------------------------------------


@dataclass
class FileResult:
    path: Path
    group: str
    ok: bool
    statements: int = 0
    error: str = ""
    notes: list[str] = field(default_factory=list)


@dataclass
class TableDiff:
    """What changed in one table. The counts are complete; the lists are a
    sample, so read the counts from the count fields."""

    table: str
    added_count: int
    removed_count: int
    added: list[tuple] = field(default_factory=list)
    removed: list[tuple] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return self.added_count + self.removed_count


@dataclass
class Query:
    """What a SELECT returned."""

    columns: list[str]
    rows: list[tuple]


def run_query(connection, sql: str) -> Query:
    cursor = connection.execute(sql)
    return Query([d[0] for d in cursor.description or []], cursor.fetchall())


def query_dump(sql: str, db: str | Path | None = None) -> Query:
    """Run SQL against the game's own dump, read-only."""
    source = Path(db) if db else default_db()
    if not source or not source.is_file():
        raise FileNotFoundError(
            "No gameplay database to query. The game writes one to "
            "Debug/gameplay-copy.sqlite while a save is loaded (CopyDatabasesToDisk 1)."
        )
    connection = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        return run_query(connection, sql)
    finally:
        connection.close()


@dataclass
class Result:
    db: Path
    age: str | None
    files: list[FileResult]
    diffs: list[TableDiff]
    cleaned: int = 0
    warnings: list[str] = field(default_factory=list)
    query: Query | None = None

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.files)

    def summary(self) -> str:
        failed = [result for result in self.files if not result.ok]
        head = (
            f"{len(self.files)} file(s) applied to {self.db.name}"
            f"{' for ' + self.age if self.age else ''}: "
            f"{'all ok' if not failed else str(len(failed)) + ' FAILED'}"
        )
        rows = sum(diff.changed for diff in self.diffs)
        return f"{head}, {rows} row change(s) across {len(self.diffs)} table(s)"


def _table_names(connection) -> list[str]:
    return [
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        )
    ]


def _rows(connection, table) -> list[tuple]:
    try:
        return list(connection.execute(f'select * from "{table}"'))
    except sqlite3.Error:
        return []


def run(
    mod_path: str | Path,
    age: str | None = None,
    db: str | Path | None = None,
    prefix: str | None = None,
    diff_limit: int = 40,
    query: str | None = None,
) -> Result:
    """Apply one mod's database items to a copy of the game's database. With
    `query`, also run that SQL against the copy once the mod is applied."""
    info = modinfo.load(mod_path)
    source = Path(db) if db else default_db()
    if not source or not Path(source).is_file():
        raise FileNotFoundError(
            "No gameplay database to test against. The game writes one to "
            "Debug/gameplay-copy.sqlite while a save is loaded (CopyDatabasesToDisk 1); "
            "pass --db to use a snapshot instead."
        )
    source = Path(source)

    warnings: list[str] = []
    ambiguous = info.ambiguous_criteria()
    if ambiguous and age:
        warnings.append(
            f"criteria {', '.join(ambiguous)} use AgeAtOrBefore/AgeAtOrAfter, whose "
            "direction is ambiguous; this run reads them literally (the age in use is "
            "at or before the named age). Affected groups: "
            + ", ".join(info.groups_using(ambiguous))
        )

    described = describe(source)
    if described["constructibles"] == 0:
        warnings.append(
            f"{source.name} holds no constructibles, so it was dumped with no age module "
            "loaded: at the main menu, or after quitting. Load a save and let the game "
            "rewrite it, or nothing a mod does to buildings can be measured here."
        )
    if age and described["active_age"] and described["active_age"] != age:
        warnings.append(
            f"asking about {age} but this database was dumped during "
            f"{described['active_age']}, so only that age's buildings exist in it. "
            "Guarded inserts for other ages will correctly do nothing; take a dump "
            "during the age being tested for a full answer."
        )

    workspace = Path(tempfile.mkdtemp(prefix="civ7lab-sql-")) / source.name
    shutil.copy2(source, workspace)
    connection = sqlite3.connect(workspace)
    connection.create_function("Make_Hash", 1, _make_hash)
    connection.execute("PRAGMA foreign_keys=ON")

    cleaned = 0
    if prefix:
        # Delete the mod's rows from a dump taken with it loaded, and count
        # them so the report can say so.
        for table, column in (("TypeTags", "Tag"), ("Tags", "Tag"), ("Types", "Type")):
            try:
                cursor = connection.execute(
                    f'delete from "{table}" where "{column}" like ?', (prefix + "%",)
                )
                cleaned += cursor.rowcount if cursor.rowcount > 0 else 0
            except sqlite3.Error:
                continue
        connection.commit()

    before = {table: _rows(connection, table) for table in _table_names(connection)}

    results: list[FileResult] = []
    effects_files: list[Path] = []
    for group, path in info.items("UpdateDatabase", age):
        if not path.is_file():
            results.append(FileResult(path, group.id, False, error="file not found"))
            continue
        text = path.read_text(errors="replace", encoding="utf-8")
        try:
            if path.suffix.lower() == ".sql":
                statements = len([s for s in re.split(r";\s*\n", text) if s.strip()])
                connection.executescript(text)
                connection.commit()
                results.append(FileResult(path, group.id, True, statements=statements))
            elif "<GameEffects" in text:
                effects_files.append(path)
                results.append(
                    FileResult(path, group.id, True, notes=["GameEffects: structure only"])
                )
            else:
                statements, notes = xml_to_statements(path)
                for sql, values in statements:
                    connection.execute(sql, values)
                connection.commit()
                results.append(
                    FileResult(path, group.id, True, statements=len(statements), notes=notes)
                )
        except (sqlite3.Error, ElementTree.ParseError) as error:
            connection.rollback()
            results.append(FileResult(path, group.id, False, error=str(error)))

    warnings.extend(game_effects_report(effects_files))

    diffs: list[TableDiff] = []
    for table in _table_names(connection):
        after = _rows(connection, table)
        original = before.get(table, [])
        if after == original:
            continue
        before_set, after_set = set(original), set(after)
        added = sorted(after_set - before_set, key=repr)
        removed = sorted(before_set - after_set, key=repr)
        if added or removed:
            sample = max(1, diff_limit)
            diffs.append(
                TableDiff(table, len(added), len(removed), added[:sample], removed[:sample])
            )
    try:
        answer = run_query(connection, query) if query else None
    finally:
        connection.close()
        shutil.rmtree(workspace.parent, ignore_errors=True)

    return Result(
        db=source,
        age=age,
        files=results,
        diffs=diffs,
        cleaned=cleaned,
        warnings=warnings,
        query=answer,
    )
