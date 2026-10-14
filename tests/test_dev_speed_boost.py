"""Dev Speed Boost is generated from tools/dev_speed_boost.py: the files under
mod/dev-speed-boost must be exactly what the generator writes."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "mod/dev-speed-boost"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "dev_speed_boost", ROOT / "tools/dev_speed_boost.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def files(folder: Path) -> dict[str, bytes]:
    """Each file's bytes, with Windows line endings read as Unix ones: git on
    Windows can check text out either way."""
    return {
        p.relative_to(folder).as_posix(): p.read_bytes().replace(b"\r\n", b"\n")
        for p in folder.rglob("*")
        if p.is_file()
    }


def test_the_committed_mod_is_what_the_generator_writes(tmp_path, capsys):
    out = tmp_path / "dev-speed-boost"
    out.mkdir()
    load_generator().build(out)
    built, committed = files(out), files(MOD)
    assert sorted(built) == sorted(committed), "run python3 tools/dev_speed_boost.py"
    stale = [name for name in built if built[name] != committed[name]]
    assert not stale, f"run python3 tools/dev_speed_boost.py; out of date: {stale}"
