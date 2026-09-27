"""Apply a mod's database changes offline, and say exactly what they did.

This is the cheapest test in the toolkit and the one that should run after
every data edit. The game's own database is dumped to disk as
`Debug/gameplay-copy.sqlite`; SQLite is SQLite, so a mod's SQL and XML can be
applied to a copy of that dump right here, in under a second, with foreign keys
on. What comes back is not just "it ran" but which rows appeared, vanished or
changed.

Three traps are built into the harness because each of them has cost this
project a playthrough:

* **`INSERT OR IGNORE` does not cover foreign keys.** SQLite applies ON
  CONFLICT to UNIQUE, NOT NULL, CHECK and PRIMARY KEY only, so an insert
  referring to a row that this age does not load fails outright. It fails here
  too, in a second, instead of in Database.log after a launch.
* **The dump is taken from a running game that had the mod loaded**, so it
  already contains the mod's own output. Applying the mod to it again measures
  nothing. `--prefix` strips those rows first and reports how many it removed,
  so a dirty baseline is stated rather than assumed.
* **Order and age decide everything.** Files are applied in the order the
  modinfo gives them for the age asked about, so a delete that undoes an
  earlier insert shows up as a missing row in the diff.

What it cannot do: GameEffects XML is interpreted by the engine's effects
system rather than being plain table data, so those files are validated for
structure and cross-checked for unresolved modifier ids, not executed.
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
    """A stand-in for the engine's Make_Hash.

    The real function is Firaxis' own; nothing offline needs its exact values,
    only that the same text hashes to the same number within a run, so that
    rows keyed by hash still join to each other.
    """
    if value is None:
        return 0
    text = str(value).encode("utf-8")
    # FNV-1a, 32 bit, signed the way the database stores it.
    hashed = 0x811C9DC5
    for byte in text:
        hashed = ((hashed ^ byte) * 0x01000193) & 0xFFFFFFFF
    return hashed - 0x100000000 if hashed >= 0x80000000 else hashed


def default_db() -> Path | None:
    """The game's own dump, which is what a mod is really applied to.

    Only as good as the moment it was taken: written at the main menu it holds
    no age module at all, and `describe()` says so rather than letting a run
    report that every insert was skipped.
    """
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
        # Which age this dump was taken in. It decides which buildings exist
        # at all, and therefore which of a mod's guarded inserts can land, so
        # applying an Exploration rule set to an Antiquity dump measures very
        # little and should say so.
        active = None
        try:
            row = connection.execute(
                "select AgeType from Ages where Active = 1").fetchone()
            active = row[0] if row else None
        except sqlite3.Error:
            pass
        return {"path": str(db_path),
                "active_age": active,
                "constructibles": count("Constructibles"),
                "types": count("Types"),
                "tables": count("sqlite_master")}
    finally:
        connection.close()


# --------------------------------------------------------------------------
# XML that is really table data
# --------------------------------------------------------------------------

def _localname(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def xml_to_statements(path: Path) -> tuple[list[tuple[str, tuple]], list[str]]:
    """Translate a <Database> document into statements.

    Covers the shapes Firaxis' own data uses: a table element holding <Row>,
    <Replace>, <Update><Where/><Set/></Update> and <Delete>. Anything else is
    returned as a note rather than skipped in silence.
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
                statements.append((f'{verb} INTO "{table_name}" ({quoted}) VALUES ({placeholders})',
                                   tuple(element.attrib[column] for column in columns)))
            elif kind == "Delete":
                where = " AND ".join(f'"{column}" = ?' for column in element.attrib)
                clause = f" WHERE {where}" if where else ""
                statements.append((f'DELETE FROM "{table_name}"{clause}',
                                   tuple(element.attrib.values())))
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
                statements.append((f'UPDATE "{table_name}" SET {assignments}{clause}',
                                   tuple(values)))
            else:
                notes.append(f"{path.name}: unhandled <{kind}> in {table_name}")
    return statements, notes


