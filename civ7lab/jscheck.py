"""Static checks for a mod's UI scripts.

There is no JavaScript engine on an authoring machine by default, so these
files cannot be run here. They can be parsed, and they can be checked against
the modinfo that serves them, which catches the mistakes that otherwise only
appear as a missing line in UI.log after a restart:

* a stray bracket or a truncated edit, found by actually parsing the file;
* a file that exists but no ActionGroup lists, so the game never serves it;
* an `import` of a sibling script that the modinfo does not list, which takes
  the importing script down with it;
* `console.log` used for output, which never reaches UI.log. Only
  `console.error` does, so the script looks silent when it is working;
* a missing build stamp, which is what lets a reader tell whether the build
  that ran is the build being tested.

Parsing needs tree-sitter (`pip install tree_sitter tree_sitter_javascript`).
Without it the structural checks still run and the parse is reported as
skipped, because half a check is worth more than an import error.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import modinfo


@dataclass
class ScriptReport:
    path: Path
    parsed: bool = False
    syntax_errors: list[tuple[int, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    build_stamp: str | None = None

    @property
    def ok(self) -> bool:
        return not self.syntax_errors


def _parser():
    try:
        import tree_sitter_javascript as grammar
        from tree_sitter import Language, Parser
    except ImportError:
        return None
    return Parser(Language(grammar.language()))


def _collect_errors(node, out):
    if node.type == "ERROR" or node.is_missing:
        out.append((node.start_point[0] + 1,
                    "missing" if node.is_missing else "unparsable",
                    node.text.decode("utf8", "replace")[:60]))
        return  # one report per broken region, not one per child
    for child in node.children:
        _collect_errors(child, out)


_IMPORT = re.compile(r"""^\s*import\s[^;]*?['"]([^'"]+)['"]""", re.M)
# A stamp is found either as the printed marker or, more usefully, as the
# constant the script prints it from. That constant is what an editor forgets
# to bump, and what a reader compares against UI.log.
_BUILD = re.compile(r"""(?:const|var|let)\s+\w*BUILD\w*\s*=\s*["']([^"']+)["']""")


def check(mod_path: str | Path, age: str | None = None) -> list[ScriptReport]:
    info = modinfo.load(mod_path)
    listed = [path for path in info.ui_scripts(None)]
    listed_names = {path.name for path in listed}
    parser = _parser()
    reports: list[ScriptReport] = []

    for path in listed:
        report = ScriptReport(path=path)
        if not path.is_file():
            report.warnings.append("listed in the modinfo but not on disk")
            reports.append(report)
            continue
        source = path.read_text(errors="replace")

        if parser is not None:
            tree = parser.parse(source.encode())
            found: list[tuple[int, str, str]] = []
            _collect_errors(tree.root_node, found)
            report.parsed = True
            report.syntax_errors = found

        for target in _IMPORT.findall(source):
            # Only the mod's own files are ours to serve. A relative import
            # that climbs out of the mod directory is reaching for one of the
            # game's shipped modules, which is normal and correct.
            resolved = (path.parent / target).resolve()
            inside = str(resolved).startswith(str(Path(info.root).resolve()))
            if inside and resolved.name.endswith(".js") and resolved.name not in listed_names:
                report.warnings.append(
                    f"imports {target}, which the modinfo does not serve: "
                    "an unresolved import takes this whole script down")

        if re.search(r"^\s*console\.log\(", source, re.M):
            report.warnings.append(
                "uses console.log, which does not reach UI.log; console.error does")

        stamp = _BUILD.search(source)
        if stamp:
            report.build_stamp = stamp.group(1).strip()
        elif "civ7lab:build" in source or "console.error" in source:
            report.warnings.append(
                "no build stamp constant, so UI.log cannot say which build ran")
        reports.append(report)

    # A script on disk that nothing lists is inert, and looks exactly like one
    # that is loaded but broken.
    ui_dirs = {path.parent for path in listed} or {Path(info.root) / "ui"}
    for directory in ui_dirs:
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.js")):
            if path.name not in listed_names:
                report = ScriptReport(path=path)
                report.warnings.append("on disk but no ActionGroup lists it, so it never loads")
                if parser is not None:
                    found: list[tuple[int, str, str]] = []
                    _collect_errors(parser.parse(path.read_bytes()).root_node, found)
                    report.parsed, report.syntax_errors = True, found
                reports.append(report)
    return reports
