"""Patch a mod's UI scripts into the running game every time a file is saved.

The old loop for a panel or a tooltip was: edit, restart the game, load the
save, get back to the tile, look. This one is: save, look. Each save goes to
the game's V8 as Debugger.setScriptSource, which is V8's live edit: the
functions of the module already loaded are replaced in place, so every module
that imported them calls the new code from its next call on, and nothing in
the mod has to be written differently to allow it.

Confirmed on 21 September 2026 against civ6point9's c69-yield-panel.js, a
module imported by another module at game start: a patched string showed in
the tooltip that importer draws, with no reload.

What live edit cannot do is run anything again. Code outside a function, such
as a constant, a lookup table or a registration call, ran once when the game
loaded the file, and a patch changes the text of it without running it. So every
change is sorted into "inside a function" (takes effect on the next call) and
"runs once at load" (warned about), by a brace scanner that is deliberately
simple: it is a warning, never a refusal.

A patch that does not compile is rejected by V8 before anything is swapped, so
a typo costs an error line here and nothing in the game.
"""

from __future__ import annotations

import difflib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path

from . import cdp

# Dispatched on window after every successful patch, with {url} as detail. A
# panel that wants to redraw itself on a patch listens for it; one that does
# not is simply redrawn the next time the game draws it.
PATCHED_EVENT = "civ7lab-patched"


class NoneLoaded(cdp.CDPError):
    """Connected, but to a UI holding none of the watched files.

    The inspector answers at the main menu, on a load screen and for a moment
    while the game shuts down, from a UI the mod's scripts are not part of.
    That is not the game yet, and telling the user every file "needs a
    restart" there would be wrong, so the watcher waits instead.
    """


# --------------------------------------------------------------------------
# Which loaded script is this file?
# --------------------------------------------------------------------------

def mod_root(path: Path) -> Path | None:
    """The nearest directory above `path` holding a .modinfo."""
    for directory in [path.parent, *path.parents]:
        if any(directory.glob("*.modinfo")):
            return directory
    return None


def resolve(urls: dict[str, str], path: Path, root: Path) -> tuple[str | None, str | None]:
    """The game URL a local file was loaded as, or why there is none.

    The game serves a mod's files as fs://game/<folder>/<path in the mod>, and
    the folder is whatever the mod is installed as, which need not match the
    checkout's name. So the match is on the path inside the mod, and the
    folder name only breaks a tie.
    """
    relative = path.resolve().relative_to(root.resolve()).as_posix()
    found = [url for url in urls if url.endswith("/" + relative)]
    if len(found) > 1:
        preferred = [url for url in found if f"/{root.name}/{relative}" in url]
        found = preferred or found
    if len(found) == 1:
        return found[0], None
    if found:
        return None, f"{relative} matches {len(found)} loaded scripts: {', '.join(found)}"
    return None, (f"{relative} is not loaded in the game. A file the game did not load at "
                  "start (not in the modinfo, or not for this age) needs a restart, not a patch.")


# --------------------------------------------------------------------------
# Inside a function, or run once at load?
# --------------------------------------------------------------------------

_NOT_FUNCTIONS = {"if", "for", "while", "switch", "catch", "with", "else", "do", "try",
                  "finally", "return", "typeof", "new", "await", "yield"}
_METHOD_HEAD = re.compile(r"^(?:(?:async|static|get|set)\s+|\*\s*)*([#\w$]+)\s*\(.*\)\s*$", re.S)


def _brace_kind(head: str) -> str:
    """What a `{` opens, judged from the statement text before it.

    "once" is the body of a function invoked where it is written, as in
    `(function () { ... })()` or `(async () => { ... })()`. It is a function,
    but its body ran exactly once, when the file loaded, so for patching it is
    load-time code like the top level. Functions nested inside it are not.
    """
    head = head.strip()
    if re.search(r"\bfunction\b", head) or head.endswith("=>"):
        return "once" if re.match(r"^[(!]", head) else "fn"
    method = _METHOD_HEAD.match(head)
    return "fn" if method and method.group(1) not in _NOT_FUNCTIONS else "block"


@dataclass
class _Line:
    in_function: bool = False   # any of the line is inside a function body
    has_code: bool = False      # anything besides whitespace and comments


