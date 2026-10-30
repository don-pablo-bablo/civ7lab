"""`civ7lab workshop`: set the tags, description or preview image of a Steam
Workshop item, or upload a new version of its mod.

Under Proton, the SDK's Workshop Uploader will not tick its tag checkboxes,
and Steam's web page has no tag editor for this game. This makes the same
calls the uploader makes: StartItemUpdate, SetItemTags, SetItemDescription,
SetItemPreview or SetItemContent, then SubmitItemUpdate with the release
notes, if any. Nothing else about the item changes. Steam's web page cannot
change the preview image either: it only edits the extra images.

Writing goes through the running Steam client, via Steam's API library and
ctypes: see paths.steam_api_library. Reading goes through the public web API,
which needs no key.
"""

from __future__ import annotations

import contextlib
import ctypes
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

from . import paths

# The uploader's config: items belong to the game, and are uploaded as the SDK.
CONSUMER_APP_ID = 1295660
CREATOR_APP_ID = 3688890

# The uploader's checkboxes, as exact strings.
CATEGORIES = (
    "Ages",
    "AI",
    "Audio",
    "Buildings",
    "Civics",
    "Civilizations",
    "Climate",
    "Crises",
    "Game Setup",
    "Gameplay Overhaul",
    "Gameplay Tweaks",
    "Governments",
    "Leaders",
    "Legacy Paths",
    "Localization",
    "Maps",
    "Mementos",
    "Narrative Events",
    "Natural Wonders",
    "Religions",
    "Resources",
    "Scenario",
    "Skins",
    "Technologies",
    "UI",
    "Units",
    "Victories",
    "Wonders",
)
ITEM_TYPES = ("Mod", "Map", "Saved Game", "Language Pack")
KNOWN = {name.lower(): name for name in ITEM_TYPES + CATEGORIES}

DETAILS_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

INVALID_HANDLE = 0xFFFFFFFFFFFFFFFF
SUBMIT_RESULT_CALLBACK = 3404  # k_iSteamUGCCallbacks + 4
EResult = {
    1: "OK",
    2: "Fail",
    3: "NoConnection",
    8: "InvalidParam",
    9: "FileNotFound",
    15: "AccessDenied",
    16: "Timeout",
    25: "LimitExceeded",
}
INIT_RESULT = {
    1: "failed",
    2: "no Steam client running",
    3: "the Steam client is older than this library",
}


class WorkshopError(Exception):
    pass


def resolve_tags(names: list[str]) -> list[str]:
    """The exact tag strings for the given names, with Mod always first.

    SetItemTags replaces the whole list, so a list without Mod would take the
    item out of the Mod filter. Case is ignored; anything not on the
    uploader's lists is refused.
    """
    wanted = [part.strip() for name in names for part in name.split(",")]
    wanted = [name for name in wanted if name]
    unknown = [name for name in wanted if name.lower() not in KNOWN]
    if unknown:
        raise WorkshopError(
            "not a Civ VII Workshop tag: "
            + ", ".join(unknown)
            + "\n  item types: "
            + ", ".join(ITEM_TYPES)
            + "\n  categories: "
            + ", ".join(CATEGORIES)
        )
    tags = ["Mod"]
    for name in wanted:
        tag = KNOWN[name.lower()]
        if tag not in tags:
            tags.append(tag)
    return tags


# --------------------------------------------------------------------------
# reading: the public web API
# --------------------------------------------------------------------------


@dataclass
class Item:
    id: str
    title: str
    creator: str
    consumer_app_id: int
    tags: list[str] = field(default_factory=list)
    description: str = ""
    updated: int = 0  # Unix time of the last update
    preview_url: str = ""


def parse_details(payload: dict, item_id: str) -> Item:
    entries = payload.get("response", {}).get("publishedfiledetails") or []
    entry = next((e for e in entries if str(e.get("publishedfileid")) == item_id), None)
    if not entry or entry.get("result") != 1:
        raise WorkshopError(f"no public Workshop item {item_id} (wrong ID, or the item is private)")
    return Item(
        id=item_id,
        title=entry.get("title", ""),
        creator=str(entry.get("creator", "")),
        consumer_app_id=int(entry.get("consumer_app_id", 0)),
        tags=[t["tag"] for t in entry.get("tags", []) if "tag" in t],
        description=entry.get("description", ""),
        updated=int(entry.get("time_updated", 0)),
        preview_url=entry.get("preview_url", ""),
    )


def details(item_id: str, timeout: float = 15.0) -> Item:
    body = urllib.parse.urlencode({"itemcount": 1, "publishedfileids[0]": item_id}).encode()
    try:
        with urllib.request.urlopen(DETAILS_URL, data=body, timeout=timeout) as reply:
            payload = json.load(reply)
    except OSError as error:
        raise WorkshopError(f"could not reach the Steam web API: {error}") from error
    return parse_details(payload, item_id)


