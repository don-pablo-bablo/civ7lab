"""`civ7lab live`: questions to a running game.

`collect("tile", {"x": 20, "y": 7})` runs the probe's tile collector in the
game and returns a dict in one round trip.

The probe need not be installed as a mod. Its scripts import nothing, so
`Probe.ensure` pushes them into the running game over the inspector. That
works on any game in progress, with any mods. The probe mod is for unattended
runs, where nothing attaches.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

from . import cdp, records

PROBE_DIR = Path(__file__).resolve().parents[1] / "mod/civ7lab-probe/ui"
# In this order: the runtime, then the collectors that register on it. The
# plan and hooks only serve unattended runs, so they are not injected.
PROBE_FILES = ["lab-core.js", "lab-collect.js"]
# The files the build stamp covers: everything the probe mod loads except the
# generated plan.
STAMPED_FILES = ["lab-core.js", "lab-collect.js", "lab-hooks.js"]
_BUILD_LINE = re.compile(r'var BUILD = "[^"]*";')


def probe_id(folder: Path = PROBE_DIR) -> str:
    """A hash of the probe's files, ignoring the stamp line itself.

    `live` compares it with the game's copy to decide whether to inject, so an
    edited probe reaches the game with no step to remember. lab-core.js prints
    it as its build stamp; tests/test_probe.py checks the two agree.
    """
    digest = hashlib.sha1()
    for name in STAMPED_FILES:
        text = (folder / name).read_text(encoding="utf-8")
        digest.update(_BUILD_LINE.sub('var BUILD = "";', text).encode())
    return "probe-" + digest.hexdigest()[:8]


class Probe:
    """A live session with the probe guaranteed present."""

    def __init__(self, session: cdp.Session):
        self.session = session
        self.build = None

    # -- installation -----------------------------------------------------
    def ensure(self, force: bool = False) -> str:
        """Inject the probe unless the game already runs the files as they
        are on disk, so a question never runs against an older probe.

        A probe loaded by the game from its files reports its build stamp. One
        injected here also carries `source`, the hash it was injected at,
        which stays right even if an edit left the stamp stale.
        """
        wanted = probe_id()
        if not force:
            present = self.session.evaluate(
                "typeof globalThis.C7Lab === 'object' ? "
                "[globalThis.C7Lab.source, globalThis.C7Lab.build] : null"
            )
            if present and wanted in present:
                self.build = wanted
                return f"probe {wanted} already present"
        for name in PROBE_FILES:
            path = PROBE_DIR / name
            if not path.is_file():
                raise FileNotFoundError(f"probe source missing: {path}")
            self.session.evaluate(path.read_text(encoding="utf-8"), await_promise=False)
        installed = self.session.evaluate(
            f"globalThis.C7Lab ? (globalThis.C7Lab.source = {json.dumps(wanted)}) : null"
        )
        if installed != wanted:
            raise cdp.CDPError("probe did not install; the target may not be the game UI context")
        self.build = wanted
        return f"probe {wanted} injected"

    # -- asking -----------------------------------------------------------
    # Collector arguments are one dict rather than keywords, since the city
    # collector's "name" argument would clash with the collector name.
    def collect(self, collector: str, args: dict | None = None):
        return self.session.call("(n, a) => C7Lab.collect(n, a)", collector, args or {})

    def dump(self, collector: str, args: dict | None = None):
        """Collect and also print to the log, for a record that outlives the game."""
        return self.session.call("(n, a) => C7Lab.dump(n, a)", collector, args or {})

    def collectors(self) -> dict:
        return self.session.evaluate("C7Lab.list()")

    def members(self, target: str):
        """Every property and method of an engine object, up its prototype
        chain."""
        return self.session.call("(t) => C7Lab.members(t)", target)

    def autoplay(self, turns: int | None, observe: int = 0) -> bool:
        """Let the AI play `turns` turns, or stop with None. The same calls the
        game's LoadGame automation makes. Stopping takes effect at the end of
        the turn in progress, and autoplay also stops by itself when an age
        ends. Returns whether autoplay is on straight afterwards."""
        if turns is None:
            return self.session.evaluate("Autoplay.setActive(false); Autoplay.isActive")
        return self.session.evaluate(
            f"Autoplay.setTurns({int(turns)}); Autoplay.setReturnAsPlayer(0); "
            f"Autoplay.setObserveAsPlayer({int(observe)}); Autoplay.setActive(true); "
            "Autoplay.isActive"
        )

    def evaluate(self, expression: str):
        return self.session.evaluate(expression)

    def snapshot(self, spec: list[tuple[str, dict]]) -> dict:
        """Several collectors in one dict, stamped with the time, turn, age and
        probe build, so two snapshots can be compared."""
        taken = {"taken": time.strftime("%Y-%m-%d %H:%M:%S"), "probe": self.build, "data": {}}
        game = self.collect("game")
        taken["turn"] = game.get("turn") if isinstance(game, dict) else None
        taken["age"] = game.get("age") if isinstance(game, dict) else None
        for name, args in spec:
            key = name if not args else f"{name}({json.dumps(args, sort_keys=True)})"
            taken["data"][key] = self.collect(name, args)
        return taken

    # -- watching ---------------------------------------------------------
    def watch(self, seconds: float = 30.0, marker: str = records.MARKER):
        """The game's console lines containing `marker`, as they print. An
        empty marker gives every line, including console.log, which UI.log
        never receives."""
        self.session.enable_console()
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.session.pump(min(1.0, deadline - time.monotonic()))
            for line in self.session.drain_console():
                text = line.get("text", "")
                if marker and marker not in text and records.CHUNK_MARKER not in text:
                    continue
                yield line


def attach(
    host: str | None = None,
    port: int | None = None,
    match: str | None = None,
    install: bool = True,
    timeout: float = 30.0,
) -> Probe:
    session = cdp.connect(host=host, port=port, match=match, timeout=timeout)
    probe = Probe(session)
    if install:
        probe.ensure()
    return probe