def scan(source: str) -> list[_Line]:
    """Per line: is it code, and does any of it sit inside a function body.

    Strings, template literals (with nested ${}) and comments are skipped so
    their braces do not count. Regex literals are not recognised; a brace in
    one can mislead the result, which only ever costs a wrong warning.
    """
    lines = [_Line()]
    stack: list[str] = []          # "fn", "block", or "interp" for a template's ${
    head = ""                      # the statement text before the next brace
    state = "code"                 # code, line, block, ', ", or `
    index = 0
    length = len(source)

    def in_function() -> bool:
        return "fn" in stack

    while index < length:
        char = source[index]
        ahead = source[index + 1] if index + 1 < length else ""
        line = lines[-1]
        if char == "\n":
            if state == "line":
                state = "code"
            lines.append(_Line(in_function=in_function()))
            head += " "
            index += 1
            continue
        if state == "line":
            index += 1
            continue
        if state == "block":
            if char == "*" and ahead == "/":
                state = "code"
                index += 1
            index += 1
            continue
        if state in ("'", '"'):
            line.has_code = True
            if char == "\\":
                # Skip the escaped character, but never a newline, or the
                # line count would drift from the file's.
                index += 1 if ahead == "\n" else 2
                continue
            if char == state:
                state = "code"
                head += "0"
            index += 1
            continue
        if state == "`":
            line.has_code = True
            if char == "\\":
                # Skip the escaped character, but never a newline, or the
                # line count would drift from the file's.
                index += 1 if ahead == "\n" else 2
                continue
            if char == "`":
                state = "code"
                head += "0"
            elif char == "$" and ahead == "{":
                stack.append("interp")
                state = "code"
                index += 1
            index += 1
            continue
        # plain code
        if char == "/" and ahead == "/":
            state = "line"
            index += 2
            continue
        if char == "/" and ahead == "*":
            state = "block"
            index += 2
            continue
        if not char.isspace():
            line.has_code = True
        if char in ("'", '"', "`"):
            state = char
        elif char == "{":
            stack.append(_brace_kind(head))
            head = ""
            if stack[-1] == "fn":
                line.in_function = True
        elif char == "}":
            if stack and stack[-1] == "interp":
                stack.pop()
                state = "`"
            elif stack:
                stack.pop()
            head = ""
        elif char == ";":
            head = ""
        else:
            head += char
        index += 1
    return lines


def load_time_changes(old: str, new: str) -> list[str]:
    """The changed lines that sit outside every function, as labels."""
    old_lines, new_lines = old.split("\n"), new.split("\n")
    old_scan, new_scan = scan(old), scan(new)
    flagged: list[str] = []
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        for j in range(j1, j2):
            info = new_scan[j]
            if info.has_code and not info.in_function:
                flagged.append(f"line {j + 1}")
        if tag == "delete":
            for i in range(i1, i2):
                info = old_scan[i]
                if info.has_code and not info.in_function:
                    flagged.append(f"removed line {i + 1}")
    return flagged


def _summarise(labels: list[str], limit: int = 4) -> str:
    shown = ", ".join(labels[:limit])
    return shown + (f" and {len(labels) - limit} more" if len(labels) > limit else "")


# --------------------------------------------------------------------------
# What the game said
# --------------------------------------------------------------------------

_STATUS = {
    "CompileError": "did not compile",
    "BlockedByActiveGenerator": "a generator from this file is suspended; try again",
    "BlockedByActiveFunction": "a function from this file is running; try again",
    "BlockedByTopLevelEsModuleChange": "this V8 refuses changes to a module's top level",
}


def interpret(reply: dict) -> tuple[bool, str]:
    """(accepted, message) from a Debugger.setScriptSource reply.

    V8 9.4, the game's, reports a compile error as exceptionDetails; newer V8
    uses a status field. Both are read, so a game update does not turn a
    rejected patch into a silently "successful" one.
    """
    details = reply.get("exceptionDetails")
    if details:
        text = (details.get("exception", {}).get("description") or details.get("text") or "")
        where = f"line {details.get('lineNumber', -1) + 1}:{details.get('columnNumber', -1) + 1}"
        return False, f"did not compile, {where}: {text.strip()}"
    status = reply.get("status")
    if status and status != "Ok":
        detail = reply.get("compileError", {}).get("message", "")
        return False, _STATUS.get(status, status) + (f": {detail}" if detail else "")
    return True, "patched"


