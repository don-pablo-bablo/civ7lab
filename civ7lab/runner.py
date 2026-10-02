"""`civ7lab run`: launch the game through its own automation.

A suite is a JSON file naming scripts to load and tests to run, passed with
`-autojson`. `{ Test=PlayGame, Turns=40 }` autoplays forty turns,
`{ Test=LoadGame, SaveName=X }` opens a save, and `{ Test=QuitApp }` exits.

Each run gets one folder: the suite, the command line, the logs from before
and after, the decoded records and a summary. The inputs sit beside the
outputs, so a run can be repeated.

LoadGame, PlayGame and QuitApp are confirmed in game; see CONTRIBUTING.md.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

from . import logs, paths, records

# The shipped scripts a suite loads. The support script implements QuitApp.
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
        path.write_text(json.dumps(self.to_json(), indent=2), encoding="utf-8")
        return path


def debug_options(inspector: bool = True) -> list[dict]:
    """AppOptions for one run only, carried in the suite as the shipped
    SaveDatabases suite does. The player's own file is not touched."""
    forced = [
        {"Section": "Debug", "Name": "CopyDatabasesToDisk", "Value": 1},
        {"Section": "Debug", "Name": "EnableConsoleOutput", "Value": 1},
    ]
    if inspector:
        forced.append({"Section": "Debug", "Name": "UIDebugger", "Value": 1})
    return forced


def play_game(
    turns: int = 10,
    map_script: str | None = None,
    map_size: str | None = None,
    map_seed: int | None = None,
    game_seed: int | None = None,
    quit_after: bool = True,
) -> Suite:
    """A new game, played by the AI for `turns` turns. With the same seeds,
    two runs play the same map, so a changed number is down to the change."""
    test: dict = {"Test": "PlayGame", "Turns": turns, "ObserveAs": 0}
    for key, value in (
        ("MapScript", map_script),
        ("MapSize", map_size),
        ("MapSeed", map_seed),
        ("GameSeed", game_seed),
    ):
        if value is not None:
            test[key] = value
    tests = [test] + ([{"Test": "QuitApp"}] if quit_after else [])
    return Suite(scripts=[SUPPORT, PLAY_GAME], tests=tests)


def latest_save() -> Path | None:
    """The newest of your saves in Saves/Single, or None.

    The LoadGame test hard-codes Type=SINGLE_PLAYER and IsAutosave=false
    (automation-test-load-game.js:52-54), so it cannot load autosaves or
    multiplayer saves. Saves the automation writes at the end of an autoplay,
    named Automation_<date>, are skipped: they are not the game you were
    playing.
    """
    saves = paths.game().saves
    folder = saves / "Single" if saves else None
    if not folder or not folder.is_dir():
        return None
    found = [
        p for p in folder.glob("*.Civ7Save") if p.is_file() and not p.name.startswith("Automation_")
    ]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


def load_save(name: str, directory: str | None = None, quit_after: bool = False) -> Suite:
    """Open a save and leave the game running.

    The suite must end with `Test=End`. Measured on 21 Sep 2026: with LoadGame
    alone, the game unloads to the main menu four seconds after the save
    loads. `End` stops the automation and leaves the game as it is.

    LoadGame reads `Turns` only when it starts a new game, never with a save
    (automation-test-load-game.js), so a save cannot be autoplayed from here.
    `civ7lab live autoplay` does it once the save is open.
    """
    test: dict = {"Test": "LoadGame", "SaveName": name}
    if directory:
        test["SaveDirectory"] = directory
    tail = [{"Test": "QuitApp"}] if quit_after else [{"Test": "End"}]
    return Suite(scripts=[SUPPORT, LOAD_GAME], tests=[test] + tail)


