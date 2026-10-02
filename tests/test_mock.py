"""Tests for harvesting fixtures, in particular --latest-by.

A panel that prints itself on every open repeats a case each time it is
hovered. The harvest should keep the last reading of each case, in the order
the cases were first seen, and should never merge two cases that differ in any
named field.
"""

import json
import tempfile
from pathlib import Path

from civ7lab import mock, records


def tile(city, x, y, total):
    return {"cityName": city, "loc": {"x": x, "y": y}, "total": total}


KEY = ["cityName", "loc.x", "loc.y"]


def test_last_reading_wins_first_place_kept():
    found = [tile("Roma", 42, 7, 1), tile("Roma", 44, 8, 2), tile("Roma", 42, 7, 3)]
    kept = mock.latest_by(found, KEY)
    assert [t["loc"]["x"] for t in kept] == [42, 44], kept
    assert kept[0]["total"] == 3, "the later reading of (42,7) should replace the earlier one"


def test_distinct_in_any_field_are_kept_apart():
    found = [tile("Roma", 42, 7, 1), tile("Roma", 42, 8, 1), tile("Antium", 42, 7, 1)]
    assert len(mock.latest_by(found, KEY)) == 3


def test_missing_field_is_a_value_not_an_error():
    found = [{"cityName": "Roma"}, {"cityName": "Roma"}, "not a dict"]
    kept = mock.latest_by(found, KEY)
    assert len(kept) == 2, kept


def test_harvest_from_a_log():
    lines = []
    for seq, data in enumerate(
        [tile("Roma", 42, 7, 1), tile("Roma", 43, 8, 5), tile("Roma", 42, 7, 2)], start=1
    ):
        record = {"v": 1, "seq": seq, "kind": "byt-fixture", "data": data}
        lines.append(f"[ts] {records.MARKER} {json.dumps(record)}")
    lines.append(
        f"[ts] {records.MARKER} "
        + json.dumps({"v": 1, "seq": 4, "kind": "other", "data": tile("Roma", 1, 1, 1)})
    )
    with tempfile.TemporaryDirectory() as tmp:
        log = Path(tmp) / "UI.log"
        log.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out, total, kept = mock.fixtures_from_records(
            kind="byt-fixture", log=log, out=Path(tmp) / "fixtures.js", latest=KEY
        )
        assert (total, kept) == (3, 2), (total, kept)
        text = out.read_text(encoding="utf-8")
        fixtures = json.loads(text[text.index("= ") + 2 : text.rindex(";")])
        assert [f["total"] for f in fixtures] == [2, 5], fixtures

        out, total, kept = mock.fixtures_from_records(
            kind="byt-fixture", log=log, out=Path(tmp) / "all.js"
        )
        assert (total, kept) == (3, 3), "without --latest-by every record is kept"
