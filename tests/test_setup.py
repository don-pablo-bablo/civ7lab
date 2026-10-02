"""doctor, options and mod, against a game folder layout on disk."""

import sqlite3
import time

import pytest

from civ7lab import appoptions, doctor, mod, paths

APP_OPTIONS = """\
[Debug]
;UIDebugger 1
  ;CopyDatabasesToDisk 0
UILogLevel 2

[Video]
Width 1920
"""


def options_file(path):
    path.write_text(APP_OPTIONS, encoding="utf-8")
    return appoptions.AppOptions(path)


# -- options ------------------------------------------------------------------


def test_a_commented_option_is_reported_as_off(tmp_path):
    options = options_file(tmp_path / "AppOptions.txt")
    assert options.get("UIDebugger").value == "1"
    assert options.effective("UIDebugger") is None
    assert options.effective("UILogLevel") == "2"


def test_setting_uncomments_in_place_and_keeps_the_indent(tmp_path):
    options = options_file(tmp_path / "AppOptions.txt")
    assert options.set("CopyDatabasesToDisk", "1") == "CopyDatabasesToDisk: 0 (commented out) -> 1"
    options.save(backup=False)
    assert "  CopyDatabasesToDisk 1\n" in (tmp_path / "AppOptions.txt").read_text(encoding="utf-8")


def test_a_new_option_goes_at_the_end_of_its_section(tmp_path):
    options = options_file(tmp_path / "AppOptions.txt")
    options.set("EnableTuner", "1")
    options.save(backup=False)
    text = (tmp_path / "AppOptions.txt").read_text(encoding="utf-8")
    assert text.index("EnableTuner 1") < text.index("[Video]")


def test_setting_a_value_already_set_says_so(tmp_path):
    options = options_file(tmp_path / "AppOptions.txt")
    assert options.set("UILogLevel", "2") == "UILogLevel already 2"


def test_the_first_save_of_the_day_is_backed_up_once(tmp_path):
    path = tmp_path / "AppOptions.txt"
    options = options_file(path)
    options.set("UIDebugger", "1")
    backup = options.save()
    assert backup.name == f"AppOptions.txt.civ7lab-{time.strftime('%Y%m%d')}.bak"
    options.set("UILogLevel", "3")
    options.save()
    assert backup.read_text(encoding="utf-8") == APP_OPTIONS, (
        "the backup should keep the file as it was"
    )


def test_no_options_file_is_explained(game):
    with pytest.raises(FileNotFoundError, match="run the game once"):
        appoptions.load()


# -- mods ---------------------------------------------------------------------


def make_mod(folder, name="my-mod"):
    source = folder / name
    source.mkdir()
    (source / f"{name}.modinfo").write_text(
        f'<Mod id="{name}" version="1" xmlns="ModInfo"/>', encoding="utf-8"
    )
    return source


def test_install_links_and_uninstall_leaves_the_source(game, tmp_path):
    source = make_mod(tmp_path)
    assert mod.install(source).startswith("linked my-mod")
    link = game.user / "Mods/my-mod"
    assert link.is_symlink() and link.resolve() == source.resolve()
    assert "already linked" in mod.install(source)
    mod.uninstall("my-mod")
    assert not link.exists() and source.is_dir()


def test_install_will_not_replace_another_mod_without_force(game, tmp_path):
    source = make_mod(tmp_path)
    (game.user / "Mods/my-mod").mkdir()
    assert "pass --force" in mod.install(source)
    assert mod.install(source, force=True).startswith("linked")


def test_a_folder_with_no_modinfo_is_refused(game, tmp_path):
    (tmp_path / "not-a-mod").mkdir()
    with pytest.raises(FileNotFoundError, match="no .modinfo"):
        mod.install(tmp_path / "not-a-mod")


def test_list_flags_a_broken_link(game, tmp_path):
    source = make_mod(tmp_path)
    mod.install(source)
    source.rename(tmp_path / "moved")
    (row,) = mod.installed()
    assert row.kind == "link" and not row.valid


# -- doctor -------------------------------------------------------------------


def finding(label):
    return next(f for f in doctor.check() if f.label == label)


def test_doctor_names_each_problem_with_its_fix(game):
    (game.user / "AppOptions.txt").write_text(APP_OPTIONS, encoding="utf-8")
    assert finding("UIDebugger").ok is False
    assert "options --live" in finding("UIDebugger").fix
    assert finding("gameplay dump").ok is False
    assert finding("executable").ok is False
    assert finding("probe mod").ok is False
    assert "thing(s) to fix above" in doctor.report()


def test_doctor_spots_a_dump_taken_at_the_main_menu(game):
    dump = game.user / "Debug/gameplay-copy.sqlite"
    connection = sqlite3.connect(dump)
    connection.execute("CREATE TABLE Constructibles (ConstructibleType TEXT)")
    connection.commit()
    assert finding("gameplay dump").ok is False
    connection.execute("INSERT INTO Constructibles VALUES ('BUILDING_LIBRARY')")
    connection.commit()
    connection.close()
    assert finding("gameplay dump").ok is True


def test_doctor_finds_the_game_it_is_pointed_at(game):
    game.add_executable()
    assert finding("install").ok and finding("user directory").ok
    assert finding("executable").ok


@pytest.mark.skipif(not paths.WINDOWS, reason="junctions exist only on Windows")
def test_without_symlink_rights_windows_gets_a_junction(game, tmp_path, monkeypatch):
    source = make_mod(tmp_path)

    def refuse(*args, **kwargs):
        raise OSError("A required privilege is not held by the client")

    monkeypatch.setattr(type(source), "symlink_to", refuse)
    assert mod.install(source).startswith("linked")
    link = game.user / "Mods/my-mod"
    assert link.is_junction()
    (row,) = mod.installed()
    assert row.kind == "link" and row.valid and row.target.resolve() == source.resolve()
    mod.uninstall("my-mod")
    assert not link.exists() and (source / "my-mod.modinfo").is_file()


def crlf_file(path):
    path.write_bytes(APP_OPTIONS.replace("\n", "\r\n").encode("utf-8"))
    return appoptions.AppOptions(path)


def test_setting_a_value_already_set_writes_nothing(tmp_path):
    # The game writes CRLF. A rewrite with LF once changed the whole file.
    path = tmp_path / "AppOptions.txt"
    options = crlf_file(path)
    before = path.read_bytes()
    options.set("UILogLevel", "2")
    assert options.save() is None
    assert path.read_bytes() == before
    assert not list(tmp_path.glob("*.bak")), "nothing changed, so nothing to back up"


def test_a_change_keeps_the_files_line_endings(tmp_path):
    path = tmp_path / "AppOptions.txt"
    options = crlf_file(path)
    options.set("UIDebugger", "1")
    options.save()
    data = path.read_bytes()
    assert b"UIDebugger 1\r\n" in data
    assert data.count(b"\n") == data.count(b"\r\n"), "every line should still end in CRLF"