# --------------------------------------------------------------------------
# writing: the Steam client
# --------------------------------------------------------------------------


class SteamParamStringArray(ctypes.Structure):
    _fields_ = [("strings", ctypes.POINTER(ctypes.c_char_p)), ("count", ctypes.c_int32)]


class SubmitItemUpdateResult(ctypes.Structure):
    # Steam packs callbacks to 4 bytes on Linux; the uint64 lands at offset 8
    # either way. `_pack_` needs the "ms" layout, which Python 3.19 will no
    # longer assume.
    _layout_ = "ms"
    _pack_ = 4
    _fields_ = [
        ("result", ctypes.c_int32),
        ("needs_legal_agreement", ctypes.c_bool),
        ("item_id", ctypes.c_uint64),
    ]


_library: ctypes.CDLL | None = None

# The interfaces used, with the versions that have the calls made through
# them, newest first. The Steam runtime's library has SteamUtils v011, the
# one the game ships v010; the calls used are the same in both.
INTERFACES = {
    "SteamAPI_SteamUGC": ("v021",),
    "SteamAPI_SteamUtils": ("v011", "v010"),
    "SteamAPI_SteamUser": ("v023",),
}


def interface(lib, name: str, versions: tuple[str, ...]):
    """The library's function for the first of an interface's versions it
    has: SteamAPI_SteamUtils_v011, or else SteamAPI_SteamUtils_v010."""
    for version in versions:
        function = getattr(lib, f"{name}_{version}", None)
        if function is not None:
            return function
    raise WorkshopError(f"the Steam API library has no {name} of version {', '.join(versions)}")


def _load(path: Path | None = None) -> ctypes.CDLL:
    global _library
    if _library is not None:
        return _library
    path = path or paths.steam_api_library()
    if not path:
        raise FileNotFoundError(
            "no Steam API library: on Linux, libsteam_api.so under Steam's steamrt64/; "
            "on Windows, steam_api64.dll in the game's Base/Binaries/Win64"
        )
    lib = ctypes.CDLL(str(path))
    u64, u32, ptr = ctypes.c_uint64, ctypes.c_uint32, ctypes.c_void_p
    # Each interface under the name of the first version the library has.
    for name, versions in INTERFACES.items():
        function = interface(lib, name, versions)
        function.argtypes = []
        function.restype = ptr
        setattr(lib, name, function)
    signatures = {
        "SteamAPI_InitFlat": ([ctypes.c_char_p], ctypes.c_int),
        "SteamAPI_Shutdown": ([], None),
        "SteamAPI_RunCallbacks": ([], None),
        "SteamAPI_ISteamUser_BLoggedOn": ([ptr], ctypes.c_bool),
        "SteamAPI_ISteamUser_GetSteamID": ([ptr], u64),
        "SteamAPI_ISteamUGC_StartItemUpdate": ([ptr, u32, u64], u64),
        "SteamAPI_ISteamUGC_SetItemTags": (
            [ptr, u64, ctypes.POINTER(SteamParamStringArray), ctypes.c_bool],
            ctypes.c_bool,
        ),
        "SteamAPI_ISteamUGC_SetItemDescription": ([ptr, u64, ctypes.c_char_p], ctypes.c_bool),
        "SteamAPI_ISteamUGC_SetItemContent": ([ptr, u64, ctypes.c_char_p], ctypes.c_bool),
        "SteamAPI_ISteamUGC_SetItemPreview": ([ptr, u64, ctypes.c_char_p], ctypes.c_bool),
        "SteamAPI_ISteamUGC_GetItemUpdateProgress": (
            [ptr, u64, ctypes.POINTER(u64), ctypes.POINTER(u64)],
            ctypes.c_int,
        ),
        "SteamAPI_ISteamUGC_SubmitItemUpdate": ([ptr, u64, ctypes.c_char_p], u64),
        "SteamAPI_ISteamUtils_IsAPICallCompleted": (
            [ptr, u64, ctypes.POINTER(ctypes.c_bool)],
            ctypes.c_bool,
        ),
        "SteamAPI_ISteamUtils_GetAPICallResult": (
            [ptr, u64, ptr, ctypes.c_int, ctypes.c_int, ctypes.POINTER(ctypes.c_bool)],
            ctypes.c_bool,
        ),
    }
    for name, (argtypes, restype) in signatures.items():
        function = getattr(lib, name)
        function.argtypes = argtypes
        function.restype = restype
    _library = lib
    return lib


