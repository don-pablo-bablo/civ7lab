"""`civ7lab live` putting the probe into a game, against the real probe code.

The game's UI is stood in for by Node. Each evaluate replays everything
evaluated before it into a fresh context, which gives one persistent UI as far
as the probe can tell.
"""

import json
import re

from conftest import PROBE_UI

from civ7lab import live


class NodeGame:
    """The parts of cdp.Session that live.Probe uses, backed by Node."""

    def __init__(self, js, loaded=(), scripts=()):
        self.js = js
        self.loaded = list(loaded)  # probe files the game loaded at start
        self.history = list(scripts)  # everything evaluated since
        self.injected = 0

    def evaluate(self, expression, await_promise=True):
        if "installCiv7Lab" in expression or "registerCollectors" in expression:
            self.injected += 1
        result = self.js(expression, self.loaded, self.history)["result"]
        self.history.append(expression)
        return result

    def call(self, function, *args):
        return self.evaluate(f"({function})({', '.join(json.dumps(a) for a in args)})")


def test_a_game_without_the_probe_gets_it_once(js):
    game = NodeGame(js)
    probe = live.Probe(game)
    assert probe.ensure() == f"probe {live.probe_id()} injected"
    assert game.injected == len(live.PROBE_FILES)
    assert "already present" in probe.ensure()
    assert game.injected == len(live.PROBE_FILES)
    assert "tile" in probe.collectors()


def test_a_game_that_loaded_the_current_files_is_left_alone(js):
    game = NodeGame(js, loaded=["lab-core.js", "lab-collect.js"])
    assert "already present" in live.Probe(game).ensure()
    assert game.injected == 0


def test_an_older_probe_is_replaced_and_keeps_what_was_registered(js):
    older = re.sub(
        r'var BUILD = "[^"]*";',
        'var BUILD = "probe-older";',
        (PROBE_UI / "lab-core.js").read_text(encoding="utf-8"),
    )
    mine = 'C7Lab.register("mine", function () { return 42; }, "added by hand")'
    game = NodeGame(js, scripts=[older, mine])
    probe = live.Probe(game)
    assert "injected" in probe.ensure()
    assert probe.collect("mine") == 42
    assert "already present" in probe.ensure()


def test_a_snapshot_is_stamped_with_the_turn(js):
    game = NodeGame(js, scripts=["var Game = { turn: 44, age: 0 };"])
    probe = live.Probe(game)
    probe.ensure()
    taken = probe.snapshot([("game", {})])
    assert taken["turn"] == 44 and taken["probe"] == live.probe_id()
    assert taken["data"]["game"]["turn"] == 44


def test_a_script_file_gives_the_value_of_its_last_statement(js, tmp_path):
    script = tmp_path / "count.js"
    script.write_text(
        "var names = ['a', 'b'];\nnames.push('c');\nnames.join('-');\n", encoding="utf-8"
    )
    game = NodeGame(js)
    assert live.Probe(game).evaluate(script.read_text(encoding="utf-8")) == "a-b-c"


# The game's Autoplay API, as far as live.Probe.autoplay uses it.
AUTOPLAY = """
var Autoplay = {
  isActive: false,
  calls: [],
  setTurns: function (n) { this.calls.push("turns " + n); },
  setReturnAsPlayer: function (p) { this.calls.push("return " + p); },
  setObserveAsPlayer: function (p) { this.calls.push("observe " + p); },
  setActive: function (on) { this.isActive = on; this.calls.push("active " + on); }
};
"""


def test_autoplay_makes_the_calls_the_games_automation_makes(js):
    game = NodeGame(js, scripts=[AUTOPLAY])
    probe = live.Probe(game)
    assert probe.autoplay(20) is True
    assert game.evaluate("Autoplay.calls") == [
        "turns 20",
        "return 0",
        "observe 0",
        "active true",
    ]
    assert probe.autoplay(None) is False
