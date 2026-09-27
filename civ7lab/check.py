"""Declarative expectations, so a test can be re-run instead of re-remembered.

A spec names what to collect and what should be true of it:

    {
      "name": "the science quarter bonus survives the age turn",
      "collect": [{"as": "tile", "collector": "tile", "args": {"x": 20, "y": 7}}],
      "expect": [
        {"path": "tile.yields.YIELD_SCIENCE", "op": ">=", "value": 30},
        {"path": "tile.constructibles[type=BUILDING_LIBRARY].damaged", "op": "==",
         "value": false, "why": "a repaired building should not read as damaged"}
      ]
    }

The value of writing it down is not the assertion; it is that the next person
to ask the same question asks it the same way. A measurement taken by hand
twice is two measurements. This one is the same one, and it can be pointed at
a live game or at a snapshot taken from a run that finished last week.

The path language is small on purpose: dots for keys, `[2]` for an index, and
`[key=value]` to pick an element out of a list by one of its own fields, which
is how a building or a tile is named rather than numbered.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MISSING = object()

_STEP = re.compile(r"([^.\[\]]+)|\[([^\]]+)\]")


def resolve(data, path: str):
    """Follow a path into a snapshot, returning MISSING rather than raising.

    A missing path is a normal outcome: the building is not there, or the tile
    is not owned. It is more useful as a failed expectation naming the path
    than as an exception naming a dictionary key.
    """
    current = data
    for key, bracket in _STEP.findall(path):
        if current is MISSING or current is None:
            return MISSING
        token = key or bracket
        if bracket and "=" in bracket:
            field_name, _, wanted = bracket.partition("=")
            if not isinstance(current, list):
                return MISSING
            found = MISSING
            for item in current:
                if isinstance(item, dict) and str(item.get(field_name)) == wanted:
                    found = item
                    break
            current = found
            continue
        if bracket and bracket.lstrip("-").isdigit():
            if not isinstance(current, list):
                return MISSING
            index = int(bracket)
            current = current[index] if -len(current) <= index < len(current) else MISSING
            continue
        if isinstance(current, dict):
            current = current.get(token, MISSING)
        else:
            return MISSING
    return current


OPERATORS = {
    "==": lambda actual, expected: actual == expected,
    "!=": lambda actual, expected: actual != expected,
    ">": lambda actual, expected: _number(actual) > _number(expected),
    ">=": lambda actual, expected: _number(actual) >= _number(expected),
    "<": lambda actual, expected: _number(actual) < _number(expected),
    "<=": lambda actual, expected: _number(actual) <= _number(expected),
    "contains": lambda actual, expected: expected in (actual or []),
    "absent": lambda actual, expected: actual is MISSING or actual is None,
    "present": lambda actual, expected: actual is not MISSING and actual is not None,
    "len": lambda actual, expected: len(actual or []) == expected,
}


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


@dataclass
class Expectation:
    path: str
    op: str
    value: object = None
    why: str = ""

    def evaluate(self, data) -> tuple[bool, object]:
        actual = resolve(data, self.path)
        check = OPERATORS.get(self.op)
        if not check:
            return False, f"unknown operator {self.op}"
        if actual is MISSING and self.op not in ("absent", "present"):
            return False, MISSING
        try:
            return bool(check(actual, self.value)), actual
        except Exception as error:  # a comparison against the wrong shape
            return False, f"{actual!r} ({error})"


@dataclass
class Spec:
    name: str
    collect: list[dict] = field(default_factory=list)
    expect: list[Expectation] = field(default_factory=list)
    note: str = ""

    @classmethod
    def load(cls, path: str | Path) -> "Spec":
        document = json.loads(Path(path).read_text())
        return cls(name=document.get("name", Path(path).stem),
                   collect=document.get("collect", []),
                   expect=[Expectation(**item) for item in document.get("expect", [])],
                   note=document.get("note", ""))


@dataclass
class Outcome:
    expectation: Expectation
    passed: bool
    actual: object

    def __str__(self) -> str:
        actual = "(missing)" if self.actual is MISSING else repr(self.actual)
        head = f"{'PASS' if self.passed else 'FAIL'} {self.expectation.path} "
        # present and absent take no value, so printing one reads as a claim
        # about None that nobody made.
        head += self.expectation.op if self.expectation.op in ("present", "absent") \
            else f"{self.expectation.op} {self.expectation.value!r}"
        if not self.passed:
            head += f": got {actual}"
            if self.expectation.why:
                head += f"\n       {self.expectation.why}"
        return head


@dataclass
class SpecResult:
    spec: Spec
    data: dict
    outcomes: list[Outcome]

    @property
    def passed(self) -> bool:
        return all(outcome.passed for outcome in self.outcomes)

    def report(self) -> str:
        head = f"{'PASS' if self.passed else 'FAIL'}  {self.spec.name}"
        return head + "\n" + "\n".join("  " + str(outcome) for outcome in self.outcomes)


def from_snapshot(snapshot: dict) -> dict:
    """The data out of a saved snapshot, addressable the way a spec addresses it.

    A snapshot keys each entry by the collector and its arguments, because two
    tiles in one snapshot must not collide: `tile({"x": 20, "y": 7})`. A spec
    names things by alias: `tile`. So each key is also registered under its
    bare collector name, first one winning, and a spec written against a live
    game runs unchanged against a snapshot taken last week.
    """
    data = dict(snapshot.get("data", snapshot))
    for key in list(data):
        bare = key.split("(", 1)[0]
        if bare != key and bare not in data:
            data[bare] = data[key]
    return data


def bind(spec: Spec, data: dict) -> dict:
    """Make a snapshot answer to the names a spec uses.

    A spec is free to call the greatworks collector "works". A snapshot, which
    knows nothing about any spec, keys it "greatworks". Binding the two is the
    last step that lets one spec run against a live game and against a saved
    snapshot without being rewritten, which is the whole point of writing it
    down.
    """
    bound = dict(data)
    for item in spec.collect:
        alias = item.get("as", item.get("collector"))
        collector = item.get("collector")
        if alias in bound or not collector:
            continue
        if collector in bound:
            bound[alias] = bound[collector]
            continue
        for key, value in data.items():
            if key.split("(", 1)[0] == collector:
                bound[alias] = value
                break
    return bound


def gather(spec: Spec, probe) -> dict:
    """Run a spec's collectors against a live probe."""
    data = {}
    for item in spec.collect:
        name = item.get("collector")
        alias = item.get("as", name)
        data[alias] = probe.collect(name, item.get("args", {}))
    return data


def evaluate(spec: Spec, data: dict) -> SpecResult:
    return SpecResult(spec=spec, data=data,
                      outcomes=[Outcome(expectation, *expectation.evaluate(data))
                                for expectation in spec.expect])
