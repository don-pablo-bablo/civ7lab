"""Finding the game on Linux, under Proton, and on Windows.

`paths.WINDOWS` decides which layout is used, so both are checked on any
system. The folders are real ones under a temporary home.
"""

import pytest

from civ7lab import paths

GAME = paths.GAME_NAME


@pytest.fixture
def home(tmp_path, monkeypatch):
    for variable in (paths.ENV_INSTALL, paths.ENV_USER):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(paths, "_steam_roots", lambda: [tmp_path / "Steam"])
    return tmp_path


def test_native_linux_keeps_its_files_in_my_games(home, monkeypatch):
    monkeypatch.setattr(paths, "WINDOWS", False)
    (home / "My Games" / GAME).mkdir(parents=True)
    assert paths.user_dir() == home / "My Games" / GAME


def test_proton_keeps_them_in_the_prefixs_local_app_data(home, monkeypatch):
    monkeypatch.setattr(paths, "WINDOWS", False)
    prefix = home / "Steam/steamapps/compatdata/1295660/pfx/drive_c/users/steamuser"
    folder = prefix / "AppData/Local/Firaxis Games" / GAME
    folder.mkdir(parents=True)
    assert paths.user_dir() == folder


def test_windows_keeps_them_in_local_app_data(home, monkeypatch):
    monkeypatch.setattr(paths, "WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData/Local"))
    folder = home / "AppData/Local/Firaxis Games" / GAME
    folder.mkdir(parents=True)
    assert paths.user_dir() == folder


@pytest.mark.parametrize(
    ("windows", "binary"),
    [
        (False, "Base/Binaries/linux/Civ7_linux_Vulkan_FinalRelease"),
        (True, "Base/Binaries/Win64/Civ7_Win64_DX12_FinalRelease.exe"),
    ],
)
def test_each_system_launches_its_own_build(home, monkeypatch, windows, binary):
    monkeypatch.setattr(paths, "WINDOWS", windows)
    install = home / "Steam/steamapps/common" / GAME
    for build in (
        "Base/Binaries/linux/Civ7_linux_Vulkan_FinalRelease",
        "Base/Binaries/Win64/Civ7_Win64_DX12_FinalRelease.exe",
    ):
        (install / build).parent.mkdir(parents=True, exist_ok=True)
        (install / build).write_bytes(b"")
    assert paths.executable() == install / binary


def test_a_second_steam_library_is_found(home, monkeypatch):
    library = home / "Games"
    (library / "steamapps/common" / GAME).mkdir(parents=True)
    vdf = home / "Steam/steamapps/libraryfolders.vdf"
    vdf.parent.mkdir(parents=True)
    vdf.write_text(
        f'"libraryfolders"\n{{\n  "1"\n  {{\n    "path" "{library}"\n  }}\n}}\n', encoding="utf-8"
    )
    assert paths.install_dir() == library / "steamapps/common" / GAME


def test_windows_library_paths_have_their_backslashes_undoubled():
    assert paths.vdf_path("D:\\\\SteamLibrary") == "D:\\SteamLibrary"
