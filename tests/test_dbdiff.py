"""`civ7lab dbdiff` on two small databases."""

import sqlite3

from civ7lab import dbdiff


def database(path, statements):
    connection = sqlite3.connect(path)
    for statement in statements:
        connection.execute(statement)
    connection.commit()
    connection.close()
    return path


BEFORE = [
    "CREATE TABLE Units (UnitType TEXT PRIMARY KEY, Moves INT, Sight INT)",
    "INSERT INTO Units VALUES ('SCOUT', 2, 2), ('SETTLER', 2, 1), ('SANDBOX', 10, 2)",
    "CREATE TABLE Tags (Type TEXT, Tag TEXT)",
    "INSERT INTO Tags VALUES ('SCOUT', 'RECON')",
    "CREATE TABLE Retired (Id TEXT)",
]
AFTER = [
    "CREATE TABLE Units (UnitType TEXT PRIMARY KEY, Cost INT, Moves INT, Sight INT)",
    "INSERT INTO Units VALUES ('SCOUT', 20, 3, 2), ('SETTLER', 50, 2, 1), ('WARRIOR', 30, 2, 2)",
    "CREATE TABLE Tags (Type TEXT, Tag TEXT)",
    "INSERT INTO Tags VALUES ('SCOUT', 'RECON'), ('WARRIOR', 'MELEE')",
    "CREATE TABLE Added (Id TEXT)",
]


def changes(tmp_path):
    before = database(tmp_path / "before.sqlite", BEFORE)
    after = database(tmp_path / "after.sqlite", AFTER)
    return {change.table: change for change in dbdiff.compare(before, after)}


def test_rows_are_paired_by_key_and_compared_by_column_name(tmp_path):
    units = changes(tmp_path)["Units"]
    assert units.columns_added == ["Cost"]
    assert (units.changed, units.added, units.removed) == (1, 1, 1)
    assert units.lines == ["~ SCOUT: Moves 2 -> 3", "+ WARRIOR", "- SANDBOX"]


def test_a_table_with_no_key_lists_whole_rows(tmp_path):
    assert changes(tmp_path)["Tags"].lines == ["+ ('WARRIOR', 'MELEE')"]


def test_whole_tables_added_and_removed(tmp_path):
    found = changes(tmp_path)
    assert found["Added"].note == "new table" and found["Retired"].note == "table removed"


def test_identical_databases_have_no_changes(tmp_path):
    before = database(tmp_path / "a.sqlite", BEFORE)
    assert dbdiff.compare(before, before) == []
