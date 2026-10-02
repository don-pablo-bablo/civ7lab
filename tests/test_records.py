"""Round-trip tests for the record protocol.

The point of interest is not that a good record parses; it is that a bad one is
reported rather than lost. UI.log truncates long lines, and this protocol's
whole reason for chunking is to make that visible.
"""

import json

from civ7lab import records


def emit(record: dict, chunk_size: int = records.CHUNK_PAYLOAD) -> list[str]:
    """The Python mirror of what the probe mod prints, used to test the reader."""
    text = json.dumps(record, separators=(",", ":"))
    if len(text) <= chunk_size:
        return [f"[ts] {records.MARKER} {text}"]
    identifier = f"r{record.get('seq', 0)}"
    parts = [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    return [
        f"[ts] {records.CHUNK_MARKER} "
        + json.dumps(
            {"id": identifier, "i": index, "n": len(parts), "len": len(part), "s": part},
            separators=(",", ":"),
        )
        for index, part in enumerate(parts)
    ]


def test_plain_record():
    lines = emit({"v": 1, "seq": 1, "kind": "tile", "turn": 44, "data": {"x": 20, "y": 7}})
    report = records.parse_lines(lines)
    assert report.ok, report.errors
    assert report.records[0].data == {"x": 20, "y": 7}
    assert report.records[0].turn == 44


def test_chunked_record_reassembles():
    big = {
        "v": 1,
        "seq": 2,
        "kind": "city",
        "data": {"buildings": [{"name": f"BUILDING_{i}", "yields": [1, 2, 3]} for i in range(60)]},
    }
    lines = emit(big)
    assert len(lines) > 1, "this record should have needed chunking"
    report = records.parse_lines(lines)
    assert report.ok, report.errors
    assert report.records[0].data == big["data"]


def test_truncated_fragment_is_reported_not_silently_lost():
    lines = emit({"v": 1, "seq": 3, "kind": "city", "data": {"pad": "x" * 2000}})
    # Simulate the log clipping one fragment, which is what a line limit does.
    victim = json.loads(lines[1].split(records.CHUNK_MARKER, 1)[1])
    victim["s"] = victim["s"][:50]
    lines[1] = f"[ts] {records.CHUNK_MARKER} " + json.dumps(victim)
    report = records.parse_lines(lines)
    assert not report.ok
    assert any("was cut" in error for error in report.errors), report.errors


def test_gap_in_sequence_is_reported():
    lines = emit({"v": 1, "seq": 1, "kind": "a", "data": 1}) + emit(
        {"v": 1, "seq": 4, "kind": "a", "data": 2}
    )
    report = records.parse_lines(lines)
    assert report.missing_seq == [2, 3]


def test_interleaved_engine_noise_is_ignored():
    lines = [
        "[ts] FM: forcing focus re-evaluation",
        *emit({"v": 1, "seq": 1, "kind": "tile", "data": {}}),
        "[ts] Assert failure: Object size mismatch",
    ]
    report = records.parse_lines(lines)
    assert len(report.records) == 1
