"""Offline tests for the parts that never touch a running game.

These use a synthetic mod and a synthetic database, so they pass on a machine
with no game installed. The point is the logic that decides what a mod does:
order, age criteria, XML translation, and the row diff that turns "it ran" into
"here is what changed".
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from civ7lab import check, diff, modinfo, sqlcheck

MODINFO = """<?xml version="1.0" encoding="utf-8"?>
<Mod id="testmod" version="3" xmlns="ModInfo">
  <Properties><Name>Test Mod</Name></Properties>
  <ActionCriteria>
    <Criteria id="always"><AlwaysMet/></Criteria>
    <Criteria id="modern-only"><AgeInUse>AGE_MODERN</AgeInUse></Criteria>
  </ActionCriteria>
  <ActionGroups>
    <ActionGroup id="late" scope="game" criteria="always">
      <Properties><LoadOrder>1000</LoadOrder></Properties>
      <Actions><UpdateDatabase><Item>data/late.sql</Item></UpdateDatabase></Actions>
    </ActionGroup>
    <ActionGroup id="early" scope="game" criteria="always">
      <Actions>
        <UpdateDatabase><Item>data/early.xml</Item></UpdateDatabase>
        <UIScripts><Item>ui/one.js</Item></UIScripts>
      </Actions>
    </ActionGroup>
    <ActionGroup id="modern" scope="game" criteria="modern-only">
      <Actions><UpdateDatabase><Item>data/modern.sql</Item></UpdateDatabase></Actions>
    </ActionGroup>
  </ActionGroups>
  <!-- <Item>data/disabled.sql</Item> -->
</Mod>
"""

EARLY_XML = """<?xml version="1.0" encoding="utf-8"?>
<Database>
  <Things>
    <Row ThingType="THING_A" Value="1"/>
    <Row ThingType="THING_B" Value="2"/>
  </Things>
  <Things>
    <Update><Where ThingType="THING_A"/><Set Value="9"/></Update>
    <Delete ThingType="THING_B"/>
  </Things>
