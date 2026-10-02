"""Specs: a measurement written down so it can be run again.

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

It runs against a live game or a saved snapshot.

Paths: dots for keys, `[2]` for an index, and `[key=value]` for the list item
whose field has that value, such as `constructibles[type=BUILDING_LIBRARY]`.
Several fields are separated by commas, as `diff` prints them: `[x=3,y=4]`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MISSING = object()

_STEP = re.compile(r"([^.\[\]]+)|\[([^\]]+)\]")


def resolve(data, path: str):
    """Follow a path into a snapshot. A missing step returns MISSING, which
    fails the expectation and names the path."""
    current = data
    for key, bracket in _STEP.findall(path):
        if current is MISSING or current is None:
            return MISSING
        token = key or bracket
        if bracket and "=" in bracket:
            # One field or several, as diff labels them: [type=X] or [x=3,y=4].
            wanted = [part.partition("=")[::2] for part in bracket.split(",")]
            if not isinstance(current, list):
                return MISSING
            found = MISSING
            for item in current:
                if isinstance(item, dict) and all(
                    str(item.get(name.strip())) == value.strip() for name, value in wanted
                ):
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
    except TypeError, ValueError:
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
    def load(cls, path: str | Path) -> Spec:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            name=document.get("name", Path(path).stem),
            collect=document.get("collect", []),
            expect=[Expectation(**item) for item in document.get("expect", [])],
            note=document.get("note", ""),
        )


@dataclass
class Outcome:
    expectation: Expectation
    passed: bool
    actual: object

    def __str__(self) -> str:
        actual = "(missing)" if self.actual is MISSING else repr(self.actual)
        head = f"{'PASS' if self.passed else 'FAIL'} {self.expectation.path} "
        # present and absent take no value, so none is printed.
        head += (
            self.expectation.op
            if self.expectation.op in ("present", "absent")
            else f"{self.expectation.op} {self.expectation.value!r}"
        )
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
    """A snapshot's data, with each entry also under its bare collector name.

    A snapshot keys entries by collector and arguments, such as
    `tile({"x": 20, "y": 7})`, so two tiles do not collide. The bare name,
    `tile`, points at the first such entry.
    """
    data = dict(snapshot.get("data", snapshot))
    for key in list(data):
        bare = key.split("(", 1)[0]
        if bare != key and bare not in data:
            data[bare] = data[key]
    return data


def bind(spec: Spec, data: dict) -> dict:
    """Add the spec's aliases to snapshot data. A spec may call the
    greatworks collector "works"; the snapshot keys it "greatworks"."""
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
    return SpecResult(
        spec=spec,
        data=data,
        outcomes=[Outcome(expectation, *expectation.evaluate(data)) for expectation in spec.expect],
    )
