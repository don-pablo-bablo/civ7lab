"""Reading a .modinfo the way the game reads it.

* **Order**: an ActionGroup with a higher LoadOrder applies later. A delete
  that runs before the insert it targets does nothing.
* **Criteria**: an ActionGroup applies only when its criteria match the age,
  so a mod can do something different in each age.

`items()` gives the files one age applies, in the order it applies them.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path

# The shipped ages in order, for AgeAtOrBefore and AgeAtOrAfter. A mod that
# adds an age needs it added here.
AGES = ["AGE_ANTIQUITY", "AGE_EXPLORATION", "AGE_MODERN"]


def _localname(tag: str) -> str:
    """The tag without its namespace. Modinfo files declare xmlns="ModInfo"."""
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
        """Whether a criteria id matches an age. A test this code does not
        know counts as a match, so its group is still checked."""
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
    def items(
        self, action: str = "UpdateDatabase", age: str | None = None
    ) -> list[tuple[ActionGroup, Path]]:
        """Every item of one action kind, in the order the game applies it."""
        chosen: list[tuple[ActionGroup, Path]] = []
        for group in self.groups:
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
        """Criteria using AgeAtOrBefore or AgeAtOrAfter.

        `AgeAtOrBefore AGE_EXPLORATION` can read as "the age in use is at or
        before Exploration" or the reverse. Firaxis' group names suggest the
        reverse; this code takes the literal reading and warns. Explicit
        AgeInUse rows, as in Babylon's modinfo, remove the doubt.
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
    """Items inside XML comments, which the game does not load."""
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
                            items = [
                                (item.text or "").strip()
                                for item in action
                                if _localname(item.tag) == "Item" and (item.text or "").strip()
                            ]
                            actions.setdefault(_localname(action.tag), []).extend(items)
                groups.append(
                    ActionGroup(
                        id=node.get("id", ""),
                        scope=node.get("scope", ""),
                        criteria=node.get("criteria", ""),
                        load_order=load_order,
                        actions=actions,
                    )
                )

    return ModInfo(
        path=path,
        id=root.get("id", path.stem),
        name=properties.get("Name", root.get("id", "")),
        version=root.get("version", properties.get("Version", "")),
        criteria=criteria,
        groups=groups,
    )


def disabled_items(path: str | Path) -> list[str]:
    path = Path(path)
    if path.is_dir():
        path = sorted(path.glob("*.modinfo"))[0]
    return _commented_out_items(path.read_text(errors="replace", encoding="utf-8"))
