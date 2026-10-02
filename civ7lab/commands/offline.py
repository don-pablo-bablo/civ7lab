"""sql, modinfo and jscheck: checks that need no running game."""

from __future__ import annotations

import sqlite3

from .. import dbdiff, jscheck, modinfo, sqlcheck, textcheck
from ._common import command, print_json


def print_query(query: sqlcheck.Query) -> None:
    """Rows as aligned columns, each cut to 40 characters."""
    cells = [[str(value)[:40] for value in row] for row in query.rows]
    widths = [
        max([len(name)] + [len(row[i]) for row in cells]) for i, name in enumerate(query.columns)
    ]
    for row in [query.columns, *cells]:
        print(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        )
    print(f"({len(query.rows)} row(s))")


def query_json(query: sqlcheck.Query) -> list[dict]:
    return [dict(zip(query.columns, row, strict=True)) for row in query.rows]


def cmd_sql(args) -> int:
    if not args.mod:
        if not args.query:
            print("give a mod folder, or --query to query the game's own database")
            return 1
        try:
            answer = sqlcheck.query_dump(args.query, db=args.db)
        except sqlite3.Error as error:
            print(f"civ7lab: {error}")
            return 1
        if args.json:
            print_json(query_json(answer))
        else:
            print_query(answer)
        return 0
    try:
        result = sqlcheck.run(
            args.mod,
            age=args.age,
            db=args.db,
            prefix=args.prefix,
            diff_limit=args.rows,
            query=args.query,
        )
    except sqlite3.Error as error:
        print(f"civ7lab: {error}")
        return 1
    if args.json:
        print_json(
            {
                "summary": result.summary(),
                "files": [
                    {
                        "file": str(f.path),
                        "group": f.group,
                        "ok": f.ok,
                        "error": f.error,
                        "notes": f.notes,
                    }
                    for f in result.files
                ],
                "warnings": result.warnings,
                "query": query_json(result.query) if result.query else None,
                "diffs": [
                    {
                        "table": d.table,
                        "added": d.added_count,
                        "removed": d.removed_count,
                        "sample_added": d.added,
                        "sample_removed": d.removed,
                    }
                    for d in result.diffs
                ],
            }
        )
        return 0 if result.ok else 1
    print(result.summary())
    if result.cleaned:
        print(
            f"stripped {result.cleaned} pre-existing row(s) matching {args.prefix}* "
            "from the baseline, so this measures what the files do now"
        )
    for file_result in result.files:
        mark = "ok  " if file_result.ok else "FAIL"
        print(
            f"  {mark} {file_result.path.name:32} {file_result.group}"
            + (f"  {file_result.statements} statement(s)" if file_result.statements else "")
        )
        if file_result.error:
            print(f"       {file_result.error}")
        for note in file_result.notes:
            print(f"       note: {note}")
    for warning in result.warnings:
        print(f"  warn: {warning}")
    for table_diff in result.diffs:
        print(f"  {table_diff.table}: +{table_diff.added_count} -{table_diff.removed_count}")
        if args.rows:
            for row in table_diff.added[: args.rows]:
                print(f"       + {row}")
            for row in table_diff.removed[: args.rows]:
                print(f"       - {row}")
    if result.query:
        print()
        print_query(result.query)
    return 0 if result.ok else 1


def cmd_jscheck(args) -> int:
    reports = jscheck.check(args.mod)
    failures = 0
    for report in reports:
        if not report.ok:
            failures += 1
        mark = "ok  " if report.ok else "FAIL"
        stamp = f"[{report.build_stamp}]" if report.build_stamp else ""
        print(f"{mark} {report.path.name} {stamp}")
        for line, kind, text in report.syntax_errors:
            print(f"      line {line}: {kind}: {text!r}")
        for warning in report.warnings:
            print(f"      - {warning}")
    if not any(report.parsed for report in reports):
        print(
            f"\nsyntax was not checked: the parser is missing. Install it {jscheck.JSCHECK_INSTALL}"
        )
    return 1 if failures else 0


def cmd_modinfo(args) -> int:
    info = modinfo.load(args.mod)
    print(f"{info.id}  {info.name}  v{info.version}")
    for age in modinfo.AGES if not args.age else [args.age]:
        items = info.items("UpdateDatabase", age)
        print(f"\n{age}: {len(items)} database item(s), in apply order")
        for group, path in items:
            mark = " " if path.is_file() else "?"
            print(f"  {mark} [{group.load_order:>5}] {group.id:28} {path.name}")
    scripts = info.ui_scripts()
    if scripts:
        print(f"\nUI scripts ({len(scripts)}):")
        for path in scripts:
            print(f"    {path.name}" + ("" if path.is_file() else "   MISSING"))
    disabled = modinfo.disabled_items(args.mod)
    if disabled:
        print("\ncommented out in the modinfo, so not loaded:")
        for item in disabled:
            print(f"    {item}")
    ambiguous = info.ambiguous_criteria()
    if ambiguous:
        print(
            f"\nambiguous age criteria: {', '.join(ambiguous)}"
            f" (groups: {', '.join(info.groups_using(ambiguous))})"
            "\n  AgeAtOrBefore/AgeAtOrAfter read one way here and could mean the other;"
            "\n  spelling them as explicit AgeInUse rows removes the doubt."
        )
    return 0


