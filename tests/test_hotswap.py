"""The live-patch loop, against a stub game.

What a patch does inside V8 was confirmed in a running game; what is tested
here is everything around it that would otherwise be debugged with the game
open: which loaded script a file is, whether an edit sits inside a function,
reading V8's verdict, and the loop's bookkeeping. That means pushing a changed
file, leaving an unchanged one alone, and keeping the game's previous version
when a patch is refused.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from civ7lab import hotswap

PANEL = """\
// a comment at the top
export const COLORS = {
  SCIENCE: "#3C9BE8",
  ARTS: "#B547C7",
};

export function render(data) {
  const el = document.createElement("div");
  el.textContent = `Total ${data.items.map((x) => { return x.n; }).join(", ")}`;
  if (data.big) {
    el.className = "big";
  }
  return el;
}

class Tip {
  update() {
    return "{ not a brace }";
  }
}

registerThing("panel", render);
"""


def flagged(old, new):
    return hotswap.load_time_changes(old, new)


# -- which script -------------------------------------------------------------

def test_resolve_matches_the_path_inside_the_mod():
    root = Path("/work/yieldmod")
    urls = {"fs://game/yield-mod/ui/panel.js": "7", "fs://game/core/ui/panel-x.js": "8"}
    url, problem = hotswap.resolve(urls, root / "ui/panel.js", root)
    assert url == "fs://game/yield-mod/ui/panel.js" and problem is None


def test_resolve_prefers_the_mods_own_folder_on_a_tie():
    root = Path("/work/yieldmod")
    urls = {"fs://game/yieldmod/ui/panel.js": "1", "fs://game/other/ui/panel.js": "2"}
    url, _ = hotswap.resolve(urls, root / "ui/panel.js", root)
    assert url == "fs://game/yieldmod/ui/panel.js"


def test_resolve_explains_an_unloaded_file():
    root = Path("/work/yieldmod")
    url, problem = hotswap.resolve({}, root / "ui/new.js", root)
    assert url is None and "restart" in problem


# -- inside a function or not -------------------------------------------------

def test_edit_inside_a_function_is_not_flagged():
    assert flagged(PANEL, PANEL.replace('"big"', '"huge"')) == []


def test_edit_inside_a_method_is_not_flagged():
    assert flagged(PANEL, PANEL.replace("{ not a brace }", "{ still not }")) == []


def test_edit_inside_an_arrow_in_a_template_is_not_flagged():
    assert flagged(PANEL, PANEL.replace("return x.n;", "return x.n * 2;")) == []


def test_edit_to_a_top_level_table_is_flagged():
    labels = flagged(PANEL, PANEL.replace("#3C9BE8", "#000000"))
    assert labels == ["line 3"], labels


def test_edit_to_a_top_level_call_is_flagged():
    labels = flagged(PANEL, PANEL.replace('registerThing("panel"', 'registerThing("tip"'))
    assert labels == ["line 22"], labels


def test_the_body_of_an_immediately_invoked_function_is_load_time():
    source = "(function register() {\n  const table = { a: 1 };\n  function later() {\n    return 2;\n  }\n})();\n"
    assert flagged(source, source.replace("a: 1", "a: 9")) == ["line 2"]
    assert flagged(source, source.replace("return 2", "return 3")) == []


def test_comment_only_edit_at_top_level_is_not_flagged():
    assert flagged(PANEL, PANEL.replace("a comment at the top", "a different comment")) == []


def test_removed_top_level_line_is_flagged():
    labels = flagged(PANEL, PANEL.replace('  ARTS: "#B547C7",\n', ""))
    assert labels == ["removed line 4"], labels


def test_scan_keeps_one_entry_per_line_across_escaped_newlines():
    source = 'const s = "a\\\nb";\nfunction f() {\n  return 1;\n}\n'
    assert len(hotswap.scan(source)) == len(source.split("\n"))


# -- the game's verdict -------------------------------------------------------

def test_compile_error_from_v8_9_is_reported_with_its_line():
    accepted, message = hotswap.interpret({"exceptionDetails": {
        "text": "Uncaught SyntaxError: Unexpected token '}'", "lineNumber": 41,
        "columnNumber": 2}})
    assert not accepted and "line 42:3" in message and "SyntaxError" in message


def test_newer_status_field_is_read_too():
    accepted, message = hotswap.interpret({"status": "BlockedByTopLevelEsModuleChange"})
    assert not accepted and "top level" in message
    assert hotswap.interpret({"status": "Ok"})[0]
    assert hotswap.interpret({"callFrames": [], "stackChanged": False})[0]


# -- the loop -----------------------------------------------------------------

class StubSession:
    """Just enough of cdp.Session: a script table, and a record of calls."""

    def __init__(self, scripts, refuse=False):
        self.scripts = dict(scripts)          # url -> source
        self.ids = {url: str(n) for n, url in enumerate(self.scripts, 1)}
        self.events = []
        self.patches = []
        self.evaluated = []
        self.refuse = refuse
        self.closed = False

    def send(self, method, params=None):
        params = params or {}
        if method == "Debugger.enable":
            self.events += [{"method": "Debugger.scriptParsed",
                             "params": {"url": url, "scriptId": sid}}
                            for url, sid in self.ids.items()]
            return {}
        if method == "Debugger.getScriptSource":
            url = next(u for u, sid in self.ids.items() if sid == params["scriptId"])
            return {"scriptSource": self.scripts[url]}
        if method == "Debugger.setScriptSource":
            self.patches.append(params["scriptSource"])
            if self.refuse:
                return {"exceptionDetails": {"text": "SyntaxError", "lineNumber": 0,
                                             "columnNumber": 0}}
            url = next(u for u, sid in self.ids.items() if sid == params["scriptId"])
            self.scripts[url] = params["scriptSource"]
            return {"callFrames": [], "stackChanged": False}
        return {}

    def pump(self, seconds):
        pass

    def evaluate(self, expression):
        self.evaluated.append(expression)
        return True

    def close(self):
        self.closed = True


def make_mod(source):
    folder = Path(tempfile.mkdtemp()) / "yieldmod"
    (folder / "ui").mkdir(parents=True)
    (folder / "yieldmod.modinfo").write_text("<Mod/>")
    path = folder / "ui" / "panel.js"
    path.write_text(source)
    return folder, path


def make_watcher(path, session, lines, **kwargs):
    watcher = hotswap.Watcher([path], connect=lambda: session, out=lines.append, **kwargs)
    watcher.attach()
    return watcher


def touch_and_settle(watcher, path, text):
    path.write_text(text)
    later = time.time() + 5
    os.utime(path, (later, later))
    watcher.step()       # sees the mtime move
    watcher.step()       # sees it hold still, and pushes


def test_attach_leaves_an_identical_script_alone():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL})
    lines = []
    make_watcher(path, session, lines)
    assert session.patches == []
    assert any("in step" in line for line in lines), lines


def test_attach_pushes_a_file_newer_than_the_game():
    _, path = make_mod(PANEL.replace('"big"', '"huge"'))
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL})
    lines = []
    make_watcher(path, session, lines)
    assert len(session.patches) == 1 and '"huge"' in session.patches[0]


def test_a_save_is_patched_and_announced_to_the_game():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL})
    lines = []
    watcher = make_watcher(path, session, lines, after="redraw()")
    touch_and_settle(watcher, path, PANEL.replace('"big"', '"huge"'))
    assert len(session.patches) == 1
    assert any(hotswap.PATCHED_EVENT in e for e in session.evaluated)
    assert any("redraw()" in e for e in session.evaluated)
    assert not any("warning" in line for line in lines), lines


def test_a_top_level_edit_is_patched_with_a_warning():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL})
    lines = []
    watcher = make_watcher(path, session, lines)
    touch_and_settle(watcher, path, PANEL.replace("#3C9BE8", "#000000"))
    assert len(session.patches) == 1
    assert any("(line 3)" in line for line in lines), lines


def test_a_refused_patch_keeps_the_previous_version_as_the_baseline():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL}, refuse=True)
    lines = []
    watcher = make_watcher(path, session, lines)
    touch_and_settle(watcher, path, PANEL + "\n}")
    assert any("REJECTED" in line for line in lines), lines
    assert watcher.files[0].live == PANEL
    assert session.evaluated == []


def test_undoing_a_broken_save_says_so():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL}, refuse=True)
    lines = []
    watcher = make_watcher(path, session, lines)
    touch_and_settle(watcher, path, PANEL + "\n}")
    touch_and_settle(watcher, path, PANEL)
    assert any("back in step" in line for line in lines), lines
    assert len(session.patches) == 1


def test_load_time_warning_lasts_until_the_edit_is_undone():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL})
    lines = []
    watcher = make_watcher(path, session, lines)
    touch_and_settle(watcher, path, PANEL.replace("#3C9BE8", "#000000"))
    # an unrelated edit inside a function: the table still differs, so it still warns
    touch_and_settle(watcher, path, PANEL.replace("#3C9BE8", "#000000").replace('"big"', '"huge"'))
    assert sum("(line 3)" in line for line in lines) == 2, lines
    touch_and_settle(watcher, path, PANEL)
    assert any("matches what the game loaded again" in line for line in lines), lines
    assert sum("warning" in line for line in lines) == 2, lines


def test_an_unloaded_file_is_explained_once():
    folder, path = make_mod(PANEL)
    extra = folder / "ui" / "new.js"
    extra.write_text("export const x = 1;\n")
    session = StubSession({"fs://game/yieldmod/ui/panel.js": PANEL})
    lines = []
    watcher = hotswap.Watcher([path, extra], connect=lambda: session, out=lines.append)
    watcher.attach()
    watcher.step()
    watcher.step()
    assert sum("not loaded" in line for line in lines) == 1, lines


def test_a_ui_holding_none_of_the_files_is_not_taken_for_the_game():
    # The main menu, a load screen, or the game on its way out: the inspector
    # answers, but none of the mod's scripts are there.
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/core/ui/shell.js": "x"})
    lines = []
    watcher = hotswap.Watcher([path], connect=lambda: session, out=lines.append)
    try:
        watcher.attach()
        raise AssertionError("attach should have refused")
    except hotswap.NoneLoaded:
        pass
    assert session.closed and watcher.session is None
    assert not any("not loaded" in line or "restart" in line for line in lines), lines


def test_push_to_a_ui_holding_none_of_the_files_fails_plainly():
    _, path = make_mod(PANEL)
    session = StubSession({"fs://game/core/ui/shell.js": "x"})
    lines = []
    watcher = hotswap.Watcher([path], connect=lambda: session, out=lines.append)
    assert watcher.run(once=True) == 1
    assert len(lines) == 1 and "none of the watched files" in lines[0], lines


if __name__ == "__main__":
    failures = 0
    for name, function in sorted(globals().items()):
        if name.startswith("test_") and callable(function):
            try:
                function()
                print(f"ok   {name}")
            except Exception as error:
                failures += 1
                print(f"FAIL {name}: {type(error).__name__}: {error}")
    raise SystemExit(1 if failures else 0)
