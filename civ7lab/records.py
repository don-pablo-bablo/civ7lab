"""The wire format between a probe mod and this toolkit.

A mod running inside the game can reach the outside world in exactly one cheap
way: it can print. So the probe prints structured records, one JSON object per
line, behind a marker:

    [C7LAB] {"v":1,"seq":7,"kind":"tile","turn":44,"data":{...}}

Two details are not decoration.

**Chunking.** UI.log truncates long lines, and a truncated JSON object is a
silent loss: it parses as a syntax error at best and as wrong data at worst. So
a long record is split, and every fragment carries the length it should have.
The reassembler checks that length, which turns truncation from a mystery into
a named error on a named record.

**Sequence numbers.** The log is shared with the whole engine and a record can
be interleaved with anything. A missing seq tells the reader that something was
dropped, rather than leaving a gap to be discovered by a measurement that
quietly disagrees with the last one.

The same format is what `civ7lab live` gets back directly, minus the printing,
which is why a collector is written once and used by both routes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MARKER = "[C7LAB]"
CHUNK_MARKER = "[C7LAB#]"
PROTOCOL_VERSION = 1

# Fragment payloads are kept short because the engine's log has a line limit
# that has bitten this project before and is not documented anywhere.
CHUNK_PAYLOAD = 400

_LINE = re.compile(r"\[C7LAB(#?)\]\s*(\{.*)$")


@dataclass
class Record:
    kind: str
    data: object
    seq: int | None = None
    turn: int | None = None
    run: str | None = None
    meta: dict = field(default_factory=dict)

    @classmethod
    def from_json(cls, obj: dict) -> "Record":
        known = {"v", "seq", "kind", "turn", "run", "data"}
        return cls(kind=str(obj.get("kind", "record")),
                   data=obj.get("data"),
                   seq=obj.get("seq"),
                   turn=obj.get("turn"),
                   run=obj.get("run"),
                   meta={key: value for key, value in obj.items() if key not in known})


@dataclass
class ParseReport:
    """What came back, and what did not.

    Errors are returned rather than raised: one mangled record in a thousand
    should not cost the other nine hundred and ninety-nine, but it must still
    be visible, because a dropped record is a measurement that silently is not
    there.
    """
    records: list[Record] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    missing_seq: list[int] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[Record]:
        return [record for record in self.records if record.kind == kind]

    @property
    def ok(self) -> bool:
        return not self.errors and not self.missing_seq


def parse_lines(lines) -> ParseReport:
    report = ParseReport()
    pending: dict[str, dict] = {}

    for raw in lines:
        match = _LINE.search(raw)
        if not match:
            continue
        is_chunk, payload = match.group(1) == "#", match.group(2).strip()
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError as error:
            # A record that will not parse is nearly always a truncated line.
            # Say which, and say how long it was, because that is the number
            # that tells you what the log's real limit is.
            report.errors.append(
                f"unparsable {'fragment' if is_chunk else 'record'} "
                f"({len(payload)} chars): {error}")
            continue
        if not is_chunk:
            report.records.append(Record.from_json(obj))
            continue

        key = str(obj.get("id"))
        slot = pending.setdefault(key, {"parts": {}, "n": obj.get("n")})
        fragment = obj.get("s", "")
        declared = obj.get("len")
        if declared is not None and declared != len(fragment):
            report.errors.append(
                f"record {key} fragment {obj.get('i')} was cut: "
                f"{len(fragment)} chars of a declared {declared}")
            continue
        slot["parts"][int(obj.get("i", 0))] = fragment

        total = slot["n"]
        if total is not None and len(slot["parts"]) == int(total):
            joined = "".join(slot["parts"][index] for index in sorted(slot["parts"]))
            pending.pop(key, None)
            try:
                report.records.append(Record.from_json(json.loads(joined)))
            except json.JSONDecodeError as error:
                report.errors.append(f"record {key} reassembled but will not parse: {error}")

    for key, slot in pending.items():
        have, want = len(slot["parts"]), slot["n"]
        report.errors.append(f"record {key} incomplete: {have} of {want} fragments")

    seen = sorted(record.seq for record in report.records if record.seq is not None)
    if seen:
        report.missing_seq = [n for n in range(seen[0], seen[-1] + 1) if n not in set(seen)]
    return report


def parse_file(path) -> ParseReport:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return parse_lines(handle)