@contextlib.contextmanager
def _stdout_to_stderr():
    """libsteam_api prints breakpad notes to stdout, which would corrupt
    --json output."""
    sys.stdout.flush()
    saved = os.dup(1)
    os.dup2(2, 1)
    try:
        yield
    finally:
        os.dup2(saved, 1)
        os.close(saved)


class Steam:
    """One SteamAPI session running as `app_id`."""

    def __init__(self, app_id: int):
        self.app_id = app_id
        self.lib = _load()

    def __enter__(self) -> Steam:
        # SteamAPI_Init takes the app ID from the environment, under these
        # exact names.
        os.environ["SteamAppId"] = str(self.app_id)  # noqa: SIM112
        os.environ["SteamGameId"] = str(self.app_id)  # noqa: SIM112
        message = ctypes.create_string_buffer(1024)
        with _stdout_to_stderr():
            code = self.lib.SteamAPI_InitFlat(message)
        if code != 0:
            text = message.value.decode(errors="replace") or INIT_RESULT.get(code, "")
            raise WorkshopError(f"Steam init as app {self.app_id} failed ({code}): {text}")
        self.ugc = self.lib.SteamAPI_SteamUGC()
        self.utils = self.lib.SteamAPI_SteamUtils()
        self.user = self.lib.SteamAPI_SteamUser()
        if not (self.ugc and self.utils and self.user):
            self.lib.SteamAPI_Shutdown()
            raise WorkshopError("Steam started but gave no UGC, utils or user interface")
        return self

    def __exit__(self, *exc) -> None:
        with _stdout_to_stderr():
            self.lib.SteamAPI_Shutdown()

    def steam_id(self) -> str:
        if not self.lib.SteamAPI_ISteamUser_BLoggedOn(self.user):
            raise WorkshopError("Steam is running but not logged on")
        return str(self.lib.SteamAPI_ISteamUser_GetSteamID(self.user))

    def update(
        self,
        item_id: str,
        tags: list[str] | None = None,
        description: str | None = None,
        content: Path | None = None,
        preview: Path | None = None,
        note: str | None = None,
        timeout: float = 120.0,
        progress=None,
    ) -> str:
        """Submit new tags, a new description, new content, a new preview
        image, or any of them, with `note` as the release notes.
        `progress(done, total)` hears the upload's bytes while it runs.
        Returns the EResult name; "OK" means it took."""
        handle = self.lib.SteamAPI_ISteamUGC_StartItemUpdate(
            self.ugc, CONSUMER_APP_ID, int(item_id)
        )
        if handle == INVALID_HANDLE:
            return "StartItemUpdate refused"
        if tags is not None:
            encoded = (ctypes.c_char_p * len(tags))(*(t.encode() for t in tags))
            array = SteamParamStringArray(encoded, len(tags))
            if not self.lib.SteamAPI_ISteamUGC_SetItemTags(
                self.ugc, handle, ctypes.byref(array), False
            ):
                return "SetItemTags refused"
        if description is not None and not self.lib.SteamAPI_ISteamUGC_SetItemDescription(
            self.ugc, handle, description.encode()
        ):
            return "SetItemDescription refused"
        # Steam wants an absolute path to a folder.
        if content is not None and not self.lib.SteamAPI_ISteamUGC_SetItemContent(
            self.ugc, handle, str(content.resolve()).encode()
        ):
            return "SetItemContent refused"
        if preview is not None and not self.lib.SteamAPI_ISteamUGC_SetItemPreview(
            self.ugc, handle, str(preview.resolve()).encode()
        ):
            return "SetItemPreview refused"
        call = self.lib.SteamAPI_ISteamUGC_SubmitItemUpdate(
            self.ugc, handle, note.encode() if note else None
        )
        if call == 0:
            return "SubmitItemUpdate refused"
        failed = ctypes.c_bool(False)
        deadline = time.monotonic() + timeout
        while not self.lib.SteamAPI_ISteamUtils_IsAPICallCompleted(
            self.utils, call, ctypes.byref(failed)
        ):
            if time.monotonic() > deadline:
                return f"no answer from Steam in {timeout:.0f}s"
            self.lib.SteamAPI_RunCallbacks()
            if progress:
                done, total = ctypes.c_uint64(0), ctypes.c_uint64(0)
                self.lib.SteamAPI_ISteamUGC_GetItemUpdateProgress(
                    self.ugc, handle, ctypes.byref(done), ctypes.byref(total)
                )
                progress(done.value, total.value)
            time.sleep(0.1)
        result = SubmitItemUpdateResult()
        if (
            not self.lib.SteamAPI_ISteamUtils_GetAPICallResult(
                self.utils,
                call,
                ctypes.byref(result),
                ctypes.sizeof(result),
                SUBMIT_RESULT_CALLBACK,
                ctypes.byref(failed),
            )
            or failed.value
        ):
            return "the submit call failed"
        name = EResult.get(result.result, f"EResult {result.result}")
        if name == "OK" and result.needs_legal_agreement:
            name = "OK, but the Workshop legal agreement is not accepted yet"
        return name