def suite_for(
    save: str | None = None,
    turns: int | None = None,
    map_script: str | None = None,
    map_size: str | None = None,
    seed: int | None = None,
    quit_after: bool = False,
    inspector: bool = False,
    timeout: float | None = None,
    label: str | None = None,
) -> tuple[Suite, str, float | None]:
    """The suite, run label and timeout for `civ7lab run`'s options.

    A save is someone picking up their game: open it and stop, with no time
    limit. A new game autoplays 10 turns and is stopped after 30 minutes.
    """
    if save:
        if turns is not None:
            raise ValueError(
                "the game's LoadGame test ignores turns when it opens a save. Open the "
                "save, then run: civ7lab live autoplay TURNS"
            )
        suite = load_save(save, quit_after=quit_after)
        label = label or f"save-{save}"
    else:
        turns = 10 if turns is None else turns
        suite = play_game(
            turns=turns,
            map_script=map_script,
            map_size=map_size,
            map_seed=seed,
            game_seed=seed,
            quit_after=quit_after,
        )
        label = label or f"play-{turns}"
        timeout = 1800 if timeout is None else timeout
    if inspector:
        suite.app_options = debug_options(inspector=True)
    return suite, label, timeout


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


def plan_path(mod_dir: Path | None = None) -> Path:
    """The probe's plan file."""
    mod_dir = (
        Path(mod_dir) if mod_dir else Path(__file__).resolve().parents[1] / "mod/civ7lab-probe"
    )
    return mod_dir / "ui/lab-plan.js"


def write_plan(plan: dict, mod_dir: Path | None = None) -> Path:
    """Write a recording plan into the probe mod's lab-plan.js. The probe
    reads it at load, so it must be written before the game starts."""
    target = plan_path(mod_dir)
    body = json.dumps(plan, indent=2)
    target.write_text(
        "// civ7lab: GENERATED recording plan. Written by `civ7lab run`;\n"
        "// edit the command, not this file.\n"
        f"// written {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        '(function () {\n  "use strict";\n'
        "  if (!globalThis.C7Lab) return;\n"
        f"  globalThis.C7Lab.plan = {body};\n"
        "})();\n",
        encoding="utf-8",
    )
    return target


def command_line(suite_path: Path) -> list[str]:
    """The argv to launch with. See `launch_environment` for the rest."""
    executable = paths.executable()
    if not executable:
        raise FileNotFoundError("no game executable found; set CIV7_INSTALL")
    return [str(executable), "-autojson", str(suite_path)]


def launch_environment() -> tuple[dict, str]:
    """What the shipped launcher sets up: the binaries folder as working
    directory and, on Linux, LD_LIBRARY_PATH=runtime. The Linux binary will
    not start without them.

    On Linux it also loads Steam's overlay the way Steam does for a game it
    starts, read from a Steam-launched game on 2 Oct 2026, so F12 screenshots
    work. On Windows Steam adds its overlay another way, which needs the game
    started through Steam.
    """
    executable = paths.executable()
    directory = str(executable.parent) if executable else os.getcwd()
    # Steam must be running. The app id lets the game start outside the
    # Steam library.
    environment = {
        **os.environ,
        "SteamAppId": paths.STEAM_APP_ID,
        "SteamGameId": paths.STEAM_APP_ID,
    }
    if not paths.WINDOWS:
        environment["LD_LIBRARY_PATH"] = "runtime"
        overlay = paths.steam_overlay()
        if overlay:
            preload = [p for p in environment.get("LD_PRELOAD", "").split(":") if p]
            environment["LD_PRELOAD"] = ":".join([*preload, str(overlay)])
            environment["SteamOverlayGameId"] = paths.STEAM_APP_ID
            environment["ENABLE_VK_LAYER_VALVE_steam_overlay_1"] = "1"
    return environment, directory


