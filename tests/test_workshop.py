"""Offline tests for `workshop tags`: the tag rules, reading the web API's
reply, and a dry run. Nothing here talks to Steam or the network.
"""

import ctypes
import types

import pytest

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


def make_mod(folder, version="1.1.0"):
    folder.mkdir()
    (folder / "my-mod.modinfo").write_text(
        f'<?xml version="1.0"?>\n<Mod id="my-mod" version="{version}" xmlns="ModInfo"/>\n',
        encoding="utf-8",
    )
    (folder / "ui").mkdir()
    (folder / "ui" / "panel.js").write_text("// panel\n", encoding="utf-8")
    return folder


def test_parse_details_reads_the_update_time():
    reply = {
        "response": {
            "publishedfiledetails": [
                {**REPLY["response"]["publishedfiledetails"][0], "time_updated": 1760400000}
            ]
        }
    }
    assert workshop.parse_details(reply, "1234567890").updated == 1760400000


def test_a_mod_folder_is_read_from_its_modinfo(tmp_path):
    mod = workshop.mod_folder(make_mod(tmp_path / "my-mod"))
    assert (mod.id, mod.version) == ("my-mod", "1.1.0")
    assert [f.name for f in mod.files] == ["my-mod.modinfo", "panel.js"]


def test_a_mod_folder_with_a_version_starting_with_0_is_refused(tmp_path):
    try:
        workshop.mod_folder(make_mod(tmp_path / "my-mod", version="0.9.0"))
    except workshop.WorkshopError as error:
        assert "never loads it" in str(error)
    else:
        raise AssertionError("a 0.x version was accepted")


def test_a_folder_without_a_modinfo_at_its_top_is_refused(tmp_path):
    # The parent of a mod's folder: the game would not find the mod.
    make_mod(tmp_path / "my-mod")
    try:
        workshop.mod_folder(tmp_path)
    except workshop.WorkshopError as error:
        assert "0 .modinfo files" in str(error)
    else:
        raise AssertionError("a folder without a .modinfo was accepted")


