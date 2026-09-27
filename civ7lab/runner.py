"""Launching the game unattended, and keeping what came back.

The game ships its own automation framework: a suite is a JSON file listing
scripts to load and a parameter string describing tests, and the binary takes
`-autojson`, `-autoscript` and `-autoparams` on the command line. Between them,
`{ Test=PlayGame, Turns=40 }` plays forty turns with nobody watching, and
`{ Test=LoadGame, SaveName=X }` boots straight into a save. `{ Test=QuitApp }`
ends the run, so the whole thing terminates by itself.

That is what makes an expensive measurement repeatable. A run that used to mean
an evening of play becomes a command that can be re-run after a change and
diffed against the last one, and the saves it produces are themselves reusable
starting points.

Everything a run produces lands in one directory: the logs before and after,
the records the probe printed, the suite that was used and the command line
that launched it. A measurement nobody can reproduce is an anecdote, and the
cheapest way to keep it reproducible is to keep the inputs beside the outputs.

**Status of the command-line flags.** They are read out of the shipped binary's
own strings and out of the suite format Firaxis' TestSuites use; they have not
yet been confirmed on a live launch on this machine. `--dry-run` prints the
command without running it, and `flags=` lets a caller change them, so a wrong
guess costs one edit rather than a rewrite.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import logs, paths, records

# The shipped scripts a suite needs. Loading the support script is not optional:
# it is what implements QuitApp, and without it a run never ends.
SUPPORT = "fs://game/base-standard/ui/automation/automation-test-support.js"
PLAY_GAME = "fs://game/base-standard/ui/automation/automation-test-play-game.js"
LOAD_GAME = "fs://game/base-standard/ui/automation/automation-test-load-game.js"


@dataclass
class Suite:
    """One automation suite: the scripts, the tests, and the options to force."""
    scripts: list[str] = field(default_factory=lambda: [SUPPORT])
    tests: list[dict] = field(default_factory=list)
    app_options: list[dict] = field(default_factory=list)

    def parameter_string(self) -> str:
        """The `Tests=( { ... }, { ... } )` string the automation parser wants."""
        parts = []
        for test in self.tests:
            inner = ", ".join(f"{key}={value}" for key, value in test.items())
            parts.append("{ " + inner + " }")
        return "Tests=( " + ", ".join(parts) + " )"

    def to_json(self) -> dict:
        document: dict = {"Scripts": self.scripts, "Tests": [self.parameter_string()]}
        if self.app_options:
            document["AppOptions"] = self.app_options
        return document

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_json(), indent=2))
        return path


def debug_options(inspector: bool = True) -> list[dict]:
    """AppOptions to force for a run, without touching the player's own file.

    A suite can carry option overrides, as the shipped SaveDatabases suite
    does. That turns the inspector and the database dumps on for one run only.
    """
    forced = [{"Section": "Debug", "Name": "CopyDatabasesToDisk", "Value": 1},
              {"Section": "Debug", "Name": "EnableConsoleOutput", "Value": 1}]
    if inspector:
        forced.append({"Section": "Debug", "Name": "UIDebugger", "Value": 1})
    return forced


def play_game(turns: int = 10, map_script: str | None = None, map_size: str | None = None,
              difficulty: str | None = None, game_speed: str | None = None,
              map_seed: int | None = None, game_seed: int | None = None,
              observe_as: int | str = 0, quit_after: bool = True,
              extra: dict | None = None) -> Suite:
    """A new game, played by the AI for `turns` turns.

    Seeds are worth setting every time. Two runs of the same seed are the same
    game, which is what turns "the numbers moved" into evidence about the change
    rather than about the map.
    """
    test: dict = {"Test": "PlayGame", "Turns": turns, "ObserveAs": observe_as}
    for key, value in (("MapScript", map_script), ("MapSize", map_size),
                       ("Difficulty", difficulty), ("GameSpeed", game_speed),
                       ("MapSeed", map_seed), ("GameSeed", game_seed)):
        if value is not None:
            test[key] = value
    if extra:
        test.update(extra)
    tests = [test] + ([{"Test": "QuitApp"}] if quit_after else [])
    return Suite(scripts=[SUPPORT, PLAY_GAME], tests=tests)


def latest_save() -> Path | None:
    """The newest save the LoadGame test can boot into, or None.

    Only Saves/Single itself: the game's LoadGame handler builds its request with
    Type=SINGLE_PLAYER and IsAutosave=false hard-coded
    (automation-test-load-game.js:52-54), so an autosave in Single/auto or a
    multiplayer save is not something it can load, however new.
    """
    saves = paths.game().saves
    folder = saves / "Single" if saves else None
    if not folder or not folder.is_dir():
        return None
    found = [p for p in folder.glob("*.Civ7Save") if p.is_file()]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def load_save(name: str, directory: str | None = None, turns: int | None = None,
              quit_after: bool = False) -> Suite:
    """Boot straight into an existing save, and stay there.

    The cheapest measurement available: a save that took an evening to reach is
    reloaded in a minute, and the question asked of it costs nothing more.

    The trailing `Test=End` is not optional. Measured on 21 September 2026: a
    suite of LoadGame alone loads the save, passes, and then the automation
    manager handles AutomationComplete and unloads the game back to the main
    menu four seconds later. `End` calls Automation.setActive(false), which
    stops the automation and leaves the game exactly as it is, which is the
    state a `civ7lab live` session wants to attach to.
    """
    test: dict = {"Test": "LoadGame", "SaveName": name}
    if directory:
        test["SaveDirectory"] = directory
    if turns is not None:
        test["Turns"] = turns
    tail = [{"Test": "QuitApp"}] if quit_after else [{"Test": "End"}]
    return Suite(scripts=[SUPPORT, LOAD_GAME], tests=[test] + tail)


@dataclass
class RunResult:
    directory: Path
    command: list[str]
    returncode: int | None
    seconds: float
    records: records.ParseReport | None = None
    errors: list[logs.LogError] = field(default_factory=list)
    stamps: dict = field(default_factory=dict)
    note: str = ""

    def summary(self) -> str:
        parts = [f"run {self.directory.name}: exit {self.returncode} after {self.seconds:.0f}s"]
        if self.records:
            parts.append(f"{len(self.records.records)} record(s)")
            if self.records.errors:
                parts.append(f"{len(self.records.errors)} record error(s)")
        if self.errors:
            parts.append(f"{len(self.errors)} log error(s)")
        return ", ".join(parts)


def write_plan(plan: dict, mod_dir: Path | None = None) -> Path:
    """Install a recording plan into the probe mod before a run.

    The plan has to exist before the first turn, and an unattended run has
    nobody to type it, so it goes in as a generated file the probe reads at
    load. Rewriting it is how one suite serves many measurements.
    """
    mod_dir = Path(mod_dir) if mod_dir else Path(__file__).resolve().parents[1] / "mod/civ7lab-probe"
    target = mod_dir / "ui/lab-plan.js"
    body = json.dumps(plan, indent=2)
    target.write_text(
        "// civ7lab: GENERATED recording plan. Written by `civ7lab run`;\n"
        "// edit the command, not this file.\n"
        f"// written {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        '(function () {\n  "use strict";\n'
        "  if (!globalThis.C7Lab) return;\n"
        f"  globalThis.C7Lab.plan = {body};\n"
        "  globalThis.C7Lab.config.dumpOnCitySelect = true;\n"
        "})();\n")
    return target


def command_line(suite_path: Path | None, flags: dict | None = None,
                 extra_args: list[str] | None = None) -> list[str]:
    """The argv to launch with.

    The shipped launcher is two lines: cd to the binaries directory and set
    LD_LIBRARY_PATH=runtime. The binary will not start without them, so a
    run reproduces both rather than inventing a third way to start the game.
    """
    executable = paths.executable()
    if not executable:
        raise FileNotFoundError("no game executable found; set CIV7_INSTALL")
    flags = {"suite": "-autojson", **(flags or {})}
    argv = [str(executable)]
    if suite_path:
        argv += [flags["suite"], str(suite_path)]
    argv += list(extra_args or [])
    return argv


def launch_environment(env: dict | None = None) -> tuple[dict, str]:
    """The environment and working directory the shipped launcher sets up."""
    executable = paths.executable()
    directory = str(executable.parent) if executable else os.getcwd()
    environment = {**os.environ,
                   "LD_LIBRARY_PATH": "runtime",
                   # Steam must be running; naming the app id keeps the client
                   # from refusing to initialise when started outside the
                   # library UI.
                   "SteamAppId": paths.STEAM_APP_ID,
                   **(env or {})}
    return environment, directory


def run(suite: Suite | None, label: str = "run", out_dir: Path | None = None,
        timeout: float | None = 1800, dry_run: bool = False, plan: dict | None = None,
        flags: dict | None = None, extra_args: list[str] | None = None,
        env: dict | None = None) -> RunResult:
    """Launch the game, wait for it, and harvest everything it left behind."""
    root = Path(out_dir) if out_dir else Path.cwd() / "runs"
    directory = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}"
    directory.mkdir(parents=True, exist_ok=True)

    if plan is not None:
        write_plan(plan)
        (directory / "plan.json").write_text(json.dumps(plan, indent=2))

    suite_path = suite.write(directory / "suite.json") if suite else None
    argv = command_line(suite_path, flags, extra_args)
    (directory / "command.txt").write_text(" ".join(argv) + "\n")

    # The logs from the session before this one are about to be destroyed: the
    # game truncates every log at launch. Copy them first, every time.
    with_logs = directory / "logs-before"
    try:
        logs.snapshot(with_logs, note=f"state before {label}")
    except FileNotFoundError:
        pass

    if dry_run:
        return RunResult(directory=directory, command=argv, returncode=None, seconds=0.0,
                         note="dry run: nothing was launched")

    started = time.monotonic()
    environment, working_directory = launch_environment(env)
    with open(directory / "stdout.log", "wb") as out:
        process = subprocess.Popen(argv, stdout=out, stderr=subprocess.STDOUT,
                                   env=environment, cwd=working_directory,
                                   start_new_session=True)
        try:
            returncode = process.wait(timeout=timeout)
            note = ""
        except subprocess.TimeoutExpired:
            # A run that will not end is a run that has to be ended, but its
            # logs are still the evidence, so stop it politely and harvest.
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            try:
                returncode = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                returncode = process.wait()
            note = f"timed out after {timeout}s and was stopped"
    seconds = time.monotonic() - started

    after = directory / "logs-after"
    try:
        logs.snapshot(after, note=f"state after {label}")
    except FileNotFoundError:
        pass

    ui_log = after / "UI.log"
    report = records.parse_file(ui_log) if ui_log.is_file() else None
    if report:
        with open(directory / "records.jsonl", "w") as handle:
            for record in report.records:
                handle.write(json.dumps({"seq": record.seq, "kind": record.kind,
                                         "turn": record.turn, "run": record.run,
                                         "data": record.data}) + "\n")

    result = RunResult(directory=directory, command=argv, returncode=returncode,
                       seconds=seconds, records=report,
                       errors=logs.errors(after), stamps=logs.build_stamps(ui_log),
                       note=note)
    (directory / "summary.json").write_text(json.dumps({
        "label": label, "command": argv, "returncode": returncode,
        "seconds": round(seconds, 1), "build": paths.build_id(),
        "records": len(report.records) if report else 0,
        "record_errors": report.errors if report else [],
        "log_errors": [str(error) for error in result.errors][:50],
        "stamps": result.stamps, "note": note,
    }, indent=2))
    return result
