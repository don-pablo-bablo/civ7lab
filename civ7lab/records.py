"""The record format a mod uses to get data out of the game through UI.log.

A script in the game can only reach the outside by printing, so it prints
one JSON object per line behind a marker:

    [C7LAB] {"v":1,"seq":7,"kind":"tile","turn":44,"data":{...}}

* **Chunks**: UI.log cuts long lines. A long record is split into fragments
  marked `[C7LAB#]`, each stating its own length, so a cut fragment is
  reported as an error on that record instead of parsing as wrong data.
* **Sequence numbers**: a gap in `seq` is reported, so a dropped record is
  noticed.

Any mod can print these; see docs/probe.md. `civ7lab live` returns the same
objects over the inspector without printing them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

MARKER = "[C7LAB]"
CHUNK_MARKER = "[C7LAB#]"
PROTOCOL_VERSION = 1

# Characters per fragment. UI.log's line limit is undocumented; this is well
# under it.
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
    def from_json(cls, obj: dict) -> Record:
        known = {"v", "seq", "kind", "turn", "run", "data"}
        return cls(
            kind=str(obj.get("kind", "record")),
            data=obj.get("data"),
            seq=obj.get("seq"),
            turn=obj.get("turn"),
            run=obj.get("run"),
            meta={key: value for key, value in obj.items() if key not in known},
        )


@dataclass
class ParseReport:
    """The records that parsed, and a list of those that did not. A bad
    record is reported rather than raised, so the rest are still returned."""

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
            # Nearly always a cut line. Its length shows where the log cut it.
            report.errors.append(
                f"unparsable {'fragment' if is_chunk else 'record'} ({len(payload)} chars): {error}"
            )
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
                f"{len(fragment)} chars of a declared {declared}"
            )
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
    with open(path, encoding="utf-8", errors="replace") as handle:
        return parse_lines(handle)
