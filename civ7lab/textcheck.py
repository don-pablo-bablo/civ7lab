"""`civ7lab text`: check a mod's LOC_ keys against the text that defines them.

A key used but defined nowhere shows in game as the raw key, and is only
reported in Localization.log after a launch. This finds it offline.

* **Used**: every `LOC_` key in the mod's files, except its text files.
* **Defined by the mod**: the Tag of every row in the files its modinfo lists
  under UpdateText, in any age.
* **Defined by the game**: Debug/localization-copy.sqlite, which the game
  writes with CopyDatabasesToDisk on. A dump taken with the mod loaded holds
  the mod's keys too; `prefix` leaves those out.
"""

from __future__ import annotations

import re
import sqlite3
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path

from . import modinfo, paths

# A key ending in "_" is the start of one built in code, such as
# "LOC_UNIT_" + name, and cannot be checked.
KEY = re.compile(r"\bLOC_[A-Za-z0-9_]*[A-Za-z0-9]\b")
SEARCHED = {".js", ".ts", ".sql", ".xml", ".modinfo", ".html"}
# A dependency's title in a modinfo, such as LOC_MODULE_BASE_STANDARD_NAME.
# The game's own modinfos use these keys without defining them.
DEPENDENCY_TITLE = re.compile(r'\btitle="[^"]*"')


@dataclass
class Report:
    used: dict[str, list[str]] = field(default_factory=dict)  # key -> files using it
    defined: set[str] = field(default_factory=set)
    game: set[str] | None = None  # None: no dump to check against
    undefined: list[str] = field(default_factory=list)
    unused: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.undefined


def default_db() -> Path | None:
    debug = paths.game().debug_dumps
    dump = debug / "localization-copy.sqlite" if debug else None
    return dump if dump and dump.is_file() else None


def game_keys(db: Path, prefix: str | None = None) -> set[str]:
    connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        keys = {row[0] for row in connection.execute("SELECT DISTINCT Tag FROM LocalizedText")}
    finally:
        connection.close()
    return {key for key in keys if not (prefix and key.startswith(prefix))}


def defined_keys(text_files: list[Path]) -> set[str]:
    keys: set[str] = set()
    for path in text_files:
        if path.suffix.lower() == ".sql":
            keys |= set(KEY.findall(path.read_text(encoding="utf-8", errors="replace")))
            continue
        for element in ElementTree.parse(path).getroot().iter():
            tag = element.get("Tag")
            if tag and tag.startswith("LOC_"):
                keys.add(tag)
    return keys


def check(mod_path: str | Path, db: str | Path | None = None, prefix: str | None = None) -> Report:
    info = modinfo.load(mod_path)
    text_files = [path for _, path in info.items("UpdateText") if path.is_file()]
    report = Report(defined=defined_keys(text_files))
    skip = {path.resolve() for path in text_files}
    root = Path(info.root)
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in SEARCHED or path.resolve() in skip:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".modinfo":
            text = DEPENDENCY_TITLE.sub("", text)
        for key in set(KEY.findall(text)):
            report.used.setdefault(key, []).append(path.relative_to(root).as_posix())
    dump = Path(db) if db else default_db()
    if dump and dump.is_file():
        report.game = game_keys(dump, prefix)
    known = report.defined | (report.game or set())
    report.undefined = sorted(key for key in report.used if key not in known)
    report.unused = sorted(report.defined - set(report.used))
    return report