def launch(
    argv: list[str], log: Path, timeout: float | None, cwd: str | None = None, env=None
) -> tuple[int, str]:
    """Run a program with its output in `log`, and stop it if it runs past
    `timeout`. Returns the exit code and a note, empty unless it was stopped."""
    # Its own process group, so stopping it stops anything it started.
    group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if paths.WINDOWS
        else {"start_new_session": True}
    )
    with open(log, "wb") as out:
        process = subprocess.Popen(
            argv, stdout=out, stderr=subprocess.STDOUT, env=env, cwd=cwd, **group
        )
        try:
            return process.wait(timeout=timeout), ""
        except subprocess.TimeoutExpired:
            # Stop it politely, then collect the logs as usual.
            _stop(process, force=False)
            try:
                returncode = process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                _stop(process, force=True)
                returncode = process.wait()
            return returncode, f"timed out after {timeout}s and was stopped"


def _stop(process: subprocess.Popen, force: bool) -> None:
    if paths.WINDOWS:
        # Windows has no gentler signal a GUI program listens to.
        process.kill()
    else:
        os.killpg(os.getpgid(process.pid), signal.SIGKILL if force else signal.SIGTERM)


def run(
    suite: Suite,
    label: str = "run",
    out_dir: Path | None = None,
    timeout: float | None = 1800,
    dry_run: bool = False,
    plan: dict | None = None,
    probe_dir: Path | None = None,
) -> RunResult:
    """Launch the game, wait for it, and collect everything it left behind.

    A plan is written into the probe for the run, and the probe's plan file
    is put back as it was when the game exits. A dry run writes the run
    folder and copies the logs, but launches nothing and leaves the probe
    alone.
    """
    root = Path(out_dir) if out_dir else Path.cwd() / "runs"
    directory = root / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}"
    directory.mkdir(parents=True, exist_ok=True)

    if plan is not None:
        (directory / "plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")

    suite_path = suite.write(directory / "suite.json")
    argv = command_line(suite_path)
    (directory / "command.txt").write_text(" ".join(argv) + "\n", encoding="utf-8")

    # The game empties every log at launch, so copy the last session's first.
    with_logs = directory / "logs-before"
    with contextlib.suppress(FileNotFoundError):
        logs.snapshot(with_logs, note=f"state before {label}")

    if dry_run:
        return RunResult(
            directory=directory,
            command=argv,
            returncode=None,
            seconds=0.0,
            note="dry run: nothing was launched",
        )

    plan_file = plan_path(probe_dir)
    original = plan_file.read_text(encoding="utf-8") if plan is not None else None
    started = time.monotonic()
    try:
        if plan is not None:
            write_plan(plan, probe_dir)
        environment, working_directory = launch_environment()
        returncode, note = launch(
            argv, directory / "stdout.log", timeout, cwd=working_directory, env=environment
        )
    finally:
        if original is not None:
            plan_file.write_text(original, encoding="utf-8")
    seconds = time.monotonic() - started

    after = directory / "logs-after"
    with contextlib.suppress(FileNotFoundError):
        logs.snapshot(after, note=f"state after {label}")

    ui_log = after / "UI.log"
    report = records.parse_file(ui_log) if ui_log.is_file() else None
    if report:
        with open(directory / "records.jsonl", "w", encoding="utf-8") as handle:
            for record in report.records:
                handle.write(
                    json.dumps(
                        {
                            "seq": record.seq,
                            "kind": record.kind,
                            "turn": record.turn,
                            "run": record.run,
                            "data": record.data,
                        }
                    )
                    + "\n"
                )

    result = RunResult(
        directory=directory,
        command=argv,
        returncode=returncode,
        seconds=seconds,
        records=report,
        errors=logs.errors(after),
        stamps=logs.build_stamps(ui_log),
        note=note,
    )
    (directory / "summary.json").write_text(
        json.dumps(
            {
                "label": label,
                "command": argv,
                "returncode": returncode,
                "seconds": round(seconds, 1),
                "build": paths.build_id(),
                "records": len(report.records) if report else 0,
                "record_errors": report.errors if report else [],
                "log_errors": [str(error) for error in result.errors][:50],
                "stamps": result.stamps,
                "note": note,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return result
