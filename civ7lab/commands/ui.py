"""ui: patching a mod's scripts into the running game."""

from __future__ import annotations

from pathlib import Path

from .. import hotswap
from ._common import command


def cmd_ui(args) -> int:
    files: list[Path] = []
    for given in args.paths:
        path = Path(given)
        if path.is_dir():
            files.extend(sorted(path.rglob("*.js")))
        elif path.is_file():
            files.append(path)
        else:
            raise FileNotFoundError(f"no such file or directory: {given}")
    if not files:
        print("no .js files to watch")
        return 1
    watcher = hotswap.Watcher(
        files, root=args.root, after=args.after, port=args.port, target=args.target
    )
    return watcher.run(once=args.action == "push")


def register(sub) -> None:
    parser = command(
        sub,
        "ui",
        doc="ui.md",
        examples="""
Save a file and the game runs the new version about a second later. Edits
inside functions take effect on the next call. Code that ran once at load,
such as a constant or a registration call, still needs a restart, and the
watcher says which lines.

examples:
  civ7lab ui watch path/to/mod/ui                  every script, until Ctrl-C
  civ7lab ui watch path/to/mod/ui/panel.js
  civ7lab ui push path/to/mod/ui                   once, then exit
  civ7lab ui watch path/to/mod/ui --after 'MyPanel.redraw()'""",
    )
    parser.add_argument(
        "action",
        choices=["watch", "push"],
        help="watch: patch on every save until Ctrl-C; push: bring the game "
        "level with the files once and exit",
    )
    parser.add_argument("paths", nargs="+", help="files, or folders of .js files")
    parser.add_argument("--root", help="the mod folder, when no .modinfo sits above the files")
    parser.add_argument(
        "--after",
        help="JavaScript to run in the game after each patch, such as a call that redraws a panel",
    )
    parser.add_argument("--port", type=int)
    parser.add_argument("--target", help="pick the UI context by substring of its url")
    parser.set_defaults(func=cmd_ui)