def cmd_text(args) -> int:
    report = textcheck.check(args.mod, db=args.db, prefix=args.prefix)
    if args.json:
        print_json(
            {
                "undefined": {k: report.used[k] for k in report.undefined},
                "unused": report.unused,
                "checked_game_text": report.game is not None,
            }
        )
        return 0 if report.ok else 1
    against = (
        f"the game's {len(report.game)}"
        if report.game is not None
        else "no game text: CopyDatabasesToDisk writes it"
    )
    print(
        f"{len(report.used)} key(s) used, {len(report.defined)} defined by the mod, "
        f"checked against {against}"
    )
    if report.undefined:
        print(f"\nused but defined nowhere ({len(report.undefined)}):")
        for key in report.undefined:
            print(f"  {key:40} {', '.join(report.used[key])}")
    if report.unused:
        print(f"\ndefined by the mod but not used in its files ({len(report.unused)}):")
        for key in report.unused:
            print(f"  {key}")
    return 0 if report.ok else 1


def cmd_dbdiff(args) -> int:
    changes = dbdiff.compare(args.before, args.after)
    if args.table:
        changes = [c for c in changes if c.table == args.table]
    if args.json:
        print_json([c.__dict__ for c in changes])
        return 0
    if not changes:
        print("no differences")
        return 0
    for change in changes:
        parts = [
            f"{n} {what}"
            for n, what in (
                (change.changed, "changed"),
                (change.added, "added"),
                (change.removed, "removed"),
            )
            if n
        ]
        if change.note:
            parts.insert(0, change.note)
        if change.columns_added:
            parts.append("new columns " + ", ".join(change.columns_added))
        if change.columns_removed:
            parts.append("columns removed " + ", ".join(change.columns_removed))
        print(f"{change.table}: " + ", ".join(parts))
        for line in change.lines[: args.rows]:
            print(f"  {line}")
        if len(change.lines) > args.rows:
            print(f"  ... and {len(change.lines) - args.rows} more")
    return 0


def register(sub) -> None:
    parser = command(
        sub,
        "sql",
        doc="offline.md",
        examples="""
Copies the game's Debug/gameplay-copy.sqlite, turns foreign keys on, applies
every database file the modinfo lists for the age, and reports the rows each
table gained or lost. The dump must be taken with a save loaded: see doctor.

examples:
  civ7lab sql path/to/mod --age AGE_ANTIQUITY
  civ7lab sql path/to/mod --age AGE_ANTIQUITY --prefix MYMOD --rows 5
  civ7lab sql path/to/mod --query "SELECT * FROM Types WHERE Type LIKE 'MYMOD%'"
  civ7lab sql --query "SELECT UnitType, BaseMoves FROM Units ORDER BY BaseMoves DESC"
  civ7lab sql path/to/mod --db saved-dump.sqlite --json""",
    )
    parser.add_argument(
        "mod", nargs="?", help="path to the mod directory or its .modinfo; leave out to query"
    )
    parser.add_argument("--age", choices=modinfo.AGES, help="which age's rules to apply")
    parser.add_argument(
        "--query", metavar="SQL", help="run this SQL after the mod is applied, and print the rows"
    )
    parser.add_argument("--db", help="database to apply to (default: the game's own dump)")
    parser.add_argument(
        "--prefix",
        help="first delete tags and types starting with this, "
        "so a dump taken with the mod loaded does not "
        "already hold its rows",
    )
    parser.add_argument("--rows", type=int, default=0, help="show up to N changed rows per table")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=cmd_sql)

    parser = command(
        sub,
        "modinfo",
        doc="offline.md",
        examples="""
Also lists items commented out in the modinfo, and age criteria whose
direction is ambiguous.

examples:
  civ7lab modinfo path/to/mod
  civ7lab modinfo path/to/mod --age AGE_EXPLORATION""",
    )
    parser.add_argument("mod", help="path to the mod directory or its .modinfo")
    parser.add_argument("--age", choices=modinfo.AGES)
    parser.set_defaults(func=cmd_modinfo)

    parser = command(
        sub,
        "jscheck",
        doc="offline.md",
        examples="""
Reports syntax errors, scripts the modinfo does not list, imports of scripts
the modinfo does not serve, console.log calls, and missing build stamps.
Finding syntax errors needs the tree-sitter parser, the jscheck extra.

example:
  civ7lab jscheck path/to/mod""",
    )
    parser.add_argument("mod", help="path to the mod directory or its .modinfo")
    parser.set_defaults(func=cmd_jscheck)

    parser = command(
        sub,
        "text",
        doc="offline.md#text",
        examples="""
A key used but defined nowhere shows in game as the raw key. The game's own
keys come from Debug/localization-copy.sqlite. A dump taken with the mod
loaded holds the mod's keys too: --prefix leaves out keys starting with it.

examples:
  civ7lab text path/to/mod
  civ7lab text path/to/mod --prefix LOC_MYMOD""",
    )
    parser.add_argument("mod", help="path to the mod directory or its .modinfo")
    parser.add_argument("--db", help="the game's text database (default: its own dump)")
    parser.add_argument("--prefix", help="ignore the game's keys starting with this")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=cmd_text)

    parser = command(
        sub,
        "dbdiff",
        doc="offline.md#dbdiff",
        examples="""
Rows are paired by the table's primary key, so a changed row is shown as one
change naming its columns. Copy Debug/gameplay-copy.sqlite before a patch to
have something to compare against.

examples:
  civ7lab dbdiff before-patch.sqlite after-patch.sqlite
  civ7lab dbdiff old.sqlite new.sqlite --table Units --rows 50
  civ7lab dbdiff old.sqlite new.sqlite --json""",
    )
    parser.add_argument("before", help="the older database")
    parser.add_argument("after", help="the newer database")
    parser.add_argument("--table", help="only this table")
    parser.add_argument("--rows", type=int, default=5, help="rows to show per table")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=cmd_dbdiff)
