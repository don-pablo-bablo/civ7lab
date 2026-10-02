"""Read and edit AppOptions.txt.

The file holds the game's development switches, most commented out with a
leading `;`. Three matter here:

* **UIDebugger**: starts the inspector that `civ7lab live` and `civ7lab ui`
  attach to.
* **CopyDatabasesToDisk**: writes Debug/*.sqlite, which `civ7lab sql` reads.
* **UIFileWatcher**: meant to reload changed UI files. On 21 Sep 2026 it did
  not reload a mod's script, which is why `civ7lab ui` exists. `--live`
  leaves it alone; `--play` turns it off.

The file also holds the player's own settings, so it is backed up before each
write. The game rewrites it on exit: set options while the game is closed.
"""

from __future__ import annotations

import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from . import paths

# What `civ7lab options --live` sets.
LIVE_PRESET = {
    "UIDebugger": "1",  # the inspector this toolkit talks to
    "CopyDatabasesToDisk": "1",  # keep Debug/*.sqlite fresh for offline SQL work
    "EnableConsoleOutput": "1",  # mirror the logs to stdout, so `run` can stream
    "UILogLevel": "2",  # Normal: our own lines without the firehose
}

# What `civ7lab options --play` sets: the switches that cost something during
# normal play.
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
        # Read as bytes to see the line endings. The game writes CRLF, even on
        # Linux, and a rewrite should keep them.
        text = self.path.read_bytes().decode("utf-8", errors="replace")
        self.newline = "\r\n" if "\r\n" in text else "\n"
        self.lines = text.splitlines()
        self.changed = False

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
            # Commented-out options are kept too, so `;UIDebugger 1` can be
            # reported as present but off.
            match = re.match(r"^(;?)\s*([A-Za-z][A-Za-z0-9_]*)\s+(\S.*)$", stripped)
            if not match:
                continue
            found.append(
                Option(
                    section=section,
                    name=match.group(2),
                    value=match.group(3).strip(),
                    enabled=not match.group(1),
                    line_number=index,
                )
            )
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
        """Set an option, uncommenting it if needed. Returns one line saying
        what changed, or that it was already set."""
        existing = self.get(name)
        if existing:
            if existing.enabled and existing.value == value:
                return f"{name} already {value}"
            indent = re.match(r"^\s*", self.lines[existing.line_number]).group(0)
            self.lines[existing.line_number] = f"{indent}{name} {value}"
            self.changed = True
            was = f"{existing.value}{'' if existing.enabled else ' (commented out)'}"
            return f"{name}: {was} -> {value}"
        insert_at = self._section_end(section)
        self.lines.insert(insert_at, f"{name} {value}")
        self.changed = True
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
        """Write the file back, with its own line endings, if anything changed.
        The first write of each day backs up the file as it was before that
        day's changes. Returns the backup's path, or None if nothing was
        written or backed up."""
        if not self.changed:
            return None
        backup_path = None
        if backup:
            backup_path = self.path.with_suffix(
                self.path.suffix + f".civ7lab-{time.strftime('%Y%m%d')}.bak"
            )
            if not backup_path.exists():
                shutil.copy2(self.path, backup_path)
        # Bytes, so Windows text mode cannot turn each CRLF into CR CR LF.
        self.path.write_bytes((self.newline.join(self.lines) + self.newline).encode("utf-8"))
        return backup_path


def load() -> AppOptions:
    game = paths.game()
    if not game.app_options or not game.app_options.is_file():
        raise FileNotFoundError(
            "AppOptions.txt not found. The game writes it on first run, so run "
            "the game once, or point CIV7_USER at the right directory."
        )
    return AppOptions(game.app_options)


def apply_preset(preset: dict[str, str], dry_run: bool = False) -> tuple[list[str], bool]:
    """Set every switch in a preset. Returns a line per switch, and whether
    anything changed."""
    options = load()
    changes = [options.set(name, value) for name, value in preset.items()]
    if not dry_run:
        options.save()
    return changes, options.changed
