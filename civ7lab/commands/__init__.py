"""The command line. One file per area, each with its parsers and handlers:

  machine.py    doctor, options, mod
  offline.py    sql, modinfo, jscheck, text, dbdiff
  live.py       live, check, diff
  ui.py         ui
  run.py        run, logs
  mock.py       mock
  workshop.py   workshop

Anything that produces data takes --json, so a result can go into a diff or a
spec without being retyped.
"""

from __future__ import annotations

import argparse
import sys

from .. import cdp
from .. import workshop as workshop_api
from . import live, machine, mock, offline, run, ui, workshop
from ._common import GROUPS, overview

AREAS = [machine, offline, live, ui, run, mock, workshop]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="civ7lab",
        usage="civ7lab COMMAND [ACTION] [options]",
        description=overview(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    for area in AREAS:
        area.register(sub)
    listed = {name for _, commands in GROUPS for name, _ in commands}
    assert listed == set(sub.choices), "GROUPS and the registered commands differ"
    return parser


def main(argv=None) -> int:
    # City and leader names are not all ASCII. Windows would otherwise write
    # its own code page into a pipe or file, and fail on characters like ō.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        print(overview())
        return 0
    try:
        return args.func(args)
    except (cdp.CDPError, workshop_api.WorkshopError, FileNotFoundError) as error:
        print(f"civ7lab: {error}", file=sys.stderr)
        return 2
