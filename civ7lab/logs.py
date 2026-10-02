"""Reading the game's logs, and copying them before they are lost.

The game empties every log at launch. `snapshot()` copies the folder, and
`civ7lab run` calls it before starting the game.

`errors()` returns only the lines that report a database, modding or script
error, so a four-megabyte log reads as a few lines.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths, records

# The lines `errors()` reports. Keep it short: every false match is noise in
# every report.
ERROR_PATTERNS = [
    (re.compile(r"FOREIGN KEY constraint failed", re.I), "database"),
    (re.compile(r"\bUNIQUE constraint failed", re.I), "database"),
    (re.compile(r"\bno such (table|column)\b", re.I), "database"),
    (re.compile(r"\bsyntax error\b", re.I), "database"),
    (re.compile(r"\berror\b.*\.(sql|xml)\b", re.I), "database"),
    (re.compile(r"Failed to (load|apply|parse)", re.I), "modding"),
    (re.compile(r"Uncaught|TypeError|ReferenceError|is not a function|is not defined"), "script"),
    (re.compile(r"Assert failure", re.I), "assert"),
]


@dataclass
class LogError:
    log: str
    line_number: int
    kind: str
    text: str

    def __str__(self) -> str:
        return f"{self.log}:{self.line_number} [{self.kind}] {self.text.strip()}"


def snapshot(destination: Path, note: str = "") -> Path:
    """Copy the whole log directory somewhere it will survive the next launch."""
    game = paths.game()
    if not game.logs or not game.logs.is_dir():
        raise FileNotFoundError("no Logs directory; has the game been run on this machine?")
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for log in sorted(game.logs.iterdir()):
        if log.is_file():
            shutil.copy2(log, destination / log.name)
    stamp = destination / "SNAPSHOT.txt"
    stamp.write_text(
        f"copied {time.strftime('%Y-%m-%d %H:%M:%S')} from {game.logs}\n"
        f"game build {paths.build_id()}\n" + (f"{note}\n" if note else ""),
        encoding="utf-8",
    )
    return destination


def errors(
    log_dir: Path | None = None, names=("Database.log", "Modding.log", "UI.log"), limit: int = 200
) -> list[LogError]:
    """The lines in those logs that mean something went wrong."""
    game = paths.game()
    directory = Path(log_dir) if log_dir else game.logs
    if not directory or not Path(directory).is_dir():
        return []
    found: list[LogError] = []
    for name in names:
        path = Path(directory) / name
        if not path.is_file():
            continue
        for number, line in enumerate(
            path.read_text(errors="replace", encoding="utf-8").splitlines(), 1
        ):
            for pattern, kind in ERROR_PATTERNS:
                if pattern.search(line):
                    found.append(LogError(name, number, kind, line[:400]))
                    break
            if len(found) >= limit:
                return found
    return found


def marker_lines(log: Path | None = None, marker: str = "") -> list[str]:
    """Every UI.log line containing a marker, such as a mod's own tag."""
    path = Path(log) if log else paths.game().ui_log
    if not path or not Path(path).is_file():
        return []
    wanted = marker or records.MARKER
    return [
        line.rstrip("\n")
        for line in Path(path).read_text(errors="replace", encoding="utf-8").splitlines()
        if wanted in line
    ]


def read_records(log: Path | None = None) -> records.ParseReport:
    """Structured records a probe mod printed during the last session."""
    path = Path(log) if log else paths.game().ui_log
    if not path or not Path(path).is_file():
        return records.ParseReport(errors=[f"no log at {path}"])
    return records.parse_file(path)


def build_stamps(log: Path | None = None) -> dict[str, str]:
    """Which build of each script ran, from the `civ7lab:build <name>
    <stamp>` lines scripts print at load. A check against a stale build looks
    the same as one against a fresh build; this tells them apart."""
    path = Path(log) if log else paths.game().ui_log
    if not path or not Path(path).is_file():
        return {}
    stamps: dict[str, str] = {}
    pattern = re.compile(r"civ7lab:build\s+(\S+)\s+(.+?)\s*$")
    for line in Path(path).read_text(errors="replace", encoding="utf-8").splitlines():
        match = pattern.search(line)
        if match:
            stamps[match.group(1)] = match.group(2)
    return stamps
