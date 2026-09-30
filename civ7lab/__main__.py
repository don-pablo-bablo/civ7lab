"""The command line. One entry point, because a tool nobody can remember how to
call does not get used.

Output is meant to be read by a person or by an agent with a token budget: the
answer first, the detail only when asked. Anything that produces data takes
--json, so a result can go straight into a diff or a spec instead of being
retyped.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import appoptions, cdp, check, diff, doctor, hotswap, jscheck, live, logs, mock, mod
from . import modinfo
from . import paths, records, runner, sqlcheck, workshop


def _print_json(value) -> None:
    print(json.dumps(value, indent=2, default=str))


# --------------------------------------------------------------------------
# environment
# --------------------------------------------------------------------------

def cmd_doctor(args) -> int:
    if args.json:
        _print_json([finding.__dict__ for finding in doctor.check()])
        return 0
    print(doctor.report())
    return 0


def cmd_options(args) -> int:
    if args.live or args.play:
        preset = appoptions.LIVE_PRESET if args.live else appoptions.PLAY_PRESET
        for line in appoptions.apply_preset(preset, dry_run=args.dry_run):
            print(("would set " if args.dry_run else "") + line)
        if not args.dry_run:
            print("\nAppOptions is read at launch, so restart the game for these to take effect.")
        return 0
    if args.set:
        options = appoptions.load()
        for pair in args.set:
            name, _, value = pair.partition("=")
            print(options.set(name, value))
        if not args.dry_run:
            backup = options.save()
            print(f"saved (backup: {backup})")
            print("Restart the game: AppOptions is read at launch.")
        return 0
    options = appoptions.load()
    for name in sorted({*appoptions.LIVE_PRESET, *appoptions.PLAY_PRESET,
                        "EnableTuner", "UILogLevel", "ModdingLogLevel"}):
        option = options.get(name)
        state = "unset" if not option else (
            option.value if option.enabled else f"{option.value} (commented out)")
        print(f"{name:24} {state}")
    return 0


# --------------------------------------------------------------------------
# offline
# --------------------------------------------------------------------------

def cmd_sql(args) -> int:
    result = sqlcheck.run(args.mod, age=args.age, db=args.db, prefix=args.prefix,
                          diff_limit=args.rows)
    if args.json:
        _print_json({"summary": result.summary(),
                     "files": [{"file": str(f.path), "group": f.group, "ok": f.ok,
                                "error": f.error, "notes": f.notes} for f in result.files],
                     "warnings": result.warnings,
                     "diffs": [{"table": d.table, "added": d.added_count,
                                "removed": d.removed_count,
                                "sample_added": d.added, "sample_removed": d.removed}
                               for d in result.diffs]})
        return 0 if result.ok else 1
    print(result.summary())
    if result.cleaned:
        print(f"stripped {result.cleaned} pre-existing row(s) matching {args.prefix}* "
              "from the baseline, so this measures what the files do now")
    for file_result in result.files:
        mark = "ok  " if file_result.ok else "FAIL"
        print(f"  {mark} {file_result.path.name:32} {file_result.group}"
              + (f"  {file_result.statements} statement(s)" if file_result.statements else ""))
        if file_result.error:
            print(f"       {file_result.error}")
        for note in file_result.notes:
            print(f"       note: {note}")
    for warning in result.warnings:
        print(f"  warn: {warning}")
    for table_diff in result.diffs:
        print(f"  {table_diff.table}: +{table_diff.added_count} -{table_diff.removed_count}")
        if args.rows:
            for row in table_diff.added[:args.rows]:
                print(f"       + {row}")
            for row in table_diff.removed[:args.rows]:
                print(f"       - {row}")
    return 0 if result.ok else 1


def cmd_jscheck(args) -> int:
    reports = jscheck.check(args.mod)
    failures = 0
    for report in reports:
        if not report.ok:
            failures += 1
        mark = "ok  " if report.ok else "FAIL"
        stamp = f"[{report.build_stamp}]" if report.build_stamp else ""
        print(f"{mark} {report.path.name} {stamp}")
        for line, kind, text in report.syntax_errors:
            print(f"      line {line}: {kind}: {text!r}")
        for warning in report.warnings:
            print(f"      - {warning}")
    if not any(report.parsed for report in reports):
        print("\n(parsing was skipped: pip install tree_sitter tree_sitter_javascript)")
    return 1 if failures else 0


def cmd_modinfo(args) -> int:
    info = modinfo.load(args.mod)
    print(f"{info.id}  {info.name}  v{info.version}")
    for age in (modinfo.AGES if not args.age else [args.age]):
        items = info.items("UpdateDatabase", age)
        print(f"\n{age}: {len(items)} database item(s), in apply order")
        for group, path in items:
            mark = " " if path.is_file() else "?"
            print(f"  {mark} [{group.load_order:>5}] {group.id:28} {path.name}")
    scripts = info.ui_scripts()
    if scripts:
        print(f"\nUI scripts ({len(scripts)}):")
        for path in scripts:
            print(f"    {path.name}" + ("" if path.is_file() else "   MISSING"))
    disabled = modinfo.disabled_items(args.mod)
    if disabled:
        print("\ncommented out in the modinfo, so not loaded:")
        for item in disabled:
            print(f"    {item}")
    ambiguous = info.ambiguous_criteria()
    if ambiguous:
        print(f"\nambiguous age criteria: {', '.join(ambiguous)}"
              f" (groups: {', '.join(info.groups_using(ambiguous))})"
              "\n  AgeAtOrBefore/AgeAtOrAfter read one way here and could mean the other;"
              "\n  spelling them as explicit AgeInUse rows removes the doubt.")
    return 0


# --------------------------------------------------------------------------
# mods
# --------------------------------------------------------------------------

def cmd_mod(args) -> int:
    if args.action == "list":
        rows = mod.installed()
        if not rows:
            print("no mods installed")
            return 0
        for row in rows:
            target = f" -> {row.target}" if row.target else ""
            state = "" if row.valid else "   BROKEN"
            print(f"{row.name:28} {row.kind}{target}{state}")
        return 0
    if args.action == "install":
        print(mod.install(args.path, link=not args.copy, force=args.force))
        return 0
    if args.action == "uninstall":
        print(mod.uninstall(args.path or "civ7lab-probe"))
        return 0
    return 1


# --------------------------------------------------------------------------
# logs
# --------------------------------------------------------------------------

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
        for error in found[:args.limit]:
            print(error)
        print(f"\n{len(found)} error line(s)")
        return 1
    if args.action == "records":
        report = logs.read_records(args.log)
        if args.json:
            _print_json({"records": [{"kind": r.kind, "seq": r.seq, "turn": r.turn,
                                      "data": r.data} for r in report.records],
                         "errors": report.errors, "missing": report.missing_seq})
            return 0
        kinds: dict[str, int] = {}
        for record in report.records:
            kinds[record.kind] = kinds.get(record.kind, 0) + 1
        print(f"{len(report.records)} record(s): "
              + ", ".join(f"{kind} x{count}" for kind, count in sorted(kinds.items())))
        for error in report.errors[:20]:
            print(f"  error: {error}")
        if report.missing_seq:
            print(f"  missing sequence numbers: {report.missing_seq[:20]}")
        return 0
    if args.action == "stamps":
        stamps = logs.build_stamps(args.log)
        if not stamps:
            print("no build stamps in the log: either nothing instrumented ran, "
                  "or the scripts do not print one")
            return 1
        for name, stamp in stamps.items():
            print(f"{name:20} {stamp}")
        return 0
    if args.action == "marker":
        for line in logs.marker_lines(args.log, args.marker):
            print(line)
        return 0
    return 1


# --------------------------------------------------------------------------
# live
# --------------------------------------------------------------------------

def cmd_live(args) -> int:
    if args.action == "targets":
        port = args.port or cdp.find_port()
        if not port:
            print("nothing listening. Is the game running, and is UIDebugger on?\n"
                  "  civ7lab options --live   (then restart the game)")
            return 1
        for target in cdp.targets("127.0.0.1", port):
            print(target)
        return 0

    probe = live.attach(port=args.port, match=args.target, install=not args.no_install)
    if args.action == "attach":
        print(f"attached: {probe.session.ws_url}")
        print(f"probe build {probe.build}")
        print("collectors: " + ", ".join(probe.collectors()))
        return 0
    if args.action == "collectors":
        _print_json(probe.collectors())
        return 0
    if args.action == "eval":
        _print_json(probe.evaluate(args.expression))
        return 0
    if args.action == "members":
        _print_json(probe.members(args.expression))
        return 0
    if args.action == "collect":
        arguments = json.loads(args.args) if args.args else {}
        value = probe.dump(args.collector, arguments) if args.also_log \
            else probe.collect(args.collector, arguments)
        if args.out:
            Path(args.out).write_text(json.dumps(value, indent=2, default=str))
            print(f"wrote {args.out}")
        else:
            _print_json(value)
        return 0
    if args.action == "snapshot":
        spec = []
        for item in args.collect or ["game"]:
            name, _, arguments = item.partition(":")
            spec.append((name, json.loads(arguments) if arguments else {}))
        taken = probe.snapshot(spec)
        if args.out:
            Path(args.out).write_text(json.dumps(taken, indent=2, default=str))
            print(f"wrote {args.out}  (turn {taken.get('turn')}, {taken.get('age')})")
        else:
            _print_json(taken)
        return 0
    if args.action == "watch":
        for line in probe.watch(seconds=args.seconds):
            print(f"[{line['level']}] {line['text']}")
        return 0
    if args.action == "check":
        spec = check.Spec.load(args.spec)
        result = check.evaluate(spec, check.gather(spec, probe))
        print(result.report())
        if args.out:
            Path(args.out).write_text(json.dumps(result.data, indent=2, default=str))
        return 0 if result.passed else 1
    return 1


# --------------------------------------------------------------------------
# ui
# --------------------------------------------------------------------------

def cmd_ui(args) -> int:
    files: list[Path] = []
    for given in args.paths:
        path = Path(given)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.js")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"no such file or directory: {given}")
    if not files:
        print("no .js files to watch")
        return 1
    watcher = hotswap.Watcher(files, root=args.root, after=args.after,
                              port=args.port, target=args.target)
    return watcher.run(once=args.action == "push")


# --------------------------------------------------------------------------
# runs and comparisons
# --------------------------------------------------------------------------

def cmd_run(args) -> int:
    plan = json.loads(Path(args.plan).read_text()) if args.plan else None
    # A save is somebody picking up their game: load it and stop, and do not
    # end it after half an hour. A new game is the unattended case the old
    # defaults were for, and keeps them.
    turns = args.turns if args.turns is not None else (-1 if args.save else 10)
    timeout = args.timeout if args.timeout is not None else (None if args.save else 1800)
    save = args.save
    if save == "latest":
        newest = runner.latest_save()
        if newest is None:
            print("no save in Saves/Single to load (autosaves cannot be loaded this way)")
            return 1
        save = newest.stem
        stamp = time.strftime("%d %b %H:%M", time.localtime(newest.stat().st_mtime))
        print(f"latest save: {save} ({stamp})")
    if save:
        suite = runner.load_save(save, turns=turns if turns >= 0 else None,
                                 quit_after=args.quit)
        label = args.label or f"save-{save}"
    else:
        suite = runner.play_game(turns=turns, map_script=args.map,
                                 map_size=args.size, map_seed=args.seed,
                                 game_seed=args.seed, quit_after=args.quit)
        label = args.label or f"play-{args.turns}"
    if args.inspector:
        suite.app_options = runner.debug_options(inspector=True)
    result = runner.run(suite, label=label, out_dir=args.out, timeout=timeout,
                        dry_run=args.dry_run, plan=plan)
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


def cmd_mock(args) -> int:
    if args.action == "fixtures":
        latest = [f.strip() for f in args.latest_by.split(",") if f.strip()] if args.latest_by else None
        out, total, kept = mock.fixtures_from_records(kind=args.kind, log=args.log, out=args.out,
                                                      latest=latest)
        dropped = f", {total - kept} older reading(s) of the same case dropped" if latest else ""
        print(f"wrote {out}: {kept} fixture(s) from {total} {args.kind} record(s){dropped}")
        return 0
    mock.serve(root=args.root, renderer=args.renderer, export=args.export,
               fixtures=args.fixtures, port=args.port, open_browser=args.open)
    return 0


def cmd_diff(args) -> int:
    before = json.loads(Path(args.before).read_text())
    after = json.loads(Path(args.after).read_text())
    if args.path:
        before = check.resolve(before, args.path)
        after = check.resolve(after, args.path)
    changes = diff.compare(before, after)
    if args.json:
        _print_json([{"path": change.path, "kind": change.kind,
                      "before": change.before, "after": change.after} for change in changes])
        return 0
    print(diff.summarise(changes, limit=args.limit))
    return 0


def cmd_check(args) -> int:
    spec = check.Spec.load(args.spec)
    if args.snapshot:
        data = check.bind(spec, check.from_snapshot(
            json.loads(Path(args.snapshot).read_text())))
    else:
        probe = live.attach(port=args.port)
        data = check.gather(spec, probe)
    result = check.evaluate(spec, data)
    print(result.report())
    return 0 if result.passed else 1


# --------------------------------------------------------------------------
# workshop
# --------------------------------------------------------------------------

def cmd_workshop(args) -> int:
    item = workshop.details(args.item)
    if item.consumer_app_id != workshop.CONSUMER_APP_ID:
        print(f"item {item.id} is for app {item.consumer_app_id}, not Civ VII")
        return 1
    if not args.tags:
        if args.json:
            _print_json(item.__dict__)
            return 0
        print(f"{item.title} ({item.id})")
        print("  tags: " + (", ".join(item.tags) or "none"))
        return 0
    tags = workshop.resolve_tags(args.tags)
    dropped = [tag for tag in item.tags if tag not in tags]
    report = {"item": item.id, "title": item.title, "now": item.tags,
              "new": tags, "dropped": dropped}
    if not args.json:
        print(f"{item.title} ({item.id})")
        print("  now: " + (", ".join(item.tags) or "none"))
        print("  new: " + ", ".join(tags))
        if dropped:
            print("  dropped: " + ", ".join(dropped))
    if args.dry_run:
        if args.json:
            _print_json(report)
        else:
            print("dry run: nothing submitted")
        return 0
    submitted = workshop.submit(item, tags)
    report["attempts"] = [{"app_id": a, "result": r} for a, r in submitted.attempts]
    if not args.json:
        for app_id, outcome in submitted.attempts:
            print(f"  submit as app {app_id}: {outcome}")
    if not submitted.ok:
        if args.json:
            _print_json(report)
        return 1
    after = workshop.read_back(item.id, tags)
    report["read_back"] = after.tags
    matched = sorted(after.tags) == sorted(tags)
    if args.json:
        _print_json(report)
    else:
        print("  read back: " + (", ".join(after.tags) or "none"))
        if not matched:
            print("  the web API does not show the new tags yet; it can lag. "
                  f"Check again with: civ7lab workshop tags {item.id}")
    return 0 if matched else 1


# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="civ7lab", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="is anything here going to work, and why not")
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.set_defaults(func=cmd_doctor)

    options_parser = sub.add_parser("options", help="read or set the game's development switches")
    options_parser.add_argument("--live", action="store_true",
                                help="turn on the inspector, the file watcher and the database dumps")
    options_parser.add_argument("--play", action="store_true", help="turn them off again")
    options_parser.add_argument("--set", nargs="+", metavar="NAME=VALUE")
    options_parser.add_argument("--dry-run", action="store_true")
    options_parser.set_defaults(func=cmd_options)

    sql_parser = sub.add_parser("sql", help="apply a mod's database changes offline and diff the rows")
    sql_parser.add_argument("mod", help="path to the mod directory or its .modinfo")
    sql_parser.add_argument("--age", choices=modinfo.AGES, help="which age's rules to apply")
    sql_parser.add_argument("--db", help="database to apply to (default: the game's own dump)")
    sql_parser.add_argument("--prefix", help="strip rows with this tag prefix first, so the "
                                             "baseline is not the mod's own previous output")
    sql_parser.add_argument("--rows", type=int, default=0, help="show up to N changed rows per table")
    sql_parser.add_argument("--json", action="store_true")
    sql_parser.set_defaults(func=cmd_sql)

    js_parser = sub.add_parser("jscheck", help="parse a mod's UI scripts and check them against its modinfo")
    js_parser.add_argument("mod")
    js_parser.set_defaults(func=cmd_jscheck)

    info_parser = sub.add_parser("modinfo", help="what a mod loads, per age, in order")
    info_parser.add_argument("mod")
    info_parser.add_argument("--age", choices=modinfo.AGES)
    info_parser.set_defaults(func=cmd_modinfo)

    mod_parser = sub.add_parser("mod", help="install, list or remove mods in the game's Mods folder")
    mod_parser.add_argument("action", choices=["list", "install", "uninstall"])
    mod_parser.add_argument("path", nargs="?", help="mod directory (default: this toolkit's probe)")
    mod_parser.add_argument("--copy", action="store_true", help="copy instead of symlinking")
    mod_parser.add_argument("--force", action="store_true")
    mod_parser.set_defaults(func=cmd_mod)

    logs_parser = sub.add_parser("logs", help="snapshot, search and decode the game's logs")
    logs_parser.add_argument("action", choices=["snapshot", "errors", "records", "stamps", "marker"])
    logs_parser.add_argument("--log", help="a UI.log to read instead of the live one")
    logs_parser.add_argument("--dir", help="a snapshot directory to read instead of the live one")
    logs_parser.add_argument("--out", help="where a snapshot goes")
    logs_parser.add_argument("--marker", default=records.MARKER)
    logs_parser.add_argument("--limit", type=int, default=40)
    logs_parser.add_argument("--json", action="store_true")
    logs_parser.set_defaults(func=cmd_logs)

    live_parser = sub.add_parser("live", help="ask a running game a question, with no reload")
    live_parser.add_argument("action", choices=["targets", "attach", "collectors", "collect",
                                                "snapshot", "eval", "members", "watch", "check"])
    live_parser.add_argument("collector", nargs="?", help="for collect: which collector")
    live_parser.add_argument("--args", help="JSON arguments for the collector")
    live_parser.add_argument("--expression", help="for eval and members")
    live_parser.add_argument("--collect", nargs="+", help="for snapshot: name or name:{json}")
    live_parser.add_argument("--spec", help="for check: a spec file")
    live_parser.add_argument("--out", help="write the result to a file")
    live_parser.add_argument("--port", type=int)
    live_parser.add_argument("--target", help="pick the UI context by substring")
    live_parser.add_argument("--no-install", action="store_true",
                             help="do not inject the probe; use what is already there")
    live_parser.add_argument("--also-log", action="store_true",
                             help="also print the result into UI.log, so it outlives the game")
    live_parser.add_argument("--seconds", type=float, default=30.0, help="for watch")
    live_parser.set_defaults(func=cmd_live)

    ui_parser = sub.add_parser("ui", help="patch a mod's UI scripts into the running game on save")
    ui_parser.add_argument("action", choices=["watch", "push"],
                           help="watch: patch on every save until Ctrl-C; push: bring the game "
                                "level with the files once and exit")
    ui_parser.add_argument("paths", nargs="+", help="files, or directories of .js files")
    ui_parser.add_argument("--root", help="the mod folder, when no .modinfo sits above the files")
    ui_parser.add_argument("--after", help="JavaScript to run in the game after each patch, "
                                            "e.g. to redraw a panel")
    ui_parser.add_argument("--port", type=int)
    ui_parser.add_argument("--target", help="pick the UI context by substring")
    ui_parser.set_defaults(func=cmd_ui)

    run_parser = sub.add_parser("run", help="launch the game unattended and harvest everything")
    run_parser.add_argument("--save", help="load this save instead of starting a new game; "
                                           "'latest' for the newest in Saves/Single")
    run_parser.add_argument("--turns", type=int, default=None,
                            help="turns to autoplay, -1 for none (default: 10 for a new game, "
                                 "none for a save)")
    run_parser.add_argument("--map", help="map script, e.g. continents.js")
    run_parser.add_argument("--size", help="map size")
    run_parser.add_argument("--seed", type=int, help="map and game seed, for a repeatable run")
    run_parser.add_argument("--plan", help="a JSON recording plan for the probe")
    run_parser.add_argument("--label", help="name for the run directory")
    run_parser.add_argument("--out", help="where run directories go (default: ./runs)")
    run_parser.add_argument("--timeout", type=float, default=None,
                            help="seconds before the game is stopped (default: 1800 for a new "
                                 "game; none for a save, which is somebody playing)")
    run_parser.add_argument("--quit", action="store_true", default=False,
                            help="end with QuitApp so the run terminates by itself")
    run_parser.add_argument("--inspector", action="store_true",
                            help="force UIDebugger on for this run only")
    run_parser.add_argument("--dry-run", action="store_true",
                            help="write the suite and print the command without launching")
    run_parser.set_defaults(func=cmd_run)

    mock_parser = sub.add_parser("mock", help="draw a mod's panel in a browser, no reload")
    mock_parser.add_argument("action", choices=["serve", "fixtures"])
    mock_parser.add_argument("--root", default=".", help="the mod directory to serve")
    mock_parser.add_argument("--renderer", default="", help="path to the render module, "
                                                           "relative to --root")
    mock_parser.add_argument("--export", default="render", help="the function to call per fixture")
    mock_parser.add_argument("--fixtures", default="fixtures.js")
    mock_parser.add_argument("--port", type=int, default=8000)
    mock_parser.add_argument("--open", action="store_true", help="open a browser")
    mock_parser.add_argument("--kind", default="fixture", help="for fixtures: the record kind")
    mock_parser.add_argument("--log", help="for fixtures: a UI.log to read")
    mock_parser.add_argument("--out", help="for fixtures: where to write fixtures.js")
    mock_parser.add_argument("--latest-by", help="for fixtures: comma-separated fields (dotted paths "
                                                 "into the data) that identify a case; keep only "
                                                 "the last record of each, e.g. cityName,loc.x,loc.y")
    mock_parser.set_defaults(func=cmd_mock)

    diff_parser = sub.add_parser("diff", help="compare two snapshots")
    diff_parser.add_argument("before")
    diff_parser.add_argument("after")
    diff_parser.add_argument("--path", help="compare only this path within each")
    diff_parser.add_argument("--limit", type=int, default=60)
    diff_parser.add_argument("--json", action="store_true")
    diff_parser.set_defaults(func=cmd_diff)

    check_parser = sub.add_parser("check", help="run a spec's expectations")
    check_parser.add_argument("spec")
    check_parser.add_argument("--snapshot", help="check a saved snapshot instead of a live game")
    check_parser.add_argument("--port", type=int)
    check_parser.set_defaults(func=cmd_check)

    workshop_parser = sub.add_parser("workshop", help="set the tags on a Workshop item you own")
    workshop_parser.add_argument("action", choices=["tags"])
    workshop_parser.add_argument("item", help="the Workshop item ID")
    workshop_parser.add_argument("tags", nargs="*",
                                 help="the full new tag list; Mod is always kept. "
                                      "Quote names with spaces, or separate with commas. "
                                      "None: show the current tags")
    workshop_parser.add_argument("--dry-run", action="store_true",
                                 help="show the current and new tags without submitting")
    workshop_parser.add_argument("--json", action="store_true")
    workshop_parser.set_defaults(func=cmd_workshop)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (cdp.CDPError, workshop.WorkshopError, FileNotFoundError) as error:
        print(f"civ7lab: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
