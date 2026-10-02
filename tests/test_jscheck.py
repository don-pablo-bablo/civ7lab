"""`civ7lab jscheck` on a small mod with one of each problem."""

import pytest

from civ7lab import jscheck

MODINFO = """<?xml version="1.0" encoding="utf-8"?>
<Mod id="checked" version="1" xmlns="ModInfo">
  <ActionGroups>
    <ActionGroup id="ui" scope="game" criteria="always">
      <Actions><UIScripts>
        <Item>ui/panel.js</Item>
        <Item>ui/broken.js</Item>
      </UIScripts></Actions>
    </ActionGroup>
  </ActionGroups>
</Mod>
"""

PANEL = """\
import { helper } from "./helper.js";
import { Component } from "../../core/ui/component.js";
const PANEL_BUILD = "7";
console.log("drawn");
"""


@pytest.fixture
def reports(tmp_path):
    (tmp_path / "ui").mkdir()
    (tmp_path / "checked.modinfo").write_text(MODINFO, encoding="utf-8")
    (tmp_path / "ui/panel.js").write_text(PANEL, encoding="utf-8")
    (tmp_path / "ui/broken.js").write_text(
        "function draw() {\n  return [1, 2;\n}\n", encoding="utf-8"
    )
    (tmp_path / "ui/helper.js").write_text("export const helper = 1;\n", encoding="utf-8")
    return {report.path.name: report for report in jscheck.check(tmp_path)}


def test_an_unserved_import_is_reported_and_the_games_own_is_not(reports):
    warnings = reports["panel.js"].warnings
    assert any("imports ./helper.js" in w for w in warnings), warnings
    assert not any("component.js" in w for w in warnings), warnings


def test_console_log_and_the_stamp(reports):
    assert any("console.log" in w for w in reports["panel.js"].warnings)
    assert reports["panel.js"].build_stamp == "7"


def test_a_script_no_action_group_lists_never_loads(reports):
    assert any("never loads" in w for w in reports["helper.js"].warnings)


def test_a_syntax_error_is_found_with_its_line(reports):
    assert reports["broken.js"].parsed, "tree_sitter is missing: run uv sync"
    assert not reports["broken.js"].ok
    assert reports["broken.js"].syntax_errors[0][0] == 2
    assert reports["panel.js"].ok
