"""`civ7lab run`, short of launching the game: which save, which suite, and
what a dry run leaves behind.
"""

import json
import os
import sys
import time

from civ7lab import runner


def save(path, age_seconds):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def test_latest_is_newest_in_single_not_an_autosave(game):
    save(game.user / "Saves/Single/Older.Civ7Save", 300)
    save(game.user / "Saves/Single/Newer.Civ7Save", 100)
    save(game.user / "Saves/Single/auto/AutoSave_0035.Civ7Save", 1)
    save(game.user / "Saves/Single/Automation_2026_09_30__23_36_12_0000.Civ7Save", 1)
    assert runner.latest_save().stem == "Newer"


def test_no_saves_is_none_not_an_error(game):
    assert runner.latest_save() is None


def test_a_save_opens_and_stays_open():
    suite, label, timeout = runner.suite_for(save="Rome35")
    text = suite.parameter_string()
    assert "SaveName=Rome35" in text and "Test=End" in text, text
    assert "Turns" not in text and "QuitApp" not in text, text
    assert (label, timeout) == ("save-Rome35", None)


def test_a_new_game_autoplays_ten_turns_with_a_time_limit():
    suite, label, timeout = runner.suite_for(seed=7)
    text = suite.parameter_string()
    assert "Test=PlayGame" in text and "Turns=10" in text and "GameSeed=7" in text, text
    assert (label, timeout) == ("play-10", 1800)


def test_quit_and_inspector_reach_the_suite():
    suite, _, _ = runner.suite_for(save="Rome35", quit_after=True, inspector=True)
    assert "Test=QuitApp" in suite.parameter_string()
    assert {"Section": "Debug", "Name": "UIDebugger", "Value": 1} in suite.app_options


def test_dry_run_writes_the_run_folder_and_launches_nothing(game, tmp_path):
    game.add_executable()
    (game.user / "Logs/UI.log").write_text("from the last session\n", encoding="utf-8")
    probe = tmp_path / "probe"
    (probe / "ui").mkdir(parents=True)
    suite, label, _ = runner.suite_for(save="Rome35")
    result = runner.run(
        suite,
        label=label,
        out_dir=tmp_path / "runs",
        dry_run=True,
        plan={"onTurn": []},
        probe_dir=probe,
    )
    assert result.returncode is None
    assert (result.directory / "logs-before/UI.log").read_text(
        encoding="utf-8"
    ) == "from the last session\n"
    assert json.loads((result.directory / "suite.json").read_text(encoding="utf-8"))["Tests"]
    assert (result.directory / "plan.json").is_file()
    assert "-autojson" in (result.directory / "command.txt").read_text(encoding="utf-8")
    assert not (probe / "ui/lab-plan.js").exists(), "a dry run must not rewrite the probe"


def test_a_plan_is_written_into_the_probe(tmp_path):
    (tmp_path / "ui").mkdir()
    target = runner.write_plan({"onTurn": [{"collector": "game", "every": 5}]}, tmp_path)
    text = target.read_text(encoding="utf-8")
    assert '"every": 5' in text and "C7Lab.plan" in text
    assert target.name == "lab-plan.js" and target.parent.name == "ui"


def test_a_program_that_runs_too_long_is_stopped(tmp_path):
    log = tmp_path / "stdout.log"
    started = time.monotonic()
    code, note = runner.launch(
        [sys.executable, "-c", "print('started', flush=True); import time; time.sleep(60)"],
        log,
        timeout=2,
    )
    assert time.monotonic() - started < 30
    assert note == "timed out after 2s and was stopped" and code != 0
    assert "started" in log.read_text(encoding="utf-8")


def test_a_program_that_finishes_gives_its_exit_code(tmp_path):
    code, note = runner.launch(
        [sys.executable, "-c", "raise SystemExit(3)"], tmp_path / "out.log", timeout=30
    )
    assert (code, note) == (3, "")


def test_the_plan_is_in_place_for_the_game_and_put_back_after(game, tmp_path, monkeypatch):
    game.add_executable()
    probe = tmp_path / "probe"
    (probe / "ui").mkdir(parents=True)
    plan_file = probe / "ui/lab-plan.js"
    plan_file.write_text("// the empty plan\n", encoding="utf-8")
    seen = tmp_path / "seen-by-the-game.js"
    # The game is stood in for by a program that copies the plan it finds.
    monkeypatch.setattr(
        runner,
        "command_line",
        lambda suite_path: [
            sys.executable,
            "-c",
            f"import shutil; shutil.copy({str(plan_file)!r}, {str(seen)!r})",
        ],
    )
    suite, label, _ = runner.suite_for(turns=1)
    runner.run(suite, label=label, out_dir=tmp_path / "runs", plan={"onTurn": []}, probe_dir=probe)
    assert "C7Lab.plan" in seen.read_text(encoding="utf-8")
    assert plan_file.read_text(encoding="utf-8") == "// the empty plan\n"


def test_turns_with_a_save_is_refused_and_points_to_live_autoplay():
    # The game's LoadGame test ignores Turns when it opens a save.
    try:
        runner.suite_for(save="Rome35", turns=20)
        raise AssertionError("turns with a save should be refused")
    except ValueError as error:
        assert "civ7lab live autoplay" in str(error)


def test_the_game_gets_steams_overlay_as_steam_would_start_it(game, tmp_path, monkeypatch):
    monkeypatch.setattr(runner.paths, "WINDOWS", False)
    steam = tmp_path / "Steam"
    overlay = steam / "ubuntu12_64/gameoverlayrenderer.so"
    overlay.parent.mkdir(parents=True)
    overlay.write_bytes(b"")
    monkeypatch.setattr(runner.paths, "_steam_roots", lambda: [steam])
    monkeypatch.setenv("LD_PRELOAD", "/usr/lib/already-there.so")
    environment, _ = runner.launch_environment()
    assert environment["LD_PRELOAD"] == f"/usr/lib/already-there.so:{overlay}"
    assert environment["ENABLE_VK_LAYER_VALVE_steam_overlay_1"] == "1"
    assert environment["SteamOverlayGameId"] == environment["SteamGameId"] == "1295660"
    assert environment["LD_LIBRARY_PATH"] == "runtime"


def test_without_steams_overlay_the_game_still_starts(game, tmp_path, monkeypatch):
    monkeypatch.setattr(runner.paths, "WINDOWS", False)
    monkeypatch.setattr(runner.paths, "_steam_roots", lambda: [tmp_path / "no-steam"])
    monkeypatch.delenv("LD_PRELOAD", raising=False)
    environment, _ = runner.launch_environment()
    assert "LD_PRELOAD" not in environment and "SteamOverlayGameId" not in environment
