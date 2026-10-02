"""Installing mods into the game's Mods folder.

A symlink to the working copy means an edit reaches the game with no copy
step. `installed()` shows copies and broken links, since either means the game
loads something other than the file being edited.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import modinfo, paths

PROBE_SOURCE = Path(__file__).resolve().parents[1] / "mod/civ7lab-probe"


@dataclass
class Installed:
    name: str
    path: Path
    kind: str  # "link" or "copy"
    target: Path | None
    valid: bool


def is_link(path: Path) -> bool:
    """A symlink, or on Windows a directory junction."""
    return path.is_symlink() or path.is_junction()


def link_target(path: Path) -> Path:
    # Windows reports a junction's target with a \\?\ prefix.
    return Path(os.readlink(path).removeprefix("\\\\?\\"))


def remove_link(path: Path) -> None:
    """Remove a link and leave what it points at alone."""
    if path.is_junction():
        os.rmdir(path)
    else:
        path.unlink()


def make_link(source: Path, destination: Path) -> None:
    """A symlink, or on Windows without the right to make one, a directory
    junction, which needs no admin rights or Developer Mode."""
    try:
        destination.symlink_to(source, target_is_directory=True)
    except OSError:
        if not paths.WINDOWS:
            raise
        import _winapi

        _winapi.CreateJunction(str(source), str(destination))


def installed() -> list[Installed]:
    game = paths.game()
    if not game.mods or not game.mods.is_dir():
        return []
    out = []
    for entry in sorted(game.mods.iterdir()):
        if entry.name.startswith("."):
            continue
        if is_link(entry):
            target = link_target(entry)
            out.append(Installed(entry.name, entry, "link", target, target.exists()))
        else:
            out.append(Installed(entry.name, entry, "copy", None, entry.is_dir()))
    return out


def install(source: str | Path | None = None, link: bool = True, force: bool = False) -> str:
    """Link or copy a mod folder into Mods. Defaults to the civ7lab probe."""
    source = Path(source) if source else PROBE_SOURCE
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"no such mod directory: {source}")
    # The game ignores a folder with no modinfo without saying so.
    info = modinfo.load(source)
    game = paths.game()
    if not game.mods:
        raise FileNotFoundError("no Mods directory; has the game been run on this machine?")
    game.mods.mkdir(parents=True, exist_ok=True)
    destination = game.mods / source.name

    if destination.exists() or is_link(destination):
        linked = is_link(destination)
        if not force:
            if linked and link_target(destination).resolve() == source:
                return f"{info.id} already linked from {destination}"
            existing = link_target(destination) if linked else "a copy"
            return f"{destination} already exists ({existing}); pass --force to replace it"
        if linked or destination.is_file():
            remove_link(destination)
        else:
            shutil.rmtree(destination)

    if link:
        make_link(source, destination)
        return f"linked {info.id}: {destination} -> {source}"
    shutil.copytree(source, destination)
    return f"copied {info.id} into {destination}"


def uninstall(name: str) -> str:
    game = paths.game()
    if not game.mods:
        return "no Mods directory"
    target = game.mods / name
    if not target.exists() and not is_link(target):
        return f"{name} is not installed"
    if is_link(target) or target.is_file():
        remove_link(target)
        return f"removed the link {target} (the source directory is untouched)"
    shutil.rmtree(target)
    return f"removed {target}"
