"""Where the game keeps its files.

Every other module asks here for a path. Each lookup returns None when it
finds nothing, and `civ7lab doctor` turns that into a message, so the package
still imports and the offline tests still run on a machine with no game.

CIV7_INSTALL and CIV7_USER override the two roots.

Linux is where this has been used. The Windows locations come from the
game's community documentation and have not been tried; see CONTRIBUTING.md.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# Steam's app id for Civilization VII. The installed build id is read from its
# app manifest and recorded with every run.
STEAM_APP_ID = "1295660"

ENV_INSTALL = "CIV7_INSTALL"
ENV_USER = "CIV7_USER"

GAME_NAME = "Sid Meier's Civilization VII"
WINDOWS = sys.platform == "win32"


def _first_dir(candidates) -> Path | None:
    for candidate in candidates:
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    return None


def _steam_roots() -> list[Path]:
    """Where Steam itself may be installed."""
    if not WINDOWS:
        return [
            Path.home() / ".local/share/Steam",
            Path.home() / ".steam/steam",
            Path.home() / ".var/app/com.valvesoftware.Steam/data/Steam",
        ]
    roots = []
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            roots.append(Path(winreg.QueryValueEx(key, "SteamPath")[0]))
    except OSError:
        pass
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        if os.environ.get(variable):
            roots.append(Path(os.environ[variable]) / "Steam")
    return roots


def vdf_path(text: str) -> str:
    """A path as libraryfolders.vdf writes it. On Windows backslashes are
    doubled: "D:\\\\SteamLibrary"."""
    return text.replace("\\\\", "\\")


def steam_libraries() -> list[Path]:
    """Every Steam library root, read out of libraryfolders.vdf, so a game on
    a second drive is found."""
    roots = _steam_roots()
    found: list[Path] = []
    for root in roots:
        if root.is_dir() and root not in found:
            found.append(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        if not vdf.is_file():
            continue
        for match in re.finditer(
            r'"path"\s+"([^"]+)"', vdf.read_text(errors="replace", encoding="utf-8")
        ):
            extra = Path(vdf_path(match.group(1)))
            if extra.is_dir() and extra not in found:
                found.append(extra)
    return found


def steam_api_library() -> Path | None:
    """The Steam API library `workshop` loads to talk to the Steam client.

    On Linux, the libsteam_api.so in the Steam runtime. On Windows, the
    steam_api64.dll the game ships beside its executable. Neither needs an
    SDK download.
    """
    if WINDOWS:
        root = install_dir()
        candidate = root / "Base/Binaries/Win64/steam_api64.dll" if root else None
        return candidate if candidate and candidate.is_file() else None
    for root in steam_libraries():
        candidate = root / "steamrt64/libsteam_api.so"
        if candidate.is_file():
            return candidate
    return None


def steam_overlay() -> Path | None:
    """Steam's 64-bit overlay library on Linux, which gives a game F12
    screenshots and Shift+Tab. Steam loads it into games it starts itself."""
    if WINDOWS:
        return None
    for root in _steam_roots():
        candidate = root / "ubuntu12_64/gameoverlayrenderer.so"
        if candidate.is_file():
            return candidate
    return None


def install_dir() -> Path | None:
    """The game's install root: the directory holding Base/ and DLC/."""
    env = os.environ.get(ENV_INSTALL)
    if env:
        return Path(env) if Path(env).is_dir() else None
    names = [GAME_NAME, f"{GAME_NAME} Demo"]
    return _first_dir(
        lib / "steamapps/common" / name for lib in steam_libraries() for name in names
    )


def user_dir() -> Path | None:
    """The writable user directory: logs, saves, mods, AppOptions.txt.

    The native Linux build uses ~/My Games/<game>. The Windows build uses
    %LOCALAPPDATA%/Firaxis Games/<game>, and under Proton that folder is
    inside the game's prefix.
    """
    env = os.environ.get(ENV_USER)
    if env:
        return Path(env) if Path(env).is_dir() else None
    windows_folder = Path("Firaxis Games") / GAME_NAME
    if WINDOWS:
        local = os.environ.get("LOCALAPPDATA")
        return _first_dir([Path(local) / windows_folder] if local else [])
    candidates = [Path.home() / "My Games" / GAME_NAME]
    for lib in steam_libraries():
        prefix = lib / "steamapps/compatdata" / STEAM_APP_ID / "pfx/drive_c/users/steamuser"
        candidates.append(prefix / "AppData/Local" / windows_folder)
    return _first_dir(candidates)


def executable() -> Path | None:
    """The game binary for this system: the native Linux build, or on
    Windows the DirectX 12 build."""
    root = install_dir()
    if not root:
        return None
    relative = (
        "Base/Binaries/Win64/Civ7_Win64_DX12_FinalRelease.exe"
        if WINDOWS
        else "Base/Binaries/linux/Civ7_linux_Vulkan_FinalRelease"
    )
    candidate = root / relative
    return candidate if candidate.is_file() else None


def build_id() -> str | None:
    """The installed Steam build id. When a result stops reproducing, check
    whether this changed between the two runs."""
    for lib in steam_libraries():
        manifest = lib / f"steamapps/appmanifest_{STEAM_APP_ID}.acf"
        if not manifest.is_file():
            continue
        match = re.search(
            r'"buildid"\s+"(\d+)"', manifest.read_text(errors="replace", encoding="utf-8")
        )
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
        """Where CopyDatabasesToDisk writes gameplay-copy.sqlite and the other
        dumps. A dump written at the main menu holds no age's data."""
        return self.user / "Debug" if self.user else None

    @property
    def app_options(self) -> Path | None:
        return self.user / "AppOptions.txt" if self.user else None

    @property
    def modules(self) -> Path | None:
        return self.install / "Base/modules" if self.install else None


def game() -> GamePaths:
    return GamePaths(install=install_dir(), user=user_dir())
