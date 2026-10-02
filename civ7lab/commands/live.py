"""live, check and diff: asking a running game, and comparing the answers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .. import cdp, check, diff, live, records
from ._common import actions, command, print_json


def cmd_live(args) -> int:
    if args.action == "targets":
        port = args.port or cdp.find_port()
        if not port:
            print(
                "nothing listening. Is the game running, and is UIDebugger on?\n"
                "  civ7lab options --live   (then restart the game)"
            )
            return 1
        for target in cdp.targets("127.0.0.1", port):
            print(target)
        return 0

    probe = live.attach(port=args.port, match=args.target, install=not args.no_install)
    if args.action == "attach":
        print(f"attached: {probe.session.ws_url}")
        print(f"probe build {probe.build}")
        print("collectors:")
        for name, description in probe.collectors().items():
            print(f"  {name:12} {description}")
        return 0
    if args.action in ("eval", "members"):
        expression = args.expression or args.code
        if getattr(args, "file", None):
            expression = Path(args.file).read_text(encoding="utf-8")
        if not expression:
            print(f"live {args.action} needs a JavaScript expression")
            return 1
        run = probe.evaluate if args.action == "eval" else probe.members
        print_json(run(expression))
        return 0
    if args.action == "collect":
        arguments = json.loads(args.args) if args.args else {}
        value = (
            probe.dump(args.collector, arguments)
            if args.also_log
            else probe.collect(args.collector, arguments)
        )
        if args.out:
            Path(args.out).write_text(json.dumps(value, indent=2, default=str), encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print_json(value)
        return 0
    if args.action == "snapshot":
        spec = []
        for item in args.collect or ["game"]:
            name, _, arguments = item.partition(":")
            spec.append((name, json.loads(arguments) if arguments else {}))
        taken = probe.snapshot(spec)
        if args.out:
            Path(args.out).write_text(json.dumps(taken, indent=2, default=str), encoding="utf-8")
            print(f"wrote {args.out}  (turn {taken.get('turn')}, {taken.get('age')})")
        else:
            print_json(taken)
        return 0
    if args.action == "autoplay":
        if args.stop == (args.turns is not None):
            print("give a number of turns, or --stop")
            return 1
        if args.stop:
            # Measured: the game finishes the turn in progress, then stops.
            probe.autoplay(None)
            print("autoplay stops at the end of the current turn")
            return 0
        if probe.autoplay(args.turns, observe=args.observe):
            print(f"autoplay on for {args.turns} turn(s)")
            return 0
        print("autoplay did not start")
        return 1
    if args.action == "watch":
        marker = "" if args.all else records.MARKER
        for line in probe.watch(seconds=args.seconds, marker=marker):
            print(f"[{line['level']}] {line['text']}", flush=True)
        return 0
    return 1


def cmd_check(args) -> int:
    spec = check.Spec.load(args.spec)
    if args.snapshot:
        data = check.bind(
            spec, check.from_snapshot(json.loads(Path(args.snapshot).read_text(encoding="utf-8")))
        )
    else:
        probe = live.attach(port=args.port)
        data = check.gather(spec, probe)
    result = check.evaluate(spec, data)
    print(result.report())
    if args.out:
        Path(args.out).write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return 0 if result.passed else 1


def cmd_diff(args) -> int:
    before = json.loads(Path(args.before).read_text(encoding="utf-8"))
    after = json.loads(Path(args.after).read_text(encoding="utf-8"))
    if args.path:
        before = check.resolve(before, args.path)
        after = check.resolve(after, args.path)
    changes = diff.compare(before, after)
    if args.json:
        print_json(
            [
                {
                    "path": change.path,
                    "kind": change.kind,
                    "before": change.before,
                    "after": change.after,
                }
                for change in changes
            ]
        )
        return 0
    print(diff.summarise(changes, limit=args.limit))
    return 0


def register(sub) -> None:
    # Options every live action takes, placed after the action name.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--port", type=int, help="inspector port (default: found by scanning)")
    common.add_argument("--target", help="pick the UI context by substring of its url")
    common.add_argument(
        "--no-install",
        action="store_true",
        help="do not inject the probe; use what is already there",
    )

    parser = command(
        sub,
        "live",
        doc="live.md",
        examples="""
