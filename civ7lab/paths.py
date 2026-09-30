"""Where the game keeps its things.

Every other module asks this one for a path rather than spelling one out, so
that moving a Steam library or testing against a second install is one change
here and not twenty scattered string literals.

Nothing in this file assumes the game is installed: each lookup returns None
when it finds nothing, and `civ7lab doctor` is what turns that into a readable
complaint. That keeps the rest of the toolkit importable on a machine with no
game at all, which is what makes the offline halves (sql, jscheck) testable in
CI.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

# Steam's app id for Civilization VII. Used to read the installed build id out
# of the app manifest, which is how we tell whether a reference snapshot or a
# recorded measurement predates a patch.
STEAM_APP_ID = "1295660"

# Overridable so a second install, or another machine's copy mounted for
# analysis, needs no code change.
ENV_INSTALL = "CIV7_INSTALL"
ENV_USER = "CIV7_USER"


def _first_dir(candidates) -> Path | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def steam_libraries() -> list[Path]:
    """Every Steam library root, read out of libraryfolders.vdf.

    Users move large games to a second drive constantly, and the game is 100GB,
    so assuming ~/.local/share/Steam is the one thing guaranteed to break.
    """
    roots = [Path.home() / ".local/share/Steam",
             Path.home() / ".steam/steam",
             Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam"]
    found: list[Path] = []
    for root in roots:
        if root.is_dir() and root not in found:
            found.append(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        if not vdf.is_file():
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace")):
            extra = Path(match.group(1))
            if extra.is_dir() and extra not in found:
                found.append(extra)
    return found


def steam_api_library() -> Path | None:
    """The native Linux libsteam_api.so that ships with the Steam runtime.

    `workshop` loads it to talk to the running Steam client, so no SDK
    download is needed.
    """
    for root in steam_libraries():
        candidate = root / "steamrt64/libsteam_api.so"
        if candidate.is_file():
            return candidate
    return None


def install_dir() -> Path | None:
    """The game's install root: the directory holding Base/ and DLC/."""
    env = os.environ.get(ENV_INSTALL)
    if env:
        return Path(env) if Path(env).is_dir() else None
    names = ["Sid Meier's Civilization VII", "Sid Meier's Civilization VII Demo"]
    return _first_dir(lib / "steamapps/common" / name
                      for lib in steam_libraries() for name in names)


def user_dir() -> Path | None:
    """The writable user directory: logs, saves, mods, AppOptions.txt.

    On Linux the native build uses ~/My Games/... directly; a Proton install
    hides the same tree inside the prefix, so both are checked.
    """
    env = os.environ.get(ENV_USER)
    if env:
        return Path(env) if Path(env).is_dir() else None
    name = "Sid Meier's Civilization VII"
    candidates = [Path.home() / "My Games" / name,
                  Path.home() / "Documents/My Games" / name]
    for lib in steam_libraries():
        prefix = lib / "steamapps/compatdata" / STEAM_APP_ID / "pfx/drive_c/users/steamuser"
        candidates.append(prefix / "Documents/My Games" / name)
        candidates.append(prefix / "My Documents/My Games" / name)
    return _first_dir(candidates)


def executable() -> Path | None:
    """The game binary. The Linux build is native, which is what makes an
    unattended `civ7lab run` possible at all: no Proton, no Steam overlay."""
    root = install_dir()
    if not root:
        return None
    for relative in ["Base/Binaries/linux/Civ7_linux_Vulkan_FinalRelease",
                     "Base/Binaries/linux/Civ7_linux_Vulkan_Debug",
                     "Base/Binaries/Win64/Civ7_Win64_Vulkan_FinalRelease.exe"]:
        candidate = root / relative
        if candidate.is_file():
            return candidate
    return None


def build_id() -> str | None:
    """The installed Steam build id.

    Recorded alongside every measurement. A number that changed between two
    runs is the first thing to suspect when a result stops reproducing, and it
    is far cheaper to record it than to reconstruct it later from patch notes.
    """
    for lib in steam_libraries():
        manifest = lib / f"steamapps/appmanifest_{STEAM_APP_ID}.acf"
        if not manifest.is_file():
            continue
        match = re.search(r'"buildid"\s+"(\d+)"', manifest.read_text(errors="replace"))
        if match:
            return match.group(1)
    return None


@dataclass(frozen=True)
class GamePaths:
    install: Path | None
    user: Path | None

    @property
    def logs(self) -> Path | None:
        return self.user / "Logs" if self.user else None

    @property
    def ui_log(self) -> Path | None:
        return self.user / "Logs/UI.log" if self.user else None

    @property
    def database_log(self) -> Path | None:
        return self.user / "Logs/Database.log" if self.user else None

    @property
    def modding_log(self) -> Path | None:
        return self.user / "Logs/Modding.log" if self.user else None

    @property
    def mods(self) -> Path | None:
        return self.user / "Mods" if self.user else None

    @property
    def saves(self) -> Path | None:
        return self.user / "Saves" if self.user else None

    @property
    def debug_dumps(self) -> Path | None:
        """Where CopyDatabasesToDisk leaves gameplay-copy.sqlite and friends.

        Only ever as complete as the game that wrote it: taken at the main menu
        it holds no age module at all, so anything reading it must check.
        """
        return self.user / "Debug" if self.user else None

    @property
    def app_options(self) -> Path | None:
        return self.user / "AppOptions.txt" if self.user else None

    @property
    def modules(self) -> Path | None:
        return self.install / "Base/modules" if self.install else None


def game() -> GamePaths:
    return GamePaths(install=install_dir(), user=user_dir())
