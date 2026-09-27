"""Getting a mod into the game, and knowing which one the game will load.

Mods live in the user directory's Mods folder, and the practical way to develop
one is a symlink from there to the working copy, so an edit is in the game
without a copy step and there is only ever one version of the file. The trap is
the other direction: an old copy sitting beside the link, or a link to a moved
directory, and the game happily loading something that is not what is being
edited.
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
    kind: str          # "link" or "copy"
    target: Path | None
    valid: bool


def installed() -> list[Installed]:
    game = paths.game()
    if not game.mods or not game.mods.is_dir():
        return []
    out = []
    for entry in sorted(game.mods.iterdir()):
        if entry.name.startswith("."):
            continue
        if entry.is_symlink():
            target = Path(os.readlink(entry))
            out.append(Installed(entry.name, entry, "link", target, target.exists()))
        else:
            out.append(Installed(entry.name, entry, "copy", None, entry.is_dir()))
    return out


def install(source: str | Path | None = None, link: bool = True, force: bool = False) -> str:
    """Put a mod directory where the game will find it.

    Defaults to this toolkit's own probe mod, which is the common case: the
    thing being installed is the instrumentation, and the mod under test is
    already there.
    """
    source = Path(source) if source else PROBE_SOURCE
    source = source.resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"no such mod directory: {source}")
    # A directory with no modinfo will be ignored by the game in silence, which
    # is the failure this catches.
    info = modinfo.load(source)
    game = paths.game()
    if not game.mods:
        raise FileNotFoundError("no Mods directory; has the game been run on this machine?")
    game.mods.mkdir(parents=True, exist_ok=True)
    destination = game.mods / source.name

    if destination.exists() or destination.is_symlink():
        if not force:
            existing = os.readlink(destination) if destination.is_symlink() else "a copy"
            if destination.is_symlink() and Path(existing).resolve() == source:
                return f"{info.id} already linked from {destination}"
            return (f"{destination} already exists ({existing}); "
                    "pass --force to replace it")
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        else:
            shutil.rmtree(destination)

    if link:
        destination.symlink_to(source, target_is_directory=True)
        return f"linked {info.id}: {destination} -> {source}"
    shutil.copytree(source, destination)
    return f"copied {info.id} into {destination}"


def uninstall(name: str) -> str:
    game = paths.game()
    if not game.mods:
        return "no Mods directory"
    target = game.mods / name
    if not target.exists() and not target.is_symlink():
        return f"{name} is not installed"
    if target.is_symlink() or target.is_file():
        target.unlink()
        return f"removed the link {target} (the source directory is untouched)"
    shutil.rmtree(target)
    return f"removed {target}"