def game_effects_report(paths_in: list[Path]) -> list[str]:
    """Structural checks for GameEffects files, which cannot be executed here.

    The check that earns its place is the last one: a <GameModifiers> row
    naming a modifier that no file defines is a typo that costs nothing to
    make, does nothing in play, and reports no error anywhere.
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
            notes.append(f"{path.name}: GameModifiers names {identifier}, "
                         "which no GameEffects file in this mod defines")
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
    """What changed in one table.

    The counts are the measurement; the lists are a sample of it. Keeping them
    apart matters: an early version limited the lists and read the counts off
    them, so asking for no sample rows reported no changes at all.
    """
    table: str
    added_count: int
    removed_count: int
    added: list[tuple] = field(default_factory=list)
    removed: list[tuple] = field(default_factory=list)

    @property
    def changed(self) -> int:
        return self.added_count + self.removed_count


@dataclass
class Result:
    db: Path
    age: str | None
    files: list[FileResult]
    diffs: list[TableDiff]
    cleaned: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.files)

    def summary(self) -> str:
        failed = [result for result in self.files if not result.ok]
        head = (f"{len(self.files)} file(s) applied to {self.db.name}"
                f"{' for ' + self.age if self.age else ''}: "
                f"{'all ok' if not failed else str(len(failed)) + ' FAILED'}")
        rows = sum(diff.changed for diff in self.diffs)
        return f"{head}, {rows} row change(s) across {len(self.diffs)} table(s)"


def _table_names(connection) -> list[str]:
    return [row[0] for row in connection.execute(
        "select name from sqlite_master where type='table' and name not like 'sqlite_%'")]


def _rows(connection, table) -> list[tuple]:
    try:
        return list(connection.execute(f'select * from "{table}"'))
    except sqlite3.Error:
        return []


def run(mod_path: str | Path, age: str | None = None, db: str | Path | None = None,
        prefix: str | None = None, pre_sql: str | None = None,
        diff_limit: int = 40) -> Result:
    """Apply one mod's database items to a copy of the game's database."""
    info = modinfo.load(mod_path)
    source = Path(db) if db else default_db()
    if not source or not Path(source).is_file():
        raise FileNotFoundError(
            "No gameplay database to test against. The game writes one to "
            "Debug/gameplay-copy.sqlite while a save is loaded (CopyDatabasesToDisk 1); "
            "pass --db to use a snapshot instead.")
    source = Path(source)

    warnings: list[str] = []
    ambiguous = info.ambiguous_criteria()
    if ambiguous and age:
        warnings.append(
            f"criteria {', '.join(ambiguous)} use AgeAtOrBefore/AgeAtOrAfter, whose "
            "direction is ambiguous; this run reads them literally (the age in use is "
            f"at or before the named age). Affected groups: {', '.join(info.groups_using(ambiguous))}")

    described = describe(source)
    if described["constructibles"] == 0:
        warnings.append(
            f"{source.name} holds no constructibles, so it was dumped with no age module "
            "loaded: at the main menu, or after quitting. Load a save and let the game "
            "rewrite it, or nothing a mod does to buildings can be measured here.")
    if age and described["active_age"] and described["active_age"] != age:
        warnings.append(
            f"asking about {age} but this database was dumped during "
            f"{described['active_age']}, so only that age's buildings exist in it. "
            "Guarded inserts for other ages will correctly do nothing; take a dump "
            "during the age being tested for a full answer.")

    workspace = Path(tempfile.mkdtemp(prefix="civ7lab-sql-")) / source.name
    shutil.copy2(source, workspace)
    connection = sqlite3.connect(workspace)
    connection.create_function("Make_Hash", 1, _make_hash)
    connection.execute("PRAGMA foreign_keys=ON")

    cleaned = 0
    if prefix:
        # The dump carries the mod's own previous output. Strip the rows that
        # are certainly ours, since tag tables are where a mod's identity
        # lives, and count them so the baseline is stated.
        for table, column in (("TypeTags", "Tag"), ("Tags", "Tag"), ("Types", "Type")):
            try:
                cursor = connection.execute(
                    f'delete from "{table}" where "{column}" like ?', (prefix + "%",))
                cleaned += cursor.rowcount if cursor.rowcount > 0 else 0
            except sqlite3.Error:
                continue
        connection.commit()
    if pre_sql:
        connection.executescript(pre_sql)
        connection.commit()

    before = {table: _rows(connection, table) for table in _table_names(connection)}

    results: list[FileResult] = []
    effects_files: list[Path] = []
    for group, path in info.items("UpdateDatabase", age):
        if not path.is_file():
            results.append(FileResult(path, group.id, False, error="file not found"))
            continue
        text = path.read_text(errors="replace")
        try:
            if path.suffix.lower() == ".sql":
                statements = len([s for s in re.split(r";\s*\n", text) if s.strip()])
                connection.executescript(text)
                connection.commit()
                results.append(FileResult(path, group.id, True, statements=statements))
            elif "<GameEffects" in text:
                effects_files.append(path)
                results.append(FileResult(path, group.id, True, notes=["GameEffects: structure only"]))
            else:
                statements, notes = xml_to_statements(path)
                for sql, values in statements:
                    connection.execute(sql, values)
                connection.commit()
                results.append(FileResult(path, group.id, True,
                                          statements=len(statements), notes=notes))
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
            diffs.append(TableDiff(table, len(added), len(removed),
                                   added[:sample], removed[:sample]))
    connection.close()
    shutil.rmtree(workspace.parent, ignore_errors=True)

    return Result(db=source, age=age, files=results, diffs=diffs,
                  cleaned=cleaned, warnings=warnings)
