"""Offline tests for `workshop tags`: the tag rules, reading the web API's
reply, and a dry run. Nothing here talks to Steam or the network.
"""
import contextlib
import ctypes
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from civ7lab import __main__ as cli
from civ7lab import workshop

REPLY = {"response": {"result": 1, "resultcount": 1, "publishedfiledetails": [
    {"publishedfileid": "1234567890", "result": 1, "title": "Example Mod",
     "creator": "76561198000000000", "consumer_app_id": 1295660,
     "tags": [{"tag": "Mod"}, {"tag": "Legacy Thing"}]}]}}


def test_mod_always_first():
    assert workshop.resolve_tags(["UI"]) == ["Mod", "UI"]
    assert workshop.resolve_tags([]) == ["Mod"]
    assert workshop.resolve_tags(["game setup", "Mod", "GAMEPLAY TWEAKS"]) == \
        ["Mod", "Game Setup", "Gameplay Tweaks"]


def test_commas_and_duplicates():
    assert workshop.resolve_tags(["Mod, Game Setup", "Game Setup,UI"]) == \
        ["Mod", "Game Setup", "UI"]


def test_unknown_refused():
    try:
        workshop.resolve_tags(["UI", "Gameplay"])
    except workshop.WorkshopError as error:
        assert "Gameplay" in str(error).splitlines()[0]
    else:
        raise AssertionError("an unknown tag was accepted")


def test_parse_details():
    item = workshop.parse_details(REPLY, "1234567890")
    assert item.title == "Example Mod"
    assert item.consumer_app_id == 1295660
    assert item.tags == ["Mod", "Legacy Thing"]


def test_missing_item():
    reply = {"response": {"publishedfiledetails": [
        {"publishedfileid": "1", "result": 9}]}}
    try:
        workshop.parse_details(reply, "1")
    except workshop.WorkshopError:
        pass
    else:
        raise AssertionError("a missing item was parsed")


def test_submit_result_layout():
    # SubmitItemUpdateResult_t: EResult, bool, then the uint64 at offset 8.
    assert workshop.SubmitItemUpdateResult.item_id.offset == 8
    assert ctypes.sizeof(workshop.SubmitItemUpdateResult) == 16


def test_dry_run_submits_nothing():
    real_details, real_submit = workshop.details, workshop.submit
    workshop.details = lambda item_id: workshop.parse_details(REPLY, item_id)
    workshop.submit = lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("dry run submitted"))
    out = io.StringIO()
    try:
        with contextlib.redirect_stdout(out):
            code = cli.main(["workshop", "tags", "1234567890", "UI", "--dry-run"])
    finally:
        workshop.details, workshop.submit = real_details, real_submit
    text = out.getvalue()
    assert code == 0
    assert "  now: Mod, Legacy Thing" in text
    assert "  new: Mod, UI" in text
    assert "  dropped: Legacy Thing" in text
    assert "dry run: nothing submitted" in text


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
