"""What every command file shares: the command list and the parser helper."""

from __future__ import annotations

import argparse
import json

# The overview `civ7lab` prints with no arguments, in the order a new user
# needs it. Every command must appear here exactly once.
GROUPS = [
    (
        "Set up",
        [
            ("doctor", "check what works on this machine, and why not"),
            ("options", "turn the game's developer switches on or off"),
            ("mod", "link a mod into the game's Mods folder, or list what is there"),
        ],
    ),
    (
        "Without the game",
        [
            ("sql", "apply a mod's SQL and XML to a copy of the game database"),
            ("modinfo", "list what a mod loads in each age, in load order"),
            ("jscheck", "parse a mod's UI scripts and check them against its modinfo"),
            ("text", "find LOC_ keys a mod uses that nothing defines"),
            ("dbdiff", "compare two game databases, such as before and after a patch"),
        ],
    ),
    (
        "With the game running",
        [
            ("live", "ask the running game a question, or run JavaScript in it"),
            ("ui", "reload a mod's UI scripts in the running game on every save"),
            ("check", "test a spec's expectations against the game or a snapshot"),
            ("diff", "compare two snapshots"),
        ],
    ),
    (
        "Launching and logs",
        [
            ("run", "start the game from the command line: load a save or autoplay"),
            ("logs", "copy, search and decode the game's logs"),
        ],
    ),
    (
        "Other",
        [
            ("mock", "draw a mod's panel in a browser from saved cases"),
            ("workshop", "set the tags or description of a Steam Workshop item"),
        ],
    ),
]

SUMMARIES = {name: summary for _, commands in GROUPS for name, summary in commands}


def overview() -> str:
    lines = ["A test bench for Civilization VII mods.", ""]
    for title, commands in GROUPS:
        lines.append(title)
        lines.extend(f"  {name:10} {summary}" for name, summary in commands)
        lines.append("")
    lines.append("`civ7lab COMMAND -h` gives examples. Full docs: docs/README.md")
    return "\n".join(lines)


def command(sub, name: str, examples: str = "", doc: str = "", **kwargs) -> argparse.ArgumentParser:
    """Add one command with its summary, examples and docs page."""
    epilog = examples.strip("\n")
    if doc:
        epilog += f"\n\nDocs: docs/{doc}"
    return sub.add_parser(
        name,
        description=SUMMARIES.get(name, ""),
        epilog=epilog or None,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        **kwargs,
    )


def actions(parser: argparse.ArgumentParser):
    """Subcommands of a command, such as `live eval`."""
    return parser.add_subparsers(dest="action", metavar="ACTION", required=True)


def print_json(value) -> None:
    print(json.dumps(value, indent=2, default=str, ensure_ascii=False))
