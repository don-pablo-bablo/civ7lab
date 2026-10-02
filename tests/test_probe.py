"""The probe's JavaScript, run in Node.

The probe prints records that the Python side reads back, so the most useful
test runs the real lab-core.js and feeds what it printed to the real parser.
The runtime and the plan need no engine. Collectors that read the game are
confirmed in game instead; see CONTRIBUTING.md.
"""

import json
import re
import shutil

from conftest import PROBE_UI

from civ7lab import live, records


def parsed(lines):
    report = records.parse_lines(lines)
    assert report.ok, (report.errors, report.missing_seq)
    return report


def test_build_stamp_matches_the_files():
    wanted = live.probe_id()
    found = re.search(
        r'var BUILD = "([^"]*)";', (PROBE_UI / "lab-core.js").read_text(encoding="utf-8")
    )
    assert found and found.group(1) == wanted, (
        f"the probe's files changed. In mod/civ7lab-probe/ui/lab-core.js set:\n"
        f'  var BUILD = "{wanted}";'
    )


def test_the_stamp_ignores_its_own_line_only(tmp_path):
    for name in live.STAMPED_FILES:
        shutil.copy(PROBE_UI / name, tmp_path / name)
    before = live.probe_id(tmp_path)
    core = tmp_path / "lab-core.js"
    core.write_text(
        re.sub(
            r'var BUILD = "[^"]*";', 'var BUILD = "anything";', core.read_text(encoding="utf-8")
        ),
        encoding="utf-8",
    )
    assert live.probe_id(tmp_path) == before
    collect = tmp_path / "lab-collect.js"
    collect.write_text(collect.read_text(encoding="utf-8") + "\n// an edit\n", encoding="utf-8")
    assert live.probe_id(tmp_path) != before


def test_load_prints_the_build_stamp(js):
    out = js("C7Lab.build", ["lab-core.js"])
    assert f"civ7lab:build probe {out['result']}" in out["lines"][0], out["lines"]


def test_short_and_long_records_parse_in_python(js):
    body = """
      C7Lab.emit("small", { a: 1 });
      C7Lab.emit("big", { text: "x".repeat(3000), list: [1, 2, 3] });
      true"""
    out = js(body, ["lab-core.js"])
    assert any(line.startswith(records.CHUNK_MARKER) for line in out["lines"]), (
        "a 3000 character record should have been split"
    )
    report = parsed(out["lines"])
    by_kind = {record.kind: record.data for record in report.records}
    assert by_kind["small"] == {"a": 1}
    assert by_kind["big"]["text"] == "x" * 3000 and by_kind["big"]["list"] == [1, 2, 3]


def test_a_collector_that_throws_returns_the_error_as_data(js):
    body = """
      C7Lab.register("broken", function () { throw new Error("no such thing"); });
      [C7Lab.collect("broken", {}), C7Lab.collect("missing", {})]"""
    broken, missing = js(body, ["lab-core.js"])["result"]
    assert "no such thing" in broken["error"] and broken["collector"] == "broken"
    assert missing["error"] == "no collector named missing"


def test_dump_logs_what_collect_returns(js):
    body = """
      C7Lab.register("answer", function (args) { return { doubled: args.n * 2 }; });
      C7Lab.dump("answer", { n: 21 })"""
    out = js(body, ["lab-core.js"])
    assert out["result"] == {"doubled": 42}
    records_ = parsed(out["lines"]).of_kind("answer")
    assert records_[0].data == {"doubled": 42} and records_[0].meta["args"] == {"n": 21}


def test_loading_again_keeps_collectors_and_sequence(js):
    body = """
      C7Lab.register("mine", function () { return 1; });
      C7Lab.emit("before", 1);
      load("lab-core.js");
      C7Lab.emit("after", 2);
      Object.keys(C7Lab.list())"""
    out = js(body, ["lab-core.js"])
    assert "mine" in out["result"]
    parsed(out["lines"])  # no gap in the sequence across the reload


def test_members_walks_the_prototype_chain(js):
    body = """
      function Unit() { this.id = 3; }
      Unit.prototype.moves = function (a, b) { return a + b; };
      C7Lab.members(new Unit()).members"""
    members = js(body, ["lab-core.js"])["result"]
    assert "id: number = 3" in members and "moves: function/2" in members, members


PLAN_ENGINE = """
  var handlers = {};
  var engine = { on: function (name, fn) { handlers[name] = fn; } };
  var Game = { turn: 0 };
  var GameContext = { localPlayerID: 0 };
"""


def run_plan(js, plan, turns):
    """Load the probe with a recording plan, fire TurnBegin for each turn,
    and return which collector fired on which turn."""
    body = (
        PLAN_ENGINE.replace("\n", " ")
        + f"""
      load("lab-core.js");
      C7Lab.plan = {json.dumps(plan)};
      C7Lab.register("probe", function () {{ return Game.turn; }});
      load("lab-hooks.js");
      {json.dumps(list(turns))}.forEach(function (t) {{
        Game.turn = t;
        handlers.TurnBegin({{ turn: t }});
      }});
      handlers.GameAgeEnded();
      true"""
    )
    out = js(body)
    return [(r.kind, r.data) for r in parsed(out["lines"]).records if r.kind != "log"]


def test_plan_fires_every_n_turns_within_its_range(js):
    fired = run_plan(
        js, {"onTurn": [{"collector": "probe", "every": 5, "from": 10, "to": 20}]}, range(1, 26)
    )
    assert [turn for kind, turn in fired if kind == "probe"] == [10, 15, 20], fired


def test_age_end_always_records_the_game(js):
    fired = run_plan(js, {"onAgeEnd": [{"collector": "probe"}]}, [])
    assert [kind for kind, _ in fired] == ["game", "probe"], fired


def test_city_select_passes_the_selected_city_unless_args_say_otherwise(js):
    body = """
      var handlers = {};
      var engine = { on: function (name, fn) { handlers[name] = fn; } };
      var Game = { turn: 3 };
      var GameContext = { localPlayerID: 0 };
      var Cities = { get: function () { return { name: "LOC_CITY_ROME" }; } };
      var Locale = { compose: function (key) { return key === "LOC_CITY_ROME" ? "Rome" : key; } };
      load("lab-core.js");
      C7Lab.plan = { onCitySelect: [
        { collector: "a" },
        { collector: "b", args: { name: "Ostia" } }
      ] };
      C7Lab.register("a", function (args) { return args.name; });
      C7Lab.register("b", function (args) { return args.name; });
      load("lab-hooks.js");
      handlers.CitySelectionChanged({ selected: true, cityID: { owner: 0, id: 1 } });
      handlers.CitySelectionChanged({ selected: true, cityID: { owner: 1, id: 2 } });
      true"""
    fired = [(r.kind, r.data) for r in parsed(js(body)["lines"]).records if r.kind != "log"]
    assert fired == [("a", "Rome"), ("b", "Ostia")], fired
