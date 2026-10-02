"""`civ7lab text` on a small mod with one missing key."""

import sqlite3

import pytest

from civ7lab import textcheck

MODINFO = """<?xml version="1.0" encoding="utf-8"?>
<Mod id="texty" version="1" xmlns="ModInfo">
  <Properties><Name>LOC_TEXTY_NAME</Name></Properties>
  <Dependencies><Mod id="base-standard" title="LOC_MODULE_BASE_STANDARD_NAME"/></Dependencies>
  <ActionGroups>
    <ActionGroup id="all" scope="game" criteria="always">
      <Actions>
        <UpdateText><Item>text/en_us.xml</Item></UpdateText>
        <UpdateDatabase><Item>data/rules.sql</Item></UpdateDatabase>
      </Actions>
    </ActionGroup>
  </ActionGroups>
</Mod>
"""

TEXT = """<?xml version="1.0" encoding="utf-8"?>
<Database>
  <EnglishText>
    <Row Tag="LOC_TEXTY_NAME"><Text>Texty</Text></Row>
    <Row Tag="LOC_TEXTY_unused_HINT"><Text>Never shown</Text></Row>
  </EnglishText>
</Database>
"""


@pytest.fixture
def mod(tmp_path):
    root = tmp_path / "texty"
    for folder in ("text", "data", "ui"):
        (root / folder).mkdir(parents=True)
    (root / "texty.modinfo").write_text(MODINFO, encoding="utf-8")
    (root / "text/en_us.xml").write_text(TEXT, encoding="utf-8")
    (root / "data/rules.sql").write_text(
        "UPDATE Units SET Name = 'LOC_UNIT_SCOUT_NAME';\n", encoding="utf-8"
    )
    (root / "ui/panel.js").write_text(
        'Locale.compose("LOC_TEXTY_MISING");\nLocale.compose("LOC_UNIT_" + name);\n',
        encoding="utf-8",
    )
    return root


@pytest.fixture
def game_text(tmp_path):
    db = tmp_path / "localization-copy.sqlite"
    connection = sqlite3.connect(db)
    connection.execute("CREATE TABLE LocalizedText (Language TEXT, Tag TEXT, Text TEXT)")
    connection.executemany(
        "INSERT INTO LocalizedText VALUES ('en_US', ?, '')",
        [("LOC_UNIT_SCOUT_NAME",), ("LOC_TEXTY_MISING",)],
    )
    connection.commit()
    connection.close()
    return db


def test_a_typo_is_found_and_the_rest_is_accounted_for(mod, tmp_path):
    report = textcheck.check(mod, db=tmp_path / "none.sqlite")
    assert report.game is None
    assert report.used["LOC_TEXTY_MISING"] == ["ui/panel.js"]
    assert "LOC_UNIT_" not in report.used, "a key built in code cannot be checked"
    assert "LOC_MODULE_BASE_STANDARD_NAME" not in report.used
    assert report.unused == ["LOC_TEXTY_unused_HINT"]


def test_the_games_keys_count_as_defined(mod, game_text):
    report = textcheck.check(mod, db=game_text, prefix="LOC_TEXTY")
    assert report.undefined == ["LOC_TEXTY_MISING"], "a stale key in the dump was trusted"
    assert not report.ok
    assert textcheck.check(mod, db=game_text).undefined == []