# --------------------------------------------------------------------------
# The loop
# --------------------------------------------------------------------------

@dataclass
class _Watched:
    path: Path
    root: Path
    url: str | None = None
    script_id: str | None = None
    live: str | None = None           # the source the game is running now
    # The source as the game had it on attach: what its load-time code actually
    # ran as. Warnings compare against this, not the last patch, so they last
    # while the difference does and clear when an edit is undone. (A watcher
    # restarted mid-session takes a patched copy as its baseline; it cannot
    # know better.)
    loaded: str | None = None
    warned: bool = False              # a load-time warning is outstanding
    rejected: bool = False            # the last save did not compile
    seen: float | None = None         # mtime last read
    pending: float | None = None      # mtime seen changing, not yet settled
    problem: str | None = None        # last "cannot resolve" message, printed once


class Watcher:
    """Keeps the game's copy of each file equal to the file on disk.

    `connect` and `out` are parameters so the loop can be driven by a stub
    session in the tests; nothing here needs a real game to be exercised.
    """

    def __init__(self, files: list[Path], root: Path | None = None, after: str | None = None,
                 connect=None, out=print, port: int | None = None, target: str | None = None):
        self.files: list[_Watched] = []
        for path in files:
            path = Path(path).resolve()
            base = Path(root).resolve() if root else mod_root(path)
            if base is None:
                raise FileNotFoundError(f"no .modinfo above {path}; pass --root")
            self.files.append(_Watched(path=path, root=base))
        self.after = after
        self.out = out
        self._connect = connect or (lambda: cdp.connect(port=port, match=target, timeout=10))
        self.session = None
        self.urls: dict[str, str] = {}        # url -> scriptId

    # -- connection -------------------------------------------------------
    def attach(self) -> None:
        self.session = self._connect()
        self.session.events.clear()
        self.session.send("Debugger.enable")
        # Enabling replays a scriptParsed for everything already loaded; read
        # until the replay goes quiet so the map is complete before it is used.
        count = -1
        while count != len(self.session.events):
            count = len(self.session.events)
            self.session.pump(0.5)
        self.urls.clear()
        for watched in self.files:
            watched.url = watched.script_id = watched.live = watched.problem = None
            watched.loaded, watched.warned, watched.rejected = None, False, False
        self._drain()
        if not any(resolve(self.urls, w.path, w.root)[0] for w in self.files):
            self.close()
            raise NoneLoaded("connected, but none of the watched files are loaded there "
                             "(the main menu, a load screen, or the game shutting down?)")
        for watched in self.files:
            self._reconcile(watched)

    def close(self) -> None:
        if self.session:
            try:
                self.session.close()
            except Exception:  # noqa: BLE001: it is going away either way
                pass
        self.session = None

    def _drain(self) -> None:
        events, self.session.events = self.session.events, []
        parsed = False
        for event in events:
            method, params = event.get("method"), event.get("params", {})
            if method == "Debugger.scriptParsed" and params.get("url"):
                self.urls[params["url"]] = params["scriptId"]
                parsed = True
            elif method == "Debugger.paused":
                # Nothing of ours sets a breakpoint, and a paused debugger
                # freezes the whole game UI. A `debugger;` left in a script
                # is the usual cause.
                self.session.send("Debugger.resume")
                self._say(None, "the game paused in the debugger (a `debugger;` statement?); "
                                "resumed it")
        # A script loaded again (a new age reloads the UI) has a new id and the
        # file's current text, so the next check starts from what is on disk.
        # A file that was not loaded may have been by now.
        for watched in self.files:
            if watched.url and self.urls.get(watched.url) != watched.script_id:
                self._reconcile(watched)
            elif parsed and not watched.url and watched.seen is not None:
                self._reconcile(watched)

    # -- the work ---------------------------------------------------------
    def _reconcile(self, watched: _Watched) -> None:
        """Bring the game's copy of one file level with the disk."""
        url, problem = resolve(self.urls, watched.path, watched.root)
        if not url:
            if problem != watched.problem:
                self._say(watched, problem)
            watched.problem = problem
            watched.url = watched.script_id = None
            return
        watched.problem = None
        watched.url, watched.script_id = url, self.urls[url]
        watched.live = self.session.send("Debugger.getScriptSource",
                                         {"scriptId": watched.script_id}).get("scriptSource")
        watched.loaded, watched.warned, watched.rejected = watched.live, False, False
        watched.seen = self._mtime(watched.path)
        text = self._read(watched.path)
        if text is None or text == watched.live:
            self._say(watched, "in step with the game")
            return
        self._say(watched, "the game has an older copy than the file")
        self.push(watched, text)

    def push(self, watched: _Watched, text: str) -> bool:
        warnings = load_time_changes(watched.loaded, text) if watched.loaded is not None else []
        started = time.monotonic()
        try:
            reply = self.session.send("Debugger.setScriptSource",
                                      {"scriptId": watched.script_id, "scriptSource": text})
            accepted, message = interpret(reply)
        except cdp.CDPError as error:
            accepted, message = False, str(error)
        if not accepted:
            self._say(watched, f"REJECTED, {message}. The game still runs the previous version.")
            watched.rejected = True
            return False
        watched.live, watched.rejected = text, False
        self._say(watched, f"{message} ({time.monotonic() - started:.2f}s)")
        if warnings:
            self._say(watched, f"  warning: load-time code differs from what the game loaded "
                               f"({_summarise(warnings)}). It ran once, outside any function, "
                               "and a patch does not run it again: restart the game for it.")
            watched.warned = True
        elif watched.warned:
            self._say(watched, "  load-time code matches what the game loaded again; "
                               "no restart needed")
            watched.warned = False
        self._after_patch(watched.url)
        return True

    def _after_patch(self, url: str) -> None:
        detail = json.dumps({"url": url})
        expressions = [f"window.dispatchEvent(new CustomEvent({json.dumps(PATCHED_EVENT)}, "
                       f"{{detail: {detail}}}))"]
        if self.after:
            expressions.append(self.after)
        for expression in expressions:
            try:
                self.session.evaluate(f"(() => {{ {expression}; return true; }})()")
            except cdp.JSException as error:
                self._say(None, f"  after-patch code threw: {error}")

    def step(self) -> None:
        """One poll: read events, then push any file whose save has settled.

        A save is pushed once its mtime has held still for one poll, because
        editors that truncate and rewrite would otherwise be caught half way.
        """
        self.session.pump(0.25)
        self._drain()
        for watched in self.files:
            mtime = self._mtime(watched.path)
            if mtime is None or mtime == watched.seen:
                watched.pending = None
                continue
            if watched.pending != mtime:
                watched.pending = mtime
                continue
            watched.seen, watched.pending = mtime, None
            if not watched.script_id:
                self._reconcile(watched)
                continue
            text = self._read(watched.path)
            if text is not None and text != watched.live:
                self.push(watched, text)
            elif text is not None and watched.rejected:
                # Undoing a broken edit patches nothing, and silence there
                # reads like the watcher missed the save.
                self._say(watched, "back in step with what the game runs; nothing to patch")
                watched.rejected = False

    def run(self, once: bool = False) -> int:
        waiting_said = none_loaded_said = False
        while True:
            try:
                if not self.session:
                    self.attach()
                    waiting_said = none_loaded_said = False
                    self._say(None, f"attached; watching {len(self.files)} file(s). Ctrl-C to stop.")
                    if once:
                        self.close()
                        return 0 if all(w.script_id for w in self.files) else 1
                self.step()
            except KeyboardInterrupt:
                self.close()
                return 0
            except NoneLoaded as error:
                if once:
                    self._say(None, str(error))
                    return 1
                if not none_loaded_said:
                    self._say(None, f"{error}; waiting")
                    none_loaded_said = True
            except (OSError, cdp.CDPError) as error:
                if once:
                    raise cdp.CDPError(str(error)) from error
                if self.session:
                    self._say(None, f"lost the game ({error}); waiting for it to come back")
                    self.close()
                elif not waiting_said:
                    self._say(None, "waiting for the game (UIDebugger on, a save loaded)")
                    waiting_said = True
            else:
                continue
            try:
                time.sleep(2)
            except KeyboardInterrupt:
                return 0

    # -- helpers ----------------------------------------------------------
    @staticmethod
    def _mtime(path: Path) -> float | None:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    @staticmethod
    def _read(path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return None

    def _say(self, watched: _Watched | None, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        name = watched.path.name if watched else "civ7lab"
        self.out(f"{stamp}  {name}  {message}")
