"""Talking to a game that is already running.

This is the fast loop. The probe's collectors are registered inside the game,
so a question is one round trip: `collect("tile", {"x": 20, "y": 7})` comes
back as a dict, and nothing was reloaded, logged, screenshotted or read by eye.

The part that matters most here is `ensure_probe`. The probe does not have to
be installed as a mod at all: its scripts are plain, import-free JavaScript, so
they can be pushed into the running game over the debugger and registered on
the spot. Instrumentation can then be added to a game in progress, including
one running somebody else's mod or none, without restarting it or touching the
mod list. The mod packaging exists for the other case,
where a run is unattended and there is nobody there to attach.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import cdp, records

PROBE_DIR = Path(__file__).resolve().parents[1] / "mod/civ7lab-probe/ui"
# Order matters: the runtime first, then the collectors that register on it.
# The plan and the hooks are for unattended runs and are not injected, because
# a live session fires collectors by asking, not by waiting for a turn.
PROBE_FILES = ["lab-core.js", "lab-collect.js"]


class Probe:
    """A live session with the probe guaranteed present."""

    def __init__(self, session: cdp.Session):
        self.session = session
        self.build = None

    # -- installation -----------------------------------------------------
    def ensure(self, force: bool = False) -> str:
        """Install or refresh the probe inside the running game.

        Re-injecting a build that is already there is a no-op on the game side,
        so this is cheap to call before every question and removes the class of
        mistake where a measurement is taken against an older probe.
        """
        source_build = _source_build()
        if not force:
            present = self.session.evaluate(
                "typeof globalThis.C7Lab === 'object' ? globalThis.C7Lab.build : null")
            if present and present == source_build:
                self.build = present
                return f"probe {present} already present"
        for name in PROBE_FILES:
            path = PROBE_DIR / name
            if not path.is_file():
                raise FileNotFoundError(f"probe source missing: {path}")
            self.session.evaluate(path.read_text(), await_promise=False)
        self.build = self.session.evaluate("globalThis.C7Lab && globalThis.C7Lab.build")
        if not self.build:
            raise cdp.CDPError("probe did not install; the target may not be the game UI context")
        return f"probe {self.build} injected"

    # -- asking -----------------------------------------------------------
    # The arguments go in as one dict rather than as keywords. A collector
    # argument called "name", which is how a city is picked, would otherwise
    # collide with the collector's own name and fail before it reached the
    # game.
    def collect(self, collector: str, args: dict | None = None):
        return self.session.call("(n, a) => C7Lab.collect(n, a)", collector, args or {})

    def dump(self, collector: str, args: dict | None = None):
        """Collect and also print to the log, for a record that outlives the game."""
        return self.session.call("(n, a) => C7Lab.dump(n, a)", collector, args or {})

    def collectors(self) -> dict:
        return self.session.evaluate("C7Lab.list()")

    def members(self, target: str):
        """What an engine object actually has on it. The question that used to
        cost a reload and forty lines of log."""
        return self.session.call("(t) => C7Lab.members(t)", target)

    def evaluate(self, expression: str):
        return self.session.evaluate(expression)

    def snapshot(self, spec: list[tuple[str, dict]]) -> dict:
        """Several collectors in one go, stamped with when and what.

        The stamp is the point: a snapshot without the turn and the build it was
        taken at cannot be compared with another one honestly.
        """
        taken = {"taken": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "probe": self.build, "data": {}}
        game = self.collect("game")
        taken["turn"] = game.get("turn") if isinstance(game, dict) else None
        taken["age"] = game.get("age") if isinstance(game, dict) else None
        for name, args in spec:
            key = name if not args else f"{name}({json.dumps(args, sort_keys=True)})"
            taken["data"][key] = self.collect(name, args)
        return taken

    # -- watching ---------------------------------------------------------
    def watch(self, seconds: float = 30.0, marker: str = records.MARKER):
        """Console output as it happens, with the probe's records decoded.

        The log file is truncated at every launch and only written to disk when
        the engine feels like it; this is the same information, live.
        """
        self.session.enable_console()
        deadline = time.monotonic() + seconds
        seen: list = []
        while time.monotonic() < deadline:
            self.session.pump(min(1.0, deadline - time.monotonic()))
            for line in self.session.drain_console():
                text = line.get("text", "")
                if marker and marker not in text and records.CHUNK_MARKER not in text:
                    continue
                seen.append(text)
                yield line
        return seen


def _source_build() -> str | None:
    core = PROBE_DIR / "lab-core.js"
    if not core.is_file():
        return None
    for line in core.read_text().splitlines():
        if "var BUILD" in line and "=" in line:
            return line.split('"')[1] if '"' in line else None
    return None


def attach(host: str | None = None, port: int | None = None, match: str | None = None,
           install: bool = True, timeout: float = 30.0) -> Probe:
    session = cdp.connect(host=host, port=port, match=match, timeout=timeout)
    probe = Probe(session)
    if install:
        probe.ensure()
    return probe
