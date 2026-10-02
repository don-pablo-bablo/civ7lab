"""The command line: every documented command still parses.

Other mods' docs quote these command lines, so a change that breaks one breaks
their instructions.
"""

import shlex
import subprocess
import sys

from civ7lab import commands

# Command lines quoted in this repo's docs or in other mods' docs.
QUOTED = [
    "doctor --json",
    "options --live",
    "options --set UILogLevel=3 --dry-run",
    "mod list",
    "mod install",
    "mod install mod/some-mod --force",
    "mod uninstall some-mod",
    "sql path/to/mod --age AGE_ANTIQUITY --prefix DSB --rows 5",
    "modinfo path/to/mod --age AGE_EXPLORATION",
    "jscheck path/to/mod",
    "live attach",
    "live targets",
    """live collect tile --args '{"x":20,"y":7}'""",
    """live snapshot --collect game 'city:{"all":true}' --out before.json""",
    "live members --expression 'Players.get(0)'",
    "live eval --expression 'Game.turn'",
    "live eval 'Game.turn'",
    "live eval --file check-units.js",
    "live watch --seconds 5",
    "live autoplay 20",
    "live autoplay --stop",
    "ui watch path/to/mod/ui --after 'x()'",
    "ui push path/to/mod/ui",
    "run --save latest --inspector",
    "run --turns 40 --seed 12345 --quit --plan plans/age-turn.json",
    "check specs/example-tile-yield.json --snapshot before.json",
    "diff before.json after.json --path data.game",
    "mock serve --root path/to/mod --renderer ui/panel.js --export render",
    "mock fixtures --kind byt-fixture --latest-by cityName,loc.x,loc.y",
    'logs marker --marker "[BYT]"',
    "logs snapshot --out keep",
    "logs errors",
    "logs records --json",
    "logs stamps",
    "workshop tags 1234567890",
    'workshop tags 1234567890 "Game Setup" "Gameplay Tweaks" --dry-run',
]


def test_quoted_command_lines_parse():
    parser = commands.build_parser()
    for line in QUOTED:
        args = parser.parse_args(shlex.split(line))
        assert callable(args.func), line


def test_every_command_is_in_the_overview():
    parser = commands.build_parser()  # asserts GROUPS matches the parsers
    overview = commands.overview()
    for name in parser._subparsers._group_actions[0].choices:
        assert f"  {name} " in overview, name


def test_no_arguments_prints_the_overview(capsys):
    assert commands.main([]) == 0
    assert "Without the game" in capsys.readouterr().out


def test_names_that_are_not_ascii_print_into_a_pipe(tmp_path):
    # Windows writes its own code page into a pipe unless told otherwise, and
    # has no character for the ō in Knōssós.
    mod = tmp_path / "knossos"
    mod.mkdir()
    (mod / "knossos.modinfo").write_text(
        '<Mod id="knossos" version="1" xmlns="ModInfo">'
        "<Properties><Name>Knōssós</Name></Properties></Mod>",
        encoding="utf-8",
    )
    done = subprocess.run(
        [sys.executable, "-m", "civ7lab", "modinfo", str(mod)], capture_output=True
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    assert "Knōssós" in done.stdout.decode("utf-8")
