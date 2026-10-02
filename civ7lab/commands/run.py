"""run and logs: launching the game, and what it leaves behind."""

from __future__ import annotations

import json
import time
from pathlib import Path

from .. import logs, records, runner
from ._common import actions, command, print_json


def cmd_run(args) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if args.plan else None
    save = args.save
    if save == "latest":
        newest = runner.latest_save()
        if newest is None:
            print("no save in Saves/Single to load (autosaves cannot be loaded this way)")
            return 1
        save = newest.stem
        stamp = time.strftime("%d %b %H:%M", time.localtime(newest.stat().st_mtime))
        print(f"latest save: {save} ({stamp})")
    try:
        suite, label, timeout = runner.suite_for(
            save=save,
            turns=args.turns,
            map_script=args.map,
            map_size=args.size,
            seed=args.seed,
            quit_after=args.quit,
            inspector=args.inspector,
            timeout=args.timeout,
            label=args.label,
        )
    except ValueError as error:
        print(f"civ7lab: {error}")
        return 1
    result = runner.run(
        suite, label=label, out_dir=args.out, timeout=timeout, dry_run=args.dry_run, plan=plan
    )
    if args.dry_run:
        print("would run:")
        print("  " + " ".join(result.command))
        print(f"suite written to {result.directory / 'suite.json'}")
        print(json.dumps(suite.to_json(), indent=2))
        return 0
    print(result.summary())
    print(f"everything landed in {result.directory}")
    for error in result.errors[:10]:
        print(f"  {error}")
    return 0 if result.returncode in (0, None) else 1


def cmd_logs(args) -> int:
    if args.action == "snapshot":
        destination = logs.snapshot(args.out or Path.cwd() / "runs" / "logs-snapshot")
        print(f"copied the log directory to {destination}")
        return 0
    if args.action == "errors":
        found = logs.errors(args.dir)
        if not found:
            print("no database, modding or script errors in the logs")
            return 0
        for error in found[: args.limit]:
            print(error)
        print(f"\n{len(found)} error line(s)")
        return 1
    if args.action == "records":
        report = logs.read_records(args.log)
        if args.json:
            print_json(
                {
                    "records": [
                        {"kind": r.kind, "seq": r.seq, "turn": r.turn, "data": r.data}
                        for r in report.records
                    ],
                    "errors": report.errors,
                    "missing": report.missing_seq,
                }
            )
            return 0
        kinds: dict[str, int] = {}
        for record in report.records:
            kinds[record.kind] = kinds.get(record.kind, 0) + 1
        print(
            f"{len(report.records)} record(s): "
            + ", ".join(f"{kind} x{count}" for kind, count in sorted(kinds.items()))
        )
        for error in report.errors[:20]:
            print(f"  error: {error}")
        if report.missing_seq:
            print(f"  missing sequence numbers: {report.missing_seq[:20]}")
        return 0
    if args.action == "stamps":
        stamps = logs.build_stamps(args.log)
        if not stamps:
            print(
                "no build stamps in the log: either nothing instrumented ran, "
                "or the scripts do not print one"
            )
            return 1
        for name, stamp in stamps.items():
            print(f"{name:20} {stamp}")
        return 0
    for line in logs.marker_lines(args.log, args.marker):
        print(line)
    return 0


def register(sub) -> None:
    parser = command(
        sub,
        "run",
        doc="runs.md",
        examples="""
Uses the game's own automation. The logs from the last session are copied
first, since the game empties them at launch. Everything lands in one folder
under ./runs.

examples:
  civ7lab run --save latest --inspector       open the newest save, ready for `live`
  civ7lab run --save MySave                    open a named save from Saves/Single
  civ7lab run --turns 40 --seed 12345 --quit   autoplay a new game, then exit
  civ7lab live autoplay 20                     after opening a save: the AI plays 20 turns
  civ7lab run --turns 40 --plan plans/sample-every-five.json --quit
  civ7lab run --save MySave --dry-run          print the command, launch nothing""",
    )
    parser.add_argument(
        "--save",
        help="load this save instead of starting a new game; "
        "'latest' for the newest in Saves/Single",
    )
    parser.add_argument(
        "--turns",
        type=int,
        default=None,
        help="turns to autoplay a new game (default: 10). A save cannot be autoplayed "
        "this way: open it, then run civ7lab live autoplay",
    )
    parser.add_argument("--map", help="map script, e.g. continents.js")
    parser.add_argument("--size", help="map size")
    parser.add_argument("--seed", type=int, help="map and game seed, for a repeatable run")
    parser.add_argument(
        "--plan", help="a JSON recording plan: which collectors to log on which turns"
    )
    parser.add_argument("--label", help="name for the run folder")
    parser.add_argument("--out", help="where run folders go (default: ./runs)")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="seconds before the game is stopped (default: 1800 for a new game, none for a save)",
    )
    parser.add_argument(
        "--quit", action="store_true", default=False, help="exit the game when the tests finish"
    )
    parser.add_argument(
        "--inspector", action="store_true", help="turn UIDebugger on for this run only"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="write the suite and print the command without launching",
    )
    parser.set_defaults(func=cmd_run)

    parser = command(
        sub,
        "logs",
        doc="runs.md#logs",
        examples="""
The game empties every log at launch. Snapshot before starting it again.

examples:
  civ7lab logs errors                  database, modding and script errors only
  civ7lab logs stamps                  which build of each script actually ran
  civ7lab logs snapshot --out keep/    copy the whole log folder
  civ7lab logs marker --marker "[MYMOD]"   every UI.log line with your mod's tag
  civ7lab logs records --json          decode the probe's records""",
    )
    parser.set_defaults(func=cmd_logs)
    act = actions(parser)
    snapshot = act.add_parser("snapshot", help="copy the log folder somewhere safe")
    snapshot.add_argument("--out", help="where to copy to (default: ./runs/logs-snapshot)")
    errors = act.add_parser("errors", help="only the lines that report an error")
    errors.add_argument("--dir", help="a snapshot folder to read instead of the live logs")
    errors.add_argument("--limit", type=int, default=40, help="lines to show")
    decoded = act.add_parser("records", help="decode [C7LAB] records from UI.log")
    decoded.add_argument("--log", help="a UI.log to read instead of the live one")
    decoded.add_argument("--json", action="store_true")
    stamps = act.add_parser("stamps", help="the build stamps printed at load")
    stamps.add_argument("--log", help="a UI.log to read instead of the live one")
    marker = act.add_parser("marker", help="every UI.log line containing a tag")
    marker.add_argument("--log", help="a UI.log to read instead of the live one")
    marker.add_argument(
        "--marker", default=records.MARKER, help=f"the tag to look for (default: {records.MARKER})"
    )
