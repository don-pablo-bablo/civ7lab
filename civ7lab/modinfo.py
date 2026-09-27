"""Reading a .modinfo the way the game reads it.

Two things about that file decide what a mod actually does, and both are easy
to get wrong by eye:

* **Order.** Items apply in the order the game applies them, and an ActionGroup
  with a higher LoadOrder runs later. A rule that deletes rows placed before a
  rule that inserts them silently undoes the insert, which is a class of bug
  that offline application catches instantly and a playthrough catches slowly.
* **Criteria.** An ActionGroup only fires when its criteria match the age in
  play, so "what does this mod do" has a different answer in each age, and
  asking without naming an age is asking the wrong question.

This module answers both, so the SQL harness can apply exactly the files a
given age would see, in exactly the order it would see them.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path

# The shipped ages in order, which is what AgeAtOrBefore and friends compare
# against. A mod adding its own age would need this extended; nothing else here
# assumes the list is complete.
AGES = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]


def _localname(tag: str) -> str:
    """ElementTree keeps the namespace on every tag; modinfo files declare
    xmlns="ModInfo", so every lookup would otherwise need the prefix."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


@dataclass
class ActionGroup:
    id: str
    scope: str
    criteria: str
    load_order: int
    # action kind ("UpdateDatabase", "UIScripts", ...) -> item paths, in order
    actions: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class ModInfo:
    path: Path
    id: str
    name: str
    version: str
    criteria: dict[str, list[tuple[str, str]]]
    groups: list[ActionGroup]

    @property
    def root(self) -> Path:
        """The mod's directory: every Item path is relative to it."""
        return self.path.parent

    # -- criteria ---------------------------------------------------------
    def criteria_matches(self, name: str, age: str | None) -> bool:
        """Whether a criteria id fires for a given age.

        An unrecognised test counts as matching, with the reasoning that this
        tool is for finding mistakes in the files it does understand; silently
        dropping a group because of an unknown condition would hide the very
        rules someone is trying to check.
        """
        tests = self.criteria.get(name)
        if tests is None:
            return True
        for kind, value in tests:
            if kind == "AlwaysMet":
                continue
            if age is None:
                continue
            if kind == "AgeInUse" and value != age:
                return False
            if kind == "AgeAtOrBefore" and AGES.index(age) > AGES.index(value):
                return False
            if kind == "AgeAtOrAfter" and AGES.index(age) < AGES.index(value):
                return False
        return True

    # -- what applies -----------------------------------------------------
    def items(self, action: str = "UpdateDatabase", age: str | None = None
              ) -> list[tuple[ActionGroup, Path]]:
        """Every item of one action kind, in the order the game applies it."""
        chosen: list[tuple[ActionGroup, Path]] = []
        for index, group in enumerate(self.groups):
            if not self.criteria_matches(group.criteria, age):
                continue
            for item in group.actions.get(action, []):
                chosen.append((group, self.root / item))
        # Python's sort is stable, so equal LoadOrders keep document order,
        # which is what the game does within a group.
        chosen.sort(key=lambda pair: pair[0].load_order)
        return chosen

    def ui_scripts(self, age: str | None = None) -> list[Path]:
        return [path for _, path in self.items("UIScripts", age)]

    def ambiguous_criteria(self) -> list[str]:
        """Criteria whose direction cannot be read off the file with confidence.

        `AgeAtOrBefore AGE_EXPLORATION` can mean "the age in use is at or
        before Exploration" or "Exploration is at or before the age in use",
        and Firaxis' own naming ("exploration-age-persist") reads like the
        second while the words read like the first. This tool takes the literal
        reading and says so, because a harness that quietly picks a side is
        worse than one that makes you look: guessed wrong, a cross-age rule
        fires in the wrong age and destroys the thing it was meant to protect.

        The fix in a mod is the same either way: spell it as explicit AgeInUse
        rows, which is what Firaxis does in Babylon's modinfo.
        """
        names = []
        for name, tests in self.criteria.items():
            if any(kind in ("AgeAtOrBefore", "AgeAtOrAfter") for kind, _ in tests):
                names.append(name)
        return names

    def groups_using(self, criteria_names) -> list[str]:
        wanted = set(criteria_names)
        return [group.id for group in self.groups if group.criteria in wanted]


def _commented_out_items(text: str) -> list[str]:
    """Items sitting inside XML comments.

    A mod under development keeps probes commented out in the modinfo, and
    "did you remember to uncomment it" is a question worth answering from the
    file rather than from memory.
    """
    found = []
    for comment in re.findall(r"<!--(.*?)-->", text, re.S):
        found.extend(re.findall(r"<Item>\s*([^<]+?)\s*</Item>", comment))
    return found


def load(path: str | Path) -> ModInfo:
    path = Path(path)
    if path.is_dir():
        candidates = sorted(path.glob("*.modinfo"))
        if not candidates:
            raise FileNotFoundError(f"no .modinfo in {path}")
        path = candidates[0]
    tree = ElementTree.parse(path)
    root = tree.getroot()

    properties = {}
    criteria: dict[str, list[tuple[str, str]]] = {}
    groups: list[ActionGroup] = []

    for child in root:
        name = _localname(child.tag)
        if name == "Properties":
            properties = {_localname(node.tag): (node.text or "") for node in child}
        elif name == "ActionCriteria":
            for node in child:
                tests = [(_localname(test.tag), (test.text or "").strip()) for test in node]
                criteria[node.get("id", "")] = tests
        elif name == "ActionGroups":
            for node in child:
                load_order = 0
                actions: dict[str, list[str]] = {}
                for part in node:
                    part_name = _localname(part.tag)
                    if part_name == "Properties":
                        for prop in part:
                            if _localname(prop.tag) == "LoadOrder":
                                load_order = int((prop.text or "0").strip() or 0)
                    elif part_name == "Actions":
                        for action in part:
                            items = [(item.text or "").strip() for item in action
                                     if _localname(item.tag) == "Item" and (item.text or "").strip()]
                            actions.setdefault(_localname(action.tag), []).extend(items)
                groups.append(ActionGroup(id=node.get("id", ""), scope=node.get("scope", ""),
                                          criteria=node.get("criteria", ""),
                                          load_order=load_order, actions=actions))

    return ModInfo(path=path, id=root.get("id", path.stem),
                   name=properties.get("Name", root.get("id", "")),
                   version=root.get("version", properties.get("Version", "")),
                   criteria=criteria, groups=groups)


def disabled_items(path: str | Path) -> list[str]:
    path = Path(path)
    if path.is_dir():
        path = sorted(path.glob("*.modinfo"))[0]
    return _commented_out_items(path.read_text(errors="replace"))