def test_an_upload_dry_run_lists_the_files_and_notes_and_submits_nothing(
    monkeypatch, capsys, tmp_path
):
    monkeypatch.setattr(workshop, "details", item_with(""))

    def refuse(*args, **kwargs):
        raise AssertionError("dry run submitted")

    monkeypatch.setattr(workshop, "submit", refuse)
    folder = make_mod(tmp_path / "my-mod")
    note = tmp_path / "notes.txt"
    note.write_text("[list][*]New sizes[/list]\n", encoding="utf-8")
    code = commands.main(
        ["workshop", "upload", "1234567890", str(folder), "--note", str(note), "--dry-run"]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  mod: my-mod 1.1.0" in out
    assert "    ui/panel.js" in out
    assert "    [list][*]New sizes[/list]" in out
    assert "dry run: nothing submitted" in out


def test_an_upload_sends_the_folder_and_notes(monkeypatch, capsys, tmp_path):
    times = iter([100, 200])

    def details(item_id):
        reply = {
            "response": {
                "publishedfiledetails": [
                    {**REPLY["response"]["publishedfiledetails"][0], "time_updated": next(times)}
                ]
            }
        }
        return workshop.parse_details(reply, item_id)

    sent = {}

    def submit(item, **kwargs):
        sent.update(kwargs)
        return workshop.Submitted(workshop.CREATOR_APP_ID, [(workshop.CREATOR_APP_ID, "OK")])

    monkeypatch.setattr(workshop, "details", details)
    monkeypatch.setattr(workshop, "submit", submit)
    folder = make_mod(tmp_path / "my-mod")
    note = tmp_path / "notes.txt"
    note.write_text("Fixes\n", encoding="utf-8")
    code = commands.main(["workshop", "upload", "1234567890", str(folder), "--note", str(note)])
    assert code == 0
    assert sent["content"] == folder and sent["note"] == "Fixes"
    assert "  read back: updated" in capsys.readouterr().out


def test_an_unreadable_note_is_refused(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(workshop, "details", item_with(""))
    folder = make_mod(tmp_path / "my-mod")
    note = tmp_path / "notes.txt"
    note.write_bytes(b"\xff\xfe not text")
    code = commands.main(["workshop", "upload", "1234567890", str(folder), "--note", str(note)])
    assert code == 1
    assert "cannot read the release notes" in capsys.readouterr().out


def test_an_interface_is_its_newest_version_in_the_library():
    newer, older = object(), object()
    lib = types.SimpleNamespace(SteamAPI_SteamUtils_v011=newer, SteamAPI_SteamUtils_v010=older)
    assert workshop.interface(lib, "SteamAPI_SteamUtils", ("v011", "v010")) is newer


def test_the_games_library_has_an_older_steam_utils():
    older = object()
    lib = types.SimpleNamespace(SteamAPI_SteamUtils_v010=older)
    assert workshop.interface(lib, "SteamAPI_SteamUtils", ("v011", "v010")) is older


def test_a_library_without_the_interface_is_refused():
    with pytest.raises(workshop.WorkshopError, match="SteamAPI_SteamUGC"):
        workshop.interface(types.SimpleNamespace(), "SteamAPI_SteamUGC", ("v021",))


def test_parse_details_reads_the_preview_url():
    reply = {
        "response": {
            "publishedfiledetails": [
                {
                    **REPLY["response"]["publishedfiledetails"][0],
                    "preview_url": "https://images.steamusercontent.com/ugc/1/",
                }
            ]
        }
    }
    assert workshop.parse_details(reply, "1234567890").preview_url.endswith("/ugc/1/")


def test_a_preview_over_1_mb_is_refused(tmp_path):
    image = tmp_path / "preview.jpg"
    image.write_bytes(b"\0" * workshop.PREVIEW_LIMIT)
    with pytest.raises(workshop.WorkshopError, match="under 1024 KB"):
        workshop.preview_image(image)


def test_a_preview_that_is_not_an_image_is_refused(tmp_path):
    image = tmp_path / "preview.webp"
    image.write_bytes(b"RIFF")
    with pytest.raises(workshop.WorkshopError, match="not a JPEG, PNG or GIF"):
        workshop.preview_image(image)


def test_a_preview_dry_run_submits_nothing(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(workshop, "details", item_with(""))

    def refuse(*args, **kwargs):
        raise AssertionError("dry run submitted")

    monkeypatch.setattr(workshop, "submit", refuse)
    image = tmp_path / "preview.jpg"
    image.write_bytes(b"\xff\xd8 jpeg")
    code = commands.main(["workshop", "preview", "1234567890", str(image), "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "  now: none" in out
    assert "dry run: nothing submitted" in out


def test_a_preview_sends_the_image_and_reads_back_its_new_url(monkeypatch, capsys, tmp_path):
    urls = iter(
        ["https://images.steamusercontent.com/ugc/1/", "https://images.steamusercontent.com/ugc/2/"]
    )

    def details(item_id):
        reply = {
            "response": {
                "publishedfiledetails": [
                    {**REPLY["response"]["publishedfiledetails"][0], "preview_url": next(urls)}
                ]
            }
        }
        return workshop.parse_details(reply, item_id)

    sent = {}

    def submit(item, **kwargs):
        sent.update(kwargs)
        return workshop.Submitted(workshop.CREATOR_APP_ID, [(workshop.CREATOR_APP_ID, "OK")])

    monkeypatch.setattr(workshop, "details", details)
    monkeypatch.setattr(workshop, "submit", submit)
    image = tmp_path / "preview.jpg"
    image.write_bytes(b"\xff\xd8 jpeg")
    code = commands.main(["workshop", "preview", "1234567890", str(image)])
    assert code == 0
    assert sent == {"preview": image}
    assert "  read back: https://images.steamusercontent.com/ugc/2/" in capsys.readouterr().out
