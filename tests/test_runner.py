"""Tests for picking and loading a save, without launching anything.

`--save latest` has to pick a save the game's LoadGame test can actually load:
the newest in Saves/Single, never an autosave (the test hard-codes
IsAutosave=false), however much newer the autosave is.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from civ7lab import paths, runner


def _save(path: Path, age_seconds: float):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    stamp = time.time() - age_seconds
    os.utime(path, (stamp, stamp))


def _with_user(tmp: str):
    old = os.environ.get(paths.ENV_USER)
    os.environ[paths.ENV_USER] = tmp
    return old


def _restore(old):
    if old is None:
        os.environ.pop(paths.ENV_USER, None)
    else:
        os.environ[paths.ENV_USER] = old


def test_latest_is_newest_in_single_not_an_autosave():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Logs").mkdir()
        _save(Path(tmp) / "Saves/Single/Older.Civ7Save", 300)
        _save(Path(tmp) / "Saves/Single/Newer.Civ7Save", 100)
        _save(Path(tmp) / "Saves/Single/auto/AutoSave_0035.Civ7Save", 1)
        old = _with_user(tmp)
        try:
            newest = runner.latest_save()
        finally:
            _restore(old)
        assert newest is not None and newest.stem == "Newer", newest


def test_no_saves_is_none_not_an_error():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "Logs").mkdir()
        old = _with_user(tmp)
        try:
            assert runner.latest_save() is None
        finally:
            _restore(old)


def test_loading_a_save_without_turns_does_not_autoplay():
    suite = runner.load_save("AugustusAnt35")
    text = str(suite.to_json())
    assert "Turns" not in text, text
    assert "Test=End" in text, "the game should be left running, not unloaded"


if __name__ == "__main__":
    failures = 0
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            try:
                function()
                print(f"ok   {name}")
            except AssertionError as error:
                failures += 1
                print(f"FAIL {name}: {error}")
    raise SystemExit(1 if failures else 0)
