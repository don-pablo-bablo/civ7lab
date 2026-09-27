"""One command that says whether anything here will work, and why not.

Written because the failure modes are all silent. The inspector is off, so
nothing connects. The database dump was taken at the main menu, so it is empty
of everything worth testing. The mod is not symlinked, so the edit being tested
never loaded. Each of those looks, from the outside, exactly like the tool
being broken.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import appoptions, cdp, paths, sqlcheck


@dataclass
class Finding:
    ok: bool | None   # None: informational, nothing to fix
    label: str
    detail: str
    fix: str = ""

    def __str__(self) -> str:
        mark = "  " if self.ok is None else ("ok" if self.ok else "!!")
        line = f"{mark}  {self.label}: {self.detail}"
        if not self.ok and self.fix:
            line += f"\n      -> {self.fix}"
        return line


def check() -> list[Finding]:
    found: list[Finding] = []
    game = paths.game()

    found.append(Finding(bool(game.install), "install",
                         str(game.install) if game.install else "not found",
                         "set CIV7_INSTALL to the directory holding Base/ and DLC/"))
    found.append(Finding(bool(game.user), "user directory",
                         str(game.user) if game.user else "not found",
                         "set CIV7_USER to the directory holding Logs/ and Mods/"))
    executable = paths.executable()
    found.append(Finding(bool(executable), "executable",
                         str(executable) if executable else "not found",
                         "unattended runs need it; live and offline work do not"))
    found.append(Finding(None, "game build", paths.build_id() or "unknown"))

    # Options
    try:
        options = appoptions.load()
        debugger = options.effective("UIDebugger")
        found.append(Finding(debugger == "1", "UIDebugger",
                             debugger or "off (commented out)",
                             "civ7lab options --live, then restart the game: "
                             "without it there is nothing for `live` to attach to"))
        watcher = options.effective("UIFileWatcher")
        found.append(Finding(watcher == "1", "UIFileWatcher", watcher or "off",
                             "civ7lab options --live. It did not reload a mod's "
                             "scripts when measured; civ7lab ui watch does"))
        copies = options.effective("CopyDatabasesToDisk")
        found.append(Finding(copies == "1", "CopyDatabasesToDisk", copies or "off",
                             "civ7lab options --live: the offline SQL harness reads "
                             "the dumps this writes"))
    except FileNotFoundError as error:
        found.append(Finding(False, "AppOptions.txt", str(error)))

    # Is a game running, and does it answer?
    port = cdp.find_port()
    if port:
        try:
            targets = cdp.targets("127.0.0.1", port)
            found.append(Finding(True, "inspector",
                                 f"port {port}, {len(targets)} target(s): "
                                 + "; ".join(target.title or target.url for target in targets[:4])))
        except cdp.CDPError as error:
            found.append(Finding(False, "inspector", str(error)))
    else:
        found.append(Finding(None, "inspector",
                             "nothing listening (normal when the game is not running)"))

    # The database the offline harness works on
    dump = sqlcheck.default_db()
    if dump:
        described = sqlcheck.describe(dump)
        constructibles = described["constructibles"]
        found.append(Finding(constructibles > 0, "gameplay dump",
                             f"{dump.name}, {constructibles} constructibles",
                             "a dump with no constructibles was written at the main menu, "
                             "where no age module is loaded; load a save and let it rewrite"))
    else:
        found.append(Finding(False, "gameplay dump", "not found",
                             "run the game with CopyDatabasesToDisk 1 and a save loaded"))

    # Mods
    if game.mods and game.mods.is_dir():
        installed = []
        for entry in sorted(game.mods.iterdir()):
            kind = "link" if entry.is_symlink() else "copy"
            target = f" -> {os.readlink(entry)}" if entry.is_symlink() else ""
            installed.append(f"{entry.name} ({kind}){target}")
        found.append(Finding(None, "mods", "; ".join(installed) or "none installed"))
        probe = game.mods / "civ7lab-probe"
        found.append(Finding(probe.exists(), "probe mod",
                             "installed" if probe.exists() else "not installed",
                             "civ7lab mod install: needed for unattended runs. A live "
                             "session does not need it: the probe can be injected."))

    # Optional python pieces
    try:
        import tree_sitter  # noqa: F401
        import tree_sitter_javascript  # noqa: F401
        found.append(Finding(True, "tree-sitter", "available, so UI scripts can be parsed"))
    except ImportError:
        found.append(Finding(False, "tree-sitter", "not installed",
                             "pip install tree_sitter tree_sitter_javascript "
                             "(only jscheck needs it)"))

    found.append(Finding(None, "disk",
                         f"{shutil.disk_usage(Path.home()).free // (1024**3)} GB free in home"))
    return found


def report() -> str:
    lines = [str(finding) for finding in check()]
    problems = [finding for finding in check() if finding.ok is False]
    lines.append("")
    lines.append("ready" if not problems else f"{len(problems)} thing(s) to fix above")
    return "\n".join(lines)
