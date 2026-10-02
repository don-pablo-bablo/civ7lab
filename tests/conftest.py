"""Fixtures the tests share.

Tests use real files and real processes where they can. The game is stood in
for by folders laid out as the game lays them out, pointed at through
CIV7_INSTALL and CIV7_USER, so the code under test runs unchanged.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from civ7lab import paths

ROOT = Path(__file__).resolve().parents[1]
PROBE_UI = ROOT / "mod/civ7lab-probe/ui"


@dataclass
class Game:
    install: Path
    user: Path

    def add_executable(self) -> Path:
        """An empty game binary: enough for everything short of launching."""
        binary = self.install / (
            "Base/Binaries/Win64/Civ7_Win64_DX12_FinalRelease.exe"
            if paths.WINDOWS
            else "Base/Binaries/linux/Civ7_linux_Vulkan_FinalRelease"
        )
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_bytes(b"")
        return binary


@pytest.fixture
def game(tmp_path, monkeypatch) -> Game:
    """An install folder and a user folder, as the game lays them out."""
    install, user = tmp_path / "install", tmp_path / "user"
    (install / "Base/modules").mkdir(parents=True)
    for folder in ("Logs", "Mods", "Saves/Single", "Debug"):
        (user / folder).mkdir(parents=True)
    monkeypatch.setenv(paths.ENV_INSTALL, str(install))
    monkeypatch.setenv(paths.ENV_USER, str(user))
    return Game(install, user)


_DRIVER = """
const vm = require("vm");
const input = JSON.parse(require("fs").readFileSync(0, "utf8"));
const lines = [];
const context = { console: { error: (t) => lines.push(String(t)), log: () => {} }, lines };
vm.createContext(context);
context.load = (name) => vm.runInContext(input.sources[name], context, { filename: name });
for (const name of input.files) context.load(name);
for (const script of input.scripts) vm.runInContext(script, context);
const result = vm.runInContext(input.body, context, { filename: "test" });
process.stdout.write(JSON.stringify({ result: result === undefined ? null : result, lines }));
"""


@pytest.fixture
def js():
    """Run probe scripts in Node, then a body of JavaScript.

    `js(body, files, scripts)` loads the probe `files`, then runs `scripts`,
    in a fresh context whose only extra globals are `console`, `lines` and
    `load(name)`, which runs any probe script again. `console.error` lines,
    what UI.log would receive, are collected. Returns
    {"result": <body's value, or None>, "lines": [...]}.
    """
    node = shutil.which("node")
    if not node:
        pytest.fail("the probe tests need Node: https://nodejs.org")
    sources = {path.name: path.read_text(encoding="utf-8") for path in PROBE_UI.glob("*.js")}

    def run(body: str, files: list[str] = (), scripts: list[str] = ()) -> dict:
        completed = subprocess.run(
            [node, "-e", _DRIVER],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            input=json.dumps(
                {"sources": sources, "files": list(files), "scripts": list(scripts), "body": body}
            ),
        )
        if completed.returncode:
            raise AssertionError(f"node failed:\n{completed.stderr}")
        return json.loads(completed.stdout)

    return run