@dataclass
class Submitted:
    app_id: int | None
    attempts: list[tuple[int, str]]

    @property
    def ok(self) -> bool:
        return self.app_id is not None


def submit(
    item: Item,
    tags: list[str] | None = None,
    description: str | None = None,
    content: Path | None = None,
    preview: Path | None = None,
    note: str | None = None,
    app_ids: tuple[int, ...] = (CREATOR_APP_ID, CONSUMER_APP_ID),
    progress=None,
) -> Submitted:
    """Replace the item's tags, description, content or preview image, or any
    of them, with `note` as the release notes. Tries the SDK's app ID first,
    as the uploader does, and the game's if that fails."""
    attempts: list[tuple[int, str]] = []
    for app_id in app_ids:
        try:
            with Steam(app_id) as steam:
                owner = steam.steam_id()
                if item.creator and owner != item.creator:
                    raise WorkshopError(
                        f"item {item.id} belongs to {item.creator}, "
                        f"and Steam is logged on as {owner}"
                    )
                outcome = steam.update(
                    item.id,
                    tags=tags,
                    description=description,
                    content=content,
                    preview=preview,
                    note=note,
                    # An upload takes as long as the files take to send.
                    timeout=600.0 if content else 120.0,
                    progress=progress,
                )
        except WorkshopError as error:
            if "belongs to" in str(error) or "not logged on" in str(error):
                raise
            outcome = str(error)
        attempts.append((app_id, outcome))
        if outcome.startswith("OK"):
            return Submitted(app_id, attempts)
    return Submitted(None, attempts)


# Steam's limit on a description, in characters. Release notes share it.
DESCRIPTION_LIMIT = 8000


@dataclass
class ModFolder:
    path: Path
    modinfo: Path
    id: str
    version: str
    files: list[Path]

    @property
    def size(self) -> int:
        return sum(f.stat().st_size for f in self.files)


def mod_folder(path: Path) -> ModFolder:
    """The mod in `path`, checked as the game will read it once subscribed:
    the item's root is the mod's own folder, so its .modinfo sits at the top.
    A version starting with 0 makes the game list the mod but never load it."""
    if not path.is_dir():
        raise WorkshopError(f"{path} is not a folder")
    found = sorted(path.glob("*.modinfo"))
    if len(found) != 1:
        raise WorkshopError(
            f"{path} has {len(found)} .modinfo files at its top; a mod's folder has one"
        )
    try:
        root = ET.parse(found[0]).getroot()
    except ET.ParseError as error:
        raise WorkshopError(f"{found[0].name} does not parse: {error}") from error
    version = root.get("version", "")
    if not version or version.startswith("0"):
        raise WorkshopError(
            f"{found[0].name} has version {version or 'none'}; "
            "the game lists a mod whose version starts with 0 but never loads it"
        )
    files = sorted(f for f in path.rglob("*") if f.is_file())
    return ModFolder(path, found[0], root.get("id", ""), version, files)


# Steam's limit on a preview image, and the formats it shows.
PREVIEW_LIMIT = 1024 * 1024
PREVIEW_TYPES = (".jpg", ".jpeg", ".png", ".gif")


def preview_image(path: Path) -> Path:
    """`path`, checked as Steam will take it: a JPEG, PNG or GIF under 1 MB."""
    if not path.is_file():
        raise WorkshopError(f"{path} is not a file")
    if path.suffix.lower() not in PREVIEW_TYPES:
        raise WorkshopError(f"{path.name} is not a JPEG, PNG or GIF")
    size = path.stat().st_size
    if size >= PREVIEW_LIMIT:
        raise WorkshopError(f"{path.name} is {size / 1024:.0f} KB; Steam takes under 1024 KB")
    return path


def same_text(a: str, b: str) -> bool:
    """Whether two descriptions match, ignoring line endings and the blank
    lines around them."""
    return a.replace("\r\n", "\n").strip() == b.replace("\r\n", "\n").strip()


def read_back(item_id: str, done, wait: float = 60.0) -> Item:
    """Poll the web API until `done(item)` is true, or `wait` runs out. The
    public API can lag a submit by a minute."""
    deadline = time.monotonic() + wait
    while True:
        item = details(item_id)
        if done(item) or time.monotonic() > deadline:
            return item
        time.sleep(5)