Needs the game running with UIDebugger on (civ7lab options --live). The probe
is pushed into the game on attach, so it need not be installed as a mod.

examples:
  civ7lab live attach                                  check the connection
  civ7lab live collect tile --args '{"x":20,"y":7}'    one tile's yields and buildings
  civ7lab live collect city --args '{"name":"Rome"}' --out rome.json
  civ7lab live eval 'Game.turn'                        any JavaScript, result as JSON
  civ7lab live eval --file check-units.js              a longer script
  civ7lab live members 'Players.get(0)'                what an engine object has on it
  civ7lab live watch --seconds 60                      the probe's records as they print
  civ7lab live watch --all                             every console line, even console.log
  civ7lab live autoplay 20                             the AI plays 20 turns of the open game
  civ7lab live snapshot --collect game 'city:{"all":true}' --out before.json""",
    )
    parser.set_defaults(func=cmd_live)
    act = actions(parser)

    act.add_parser(
        "targets", parents=[common], help="list the game's UI contexts, without attaching"
    )
    act.add_parser(
        "attach",
        parents=[common],
        help="connect, inject the probe and list its collectors with their arguments",
    )

    collect = act.add_parser(
        "collect", parents=[common], help="run one collector and print what it returns"
    )
    collect.add_argument(
        "collector", help="game, tile, tiles, cities, city, yieldtree, greatworks, tags or def"
    )
    collect.add_argument(
        "--args", help='the collector\'s arguments as JSON, e.g. \'{"x":20,"y":7}\''
    )
    collect.add_argument("--out", help="write the result to this file")
    collect.add_argument(
        "--also-log",
        action="store_true",
        help="also print it to UI.log as a record, so it outlives the game",
    )

    snapshot = act.add_parser(
        "snapshot",
        parents=[common],
        help="several collectors in one file, stamped with turn and age",
    )
    snapshot.add_argument(
        "--collect", nargs="+", metavar="NAME[:JSON]", help="collectors to run (default: game)"
    )
    snapshot.add_argument("--out", help="write the snapshot to this file")

    for name, text in (
        ("eval", "run JavaScript in the game's UI and print the result"),
        ("members", "list the properties and methods of an engine object"),
    ):
        action = act.add_parser(name, parents=[common], help=text)
        action.add_argument(
            "code", nargs="?", metavar="EXPRESSION", help="JavaScript, such as 'Game.turn'"
        )
        action.add_argument("--expression", help="the same, as an option")
        if name == "eval":
            action.add_argument(
                "--file", help="run a script file; the value of its last statement is printed"
            )

    autoplay = act.add_parser(
        "autoplay",
        parents=[common],
        help="let the AI play the open game for a number of turns",
    )
    autoplay.add_argument("turns", type=int, nargs="?", help="how many turns")
    autoplay.add_argument("--stop", action="store_true", help="hand the game back now")
    autoplay.add_argument(
        "--observe", type=int, default=0, help="the player whose view to show (default: 0)"
    )

    watch = act.add_parser(
        "watch", parents=[common], help="print the game's console output as it happens"
    )
    watch.add_argument("--seconds", type=float, default=30.0)
    watch.add_argument(
        "--all",
        action="store_true",
        help="every console line, including console.log, rather than only the probe's records",
    )

    parser = command(
        sub,
        "check",
        doc="live.md#specs",
        examples="""
A spec is a JSON file naming what to collect and what should be true of it.
See specs/ for examples.

examples:
  civ7lab check specs/example-tile-yield.json                        live game
  civ7lab check specs/example-tile-yield.json --snapshot before.json  saved snapshot""",
    )
    parser.add_argument("spec", help="a spec file")
    parser.add_argument("--snapshot", help="check a saved snapshot instead of a live game")
    parser.add_argument("--out", help="write the collected data to this file")
    parser.add_argument("--port", type=int)
    parser.set_defaults(func=cmd_check)

    parser = command(
        sub,
        "diff",
        doc="live.md#snapshots-and-diffs",
        examples="""
Items in a list are matched by x and y, type or name rather than by order,
so one added building is one change.

examples:
  civ7lab diff before.json after.json
  civ7lab diff before.json after.json --path data.game""",
    )
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--path", help="compare only this path within each")
    parser.add_argument("--limit", type=int, default=60, help="changes to show")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=cmd_diff)
