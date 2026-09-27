"""Read and edit AppOptions.txt.

The game ships a long list of development switches in that file, nearly all of
them commented out with a leading `;`. Two of them change what a toolkit like
this can do:

* **UIDebugger** starts the UI remote debugger, which is what `civ7lab live`
  attaches to. Without it there is nothing to connect to and every question has
  to go through the log file again.
* **UIFileWatcher** is meant to reload UI files when they change. Measured on
  21 Sep 2026, it did not reload a mod's UI script, so `civ7lab ui` patches
  over the debugger instead.

A third, **CopyDatabasesToDisk**, is what keeps Debug/*.sqlite current, and the
offline SQL harness reads those.

The file is edited in place and backed up first, because it also holds the
player's real settings and this is not the place to be clever. Note that the
game rewrites the file on exit: set options while it is closed, and re-check
afterwards rather than assuming a value stuck.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths

# The options worth naming, with what they are for. `civ7lab options --live`
# sets exactly these, so a fresh machine is one command from instrumentable.
LIVE_PRESET = {
    "UIDebugger": "1",          # the inspector this toolkit talks to
    "UIFileWatcher": "1",       # did not reload a mod's scripts when measured
    "CopyDatabasesToDisk": "1", # keep Debug/*.sqlite fresh for offline SQL work
    "EnableConsoleOutput": "1", # mirror the logs to stdout, so `run` can stream
    "UILogLevel": "2",          # Normal: our own lines without the firehose
}

# What to put back for ordinary play. The debugger costs a listening socket and
# the file watcher costs an occasional hitch, so there is a reason to turn them
# off again, and a reason for it to be one command rather than ten edits.
PLAY_PRESET = {
    "UIDebugger": "0",
    "UIFileWatcher": "0",
    "EnableConsoleOutput": "0",
}


@dataclass
class Option:
    section: str
    name: str
    value: str
    enabled: bool
    line_number: int


class AppOptions:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.lines = self.path.read_text(errors="replace").splitlines()

    # -- reading ----------------------------------------------------------
    def entries(self) -> list[Option]:
        found: list[Option] = []
        section = ""
        for index, line in enumerate(self.lines):
            stripped = line.strip()
            header = re.match(r"^\[(.+)\]$", stripped)
            if header:
                section = header.group(1)
                continue
            # A commented-out option and a live one differ by one character, and
            # both are worth reporting: a `;UIDebugger 1` is the switch sitting
            # there unused, which is exactly what a reader wants to be told.
            match = re.match(r"^(;?)\s*([A-Za-z][A-Za-z0-9_]*)\s+(\S.*)$", stripped)
            if not match:
                continue
            found.append(Option(section=section, name=match.group(2),
                                value=match.group(3).strip(),
                                enabled=not match.group(1), line_number=index))
        return found

    def get(self, name: str) -> Option | None:
        for option in self.entries():
            if option.name.lower() == name.lower() and option.enabled:
                return option
        for option in self.entries():
            if option.name.lower() == name.lower():
                return option
        return None

    def effective(self, name: str) -> str | None:
        option = self.get(name)
        return option.value if option and option.enabled else None

    # -- writing ----------------------------------------------------------
    def set(self, name: str, value: str, section: str = "Debug") -> str:
        """Set an option, uncommenting it where the game left it commented.

        Returns a one-line description of what changed, so the caller can print
        a truthful report rather than claiming a change that was already true.
        """
        existing = self.get(name)
        if existing:
            if existing.enabled and existing.value == value:
                return f"{name} already {value}"
            indent = re.match(r"^\s*", self.lines[existing.line_number]).group(0)
            self.lines[existing.line_number] = f"{indent}{name} {value}"
            was = f"{existing.value}{'' if existing.enabled else ' (commented out)'}"
            return f"{name}: {was} -> {value}"
        insert_at = self._section_end(section)
        self.lines.insert(insert_at, f"{name} {value}")
        return f"{name}: added as {value} under [{section}]"

    def _section_end(self, section: str) -> int:
        start = None
        for index, line in enumerate(self.lines):
            if line.strip() == f"[{section}]":
                start = index
                break
        if start is None:
            self.lines.extend(["", f"[{section}]"])
            return len(self.lines)
        for index in range(start + 1, len(self.lines)):
            if re.match(r"^\[.+\]$", self.lines[index].strip()):
                return index
        return len(self.lines)

    def save(self, backup: bool = True) -> Path | None:
        """Write the file back, keeping one backup per day.

        One per day rather than one per write: the interesting backup is the
        state before a session started poking at it, and a hundred backups from
        one afternoon buries it.
        """
        backup_path = None
        if backup:
            backup_path = self.path.with_suffix(
                self.path.suffix + f".civ7lab-{time.strftime('%Y%m%d')}.bak")
            if not backup_path.exists():
                shutil.copy2(self.path, backup_path)
        self.path.write_text("\n".join(self.lines) + "\n")
        return backup_path


def load() -> AppOptions:
    game = paths.game()
    if not game.app_options or not game.app_options.is_file():
        raise FileNotFoundError(
            "AppOptions.txt not found. The game writes it on first run, so run "
            "the game once, or point CIV7_USER at the right directory.")
    return AppOptions(game.app_options)


def apply_preset(preset: dict[str, str], dry_run: bool = False) -> list[str]:
    options = load()
    changes = [options.set(name, value) for name, value in preset.items()]
    if not dry_run:
        options.save()
    return changes
