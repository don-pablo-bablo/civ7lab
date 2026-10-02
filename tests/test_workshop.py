"""Offline tests for `workshop tags`: the tag rules, reading the web API's
reply, and a dry run. Nothing here talks to Steam or the network.
"""

import ctypes

from civ7lab import commands, workshop

REPLY = {
    "response": {
        "result": 1,
        "resultcount": 1,
        "publishedfiledetails": [
            {
                "publishedfileid": "1234567890",
                "result": 1,
                "title": "Example Mod",
                "creator": "76561198000000000",
                "consumer_app_id": 1295660,
                "tags": [{"tag": "Mod"}, {"tag": "Legacy Thing"}],
            }
        ],
    }
}


def test_mod_always_first():
    assert workshop.resolve_tags(["UI"]) == ["Mod", "UI"]
    assert workshop.resolve_tags([]) == ["Mod"]
    assert workshop.resolve_tags(["game setup", "Mod", "GAMEPLAY TWEAKS"]) == [
        "Mod",
        "Game Setup",
        "Gameplay Tweaks",
    ]


def test_commas_and_duplicates():
    assert workshop.resolve_tags(["Mod, Game Setup", "Game Setup,UI"]) == [
        "Mod",
        "Game Setup",
        "UI",
    ]


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
    reply = {"response": {"publishedfiledetails": [{"publishedfileid": "1", "result": 9}]}}
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


def test_dry_run_submits_nothing(monkeypatch, capsys):
    # Steam and the web API are the boundary; everything inside runs for real.
    monkeypatch.setattr(workshop, "details", lambda item_id: workshop.parse_details(REPLY, item_id))

    def refuse(*args, **kwargs):
        raise AssertionError("dry run submitted")

    monkeypatch.setattr(workshop, "submit", refuse)
    code = commands.main(["workshop", "tags", "1234567890", "UI", "--dry-run"])
    text = capsys.readouterr().out
    assert code == 0
    assert "  now: Mod, Legacy Thing" in text
    assert "  new: Mod, UI" in text
    assert "  dropped: Legacy Thing" in text
    assert "dry run: nothing submitted" in text


def item_with(description):
    reply = {
        "response": {
            "publishedfiledetails": [
                {**REPLY["response"]["publishedfiledetails"][0], "description": description}
            ]
        }
    }
    return lambda item_id: workshop.parse_details(reply, item_id)


def test_a_description_dry_run_shows_the_change_and_submits_nothing(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(workshop, "details", item_with("Old line\r\nKept line"))

    def refuse(*args, **kwargs):
        raise AssertionError("dry run submitted")

    monkeypatch.setattr(workshop, "submit", refuse)
    text = tmp_path / "description.txt"
    text.write_text("New line\nKept line\n", encoding="utf-8")
    code = commands.main(["workshop", "description", "1234567890", str(text), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "  -Old line" in out and "  +New line" in out and "   Kept line" in out
    assert "dry run: nothing submitted" in out


def test_a_matching_description_is_left_alone(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(workshop, "details", item_with("Same\r\ntext"))
    text = tmp_path / "description.txt"
    text.write_text("Same\ntext\n\n", encoding="utf-8")
    assert commands.main(["workshop", "description", "1234567890", str(text)]) == 0
    assert "already matches" in capsys.readouterr().out


def test_a_description_over_steams_limit_is_refused(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(workshop, "details", item_with(""))
    text = tmp_path / "description.txt"
    text.write_text("x" * (workshop.DESCRIPTION_LIMIT + 1), encoding="utf-8")
    assert commands.main(["workshop", "description", "1234567890", str(text)]) == 1
    assert "at most 8000" in capsys.readouterr().out