</Database>
"""


def build_mod(root: Path) -> Path:
    mod = root / "testmod"
    (mod / "data").mkdir(parents=True)
    (mod / "ui").mkdir()
    (mod / "testmod.modinfo").write_text(MODINFO)
    (mod / "data/early.xml").write_text(EARLY_XML)
    (mod / "data/late.sql").write_text(
        "INSERT INTO Things (ThingType, Value) VALUES ('THING_C', 3);\n")
    (mod / "data/modern.sql").write_text(
        "INSERT INTO Things (ThingType, Value) VALUES ('THING_MODERN', 4);\n")
    (mod / "ui/one.js").write_text("console.error('hi');\n")
    return mod


def build_db(path: Path) -> Path:
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE Things (ThingType TEXT PRIMARY KEY, Value INT)")
    connection.execute("CREATE TABLE Ages (AgeType TEXT, Active INT)")
    connection.executemany("INSERT INTO Ages VALUES (?, ?)",
                           [("AGE_ANTIQUITY", 1), ("AGE_MODERN", 0)])
    connection.execute("CREATE TABLE Constructibles (ConstructibleType TEXT)")
    connection.execute("INSERT INTO Constructibles VALUES ('BUILDING_X')")
    connection.commit()
    connection.close()
    return path


def test_load_order_decides_apply_order():
    with tempfile.TemporaryDirectory() as temporary:
        mod = build_mod(Path(temporary))
        info = modinfo.load(mod)
        names = [path.name for _, path in info.items("UpdateDatabase", "AGE_ANTIQUITY")]
        # early.xml has no LoadOrder (0) so it applies before late.sql (1000),
        # even though its group is written second in the file.
        assert names == ["early.xml", "late.sql"], names


def test_age_criteria_filter_groups():
    with tempfile.TemporaryDirectory() as temporary:
        info = modinfo.load(build_mod(Path(temporary)))
        modern = [path.name for _, path in info.items("UpdateDatabase", "AGE_MODERN")]
        assert "modern.sql" in modern
        antiquity = [path.name for _, path in info.items("UpdateDatabase", "AGE_ANTIQUITY")]
        assert "modern.sql" not in antiquity


def test_commented_out_items_are_reported():
    with tempfile.TemporaryDirectory() as temporary:
        mod = build_mod(Path(temporary))
        assert modinfo.disabled_items(mod) == ["data/disabled.sql"]


def test_xml_rows_updates_and_deletes_are_applied_in_order():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        mod = build_mod(root)
        database = build_db(root / "test.sqlite")
        result = sqlcheck.run(mod, age="AGE_ANTIQUITY", db=database)
        assert result.ok, [f.error for f in result.files if not f.ok]
        tables = {d.table: d for d in result.diffs}
        assert "Things" in tables
        # A was inserted then updated to 9, B inserted then deleted, C inserted.
        added = dict(tables["Things"].added)
        assert added.get("THING_A") == 9, added
        assert added.get("THING_C") == 3, added
        assert "THING_B" not in added, added


def test_a_broken_statement_is_named_not_swallowed():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        mod = build_mod(root)
        (mod / "data/late.sql").write_text("INSERT INTO NoSuchTable VALUES (1);\n")
        result = sqlcheck.run(mod, age="AGE_ANTIQUITY", db=build_db(root / "test.sqlite"))
        assert not result.ok
        failures = [f for f in result.files if not f.ok]
        assert failures[0].path.name == "late.sql"
        assert "no such table" in failures[0].error.lower()


def test_wrong_age_dump_is_flagged():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        mod = build_mod(root)
        result = sqlcheck.run(mod, age="AGE_MODERN", db=build_db(root / "test.sqlite"))
        assert any("dumped during AGE_ANTIQUITY" in warning for warning in result.warnings), \
            result.warnings


def test_diff_matches_list_items_by_identity_not_position():
    before = {"tiles": [{"x": 1, "y": 1, "v": 10}, {"x": 2, "y": 2, "v": 20}]}
    after = {"tiles": [{"x": 2, "y": 2, "v": 20}, {"x": 1, "y": 1, "v": 11}]}
    changes = diff.compare(before, after)
    assert len(changes) == 1, [str(change) for change in changes]
    assert changes[0].path == "tiles[x=1,y=1].v"


def test_spec_paths_select_by_field():
    data = {"tile": {"constructibles": [{"type": "BUILDING_A", "damaged": True}]}}
    assert check.resolve(data, "tile.constructibles[type=BUILDING_A].damaged") is True
    assert check.resolve(data, "tile.constructibles[type=NOPE]") is check.MISSING


def test_a_spec_runs_against_a_snapshot_it_did_not_name():
    """A snapshot keys entries by collector and arguments; a spec names aliases.

    This is a real defect, found the first time the age-turn measurement was
    replayed from disk: every expectation failed as "missing" although the data
    was sitting right there under a different key.
    """
    snapshot = {"turn": 44, "data": {
        'tile({"x": 20, "y": 7})': {"yields": {"YIELD_SCIENCE": 36}},
        'greatworks({"name": "Pataliputra"})': [{"buildings": [{"building": "BUILDING_LIBRARY"}]}],
    }}
    spec = check.Spec(name="x", collect=[
        {"as": "tile", "collector": "tile", "args": {"x": 20, "y": 7}},
        {"as": "works", "collector": "greatworks", "args": {"name": "Pataliputra"}}],
        expect=[check.Expectation("tile.yields.YIELD_SCIENCE", ">=", 30),
                check.Expectation("works[0].buildings[building=BUILDING_LIBRARY]", "present")])
    data = check.bind(spec, check.from_snapshot(snapshot))
    assert check.evaluate(spec, data).passed


def test_missing_path_fails_the_expectation_instead_of_raising():
    result = check.evaluate(
        check.Spec(name="x", expect=[check.Expectation("a.b.c", ">", 1)]), {"a": {}})
    assert not result.passed


if __name__ == "__main__":
    failures = 0
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            try:
                function()
                print(f"ok   {name}")
            except Exception as error:
                failures += 1
                print(f"FAIL {name}: {type(error).__name__}: {error}")
    raise SystemExit(1 if failures else 0)
