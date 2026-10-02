"""mock: drawing a mod's panel in a browser."""

from __future__ import annotations

from .. import mock
from ._common import actions, command


def cmd_mock(args) -> int:
    if args.action == "fixtures":
        latest = (
            [f.strip() for f in args.latest_by.split(",") if f.strip()] if args.latest_by else None
        )
        out, total, kept = mock.fixtures_from_records(
            kind=args.kind, log=args.log, out=args.out, latest=latest
        )
        dropped = f", {total - kept} older reading(s) of the same case dropped" if latest else ""
        print(f"wrote {out}: {kept} fixture(s) from {total} {args.kind} record(s){dropped}")
        return 0
    mock.serve(
        root=args.root,
        renderer=args.renderer,
        export=args.export,
        fixtures=args.fixtures,
        port=args.port,
        open_browser=args.open,
    )
    return 0


def register(sub) -> None:
    parser = command(
        sub,
        "mock",
        doc="mock.md",
        examples="""
Works for a panel whose drawing code is in its own file and calls no engine
API. The panel logs each case it draws as a record; `fixtures` turns those
into a file the browser page reads.

examples:
  civ7lab mock fixtures --kind my-panel --latest-by cityName,loc.x,loc.y
  civ7lab mock serve --root path/to/mod --renderer ui/panel-render.js --open""",
    )
    parser.set_defaults(func=cmd_mock)
    act = actions(parser)

    serve = act.add_parser("serve", help="serve the mock page and the mod's files")
    serve.add_argument("--root", default=".", help="the mod folder to serve")
    serve.add_argument("--renderer", default="", help="the drawing module, relative to --root")
    serve.add_argument(
        "--export", default="render", help="the function it exports, called once per fixture"
    )
    serve.add_argument(
        "--fixtures", default="fixtures.js", help="the fixtures file, relative to --root"
    )
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--open", action="store_true", help="open a browser")

    fixtures = act.add_parser("fixtures", help="write fixtures.js from records in UI.log")
    fixtures.add_argument("--kind", default="fixture", help="the record kind to collect")
    fixtures.add_argument("--log", help="a UI.log to read instead of the live one")
    fixtures.add_argument("--out", help="where to write (default: ./fixtures.js)")
    fixtures.add_argument(
        "--latest-by",
        metavar="FIELDS",
        help="comma-separated fields that identify a case, as dotted "
        "paths into the data; keeps the last record of each",
    )
