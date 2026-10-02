"""Reading and keeping the game's logs."""

from civ7lab import logs

DATABASE_LOG = """\
[2026-09-21 10:00:01] Loading base-standard
[2026-09-21 10:00:02] [Gameplay] ERROR: FOREIGN KEY constraint failed
[2026-09-21 10:00:03] Loaded 34 rows
"""

UI_LOG = """\
[10:00:05] Inspector initialized. Remote debugging available on port: 9444
[10:00:06] [C7LAB] civ7lab:build probe probe-aaaa
[10:00:07] [MYMOD] panel drawn
[10:00:08] TypeError: city.Yields is undefined at fs://game/my-mod/ui/panel.js:40
[10:00:09] [C7LAB] civ7lab:build probe probe-bbbb
"""


def write_logs(game):
    (game.user / "Logs/Database.log").write_text(DATABASE_LOG, encoding="utf-8")
    (game.user / "Logs/UI.log").write_text(UI_LOG, encoding="utf-8")


def test_errors_are_only_the_lines_that_report_one(game):
    write_logs(game)
    found = [str(error) for error in logs.errors()]
    assert found == [
        "Database.log:2 [database] [2026-09-21 10:00:02] [Gameplay] ERROR: "
        "FOREIGN KEY constraint failed",
        "UI.log:4 [script] [10:00:08] TypeError: city.Yields is undefined "
        "at fs://game/my-mod/ui/panel.js:40",
    ]


def test_errors_read_a_copied_folder_too(game, tmp_path):
    write_logs(game)
    copy = logs.snapshot(tmp_path / "keep", note="before a restart")
    (game.user / "Logs/Database.log").write_text("", encoding="utf-8")
    assert len(logs.errors(copy)) == 2
    assert "before a restart" in (copy / "SNAPSHOT.txt").read_text(encoding="utf-8")


def test_stamps_keep_the_last_build_printed(game):
    write_logs(game)
    assert logs.build_stamps() == {"probe": "probe-bbbb"}


def test_marker_lines_pick_out_a_mods_own_tag(game):
    write_logs(game)
    assert logs.marker_lines(marker="[MYMOD]") == ["[10:00:07] [MYMOD] panel drawn"]


def test_no_log_is_an_empty_answer_not_an_error(game):
    assert logs.errors() == [] and logs.build_stamps() == {}
    assert logs.read_records().errors
