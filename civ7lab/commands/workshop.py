"""workshop: Steam Workshop items."""

from __future__ import annotations

import difflib
import sys
from pathlib import Path

from .. import workshop
from ._common import actions, command, print_json


def cmd_workshop(args) -> int:
    item = workshop.details(args.item)
    if item.consumer_app_id != workshop.CONSUMER_APP_ID:
        print(f"item {item.id} is for app {item.consumer_app_id}, not Civ VII")
        return 1
    if args.action == "description":
        return cmd_description(args, item)
    if args.action == "upload":
        return cmd_upload(args, item)
    if not args.tags:
        if args.json:
            print_json(item.__dict__)
            return 0
        print(f"{item.title} ({item.id})")
        print("  tags: " + (", ".join(item.tags) or "none"))
        return 0
    tags = workshop.resolve_tags(args.tags)
    dropped = [tag for tag in item.tags if tag not in tags]
    report = {
        "item": item.id,
        "title": item.title,
        "now": item.tags,
        "new": tags,
        "dropped": dropped,
    }
    if not args.json:
        print(f"{item.title} ({item.id})")
        print("  now: " + (", ".join(item.tags) or "none"))
        print("  new: " + ", ".join(tags))
        if dropped:
            print("  dropped: " + ", ".join(dropped))
    if args.dry_run:
        if args.json:
            print_json(report)
        else:
            print("dry run: nothing submitted")
        return 0
    submitted = workshop.submit(item, tags=tags)
    report["attempts"] = [{"app_id": a, "result": r} for a, r in submitted.attempts]
    if not args.json:
        for app_id, outcome in submitted.attempts:
            print(f"  submit as app {app_id}: {outcome}")
    if not submitted.ok:
        if args.json:
            print_json(report)
        return 1
    after = workshop.read_back(item.id, lambda now: sorted(now.tags) == sorted(tags))
    report["read_back"] = after.tags
    matched = sorted(after.tags) == sorted(tags)
    if args.json:
        print_json(report)
    else:
        print("  read back: " + (", ".join(after.tags) or "none"))
        if not matched:
            print(
                "  the web API does not show the new tags yet; it can lag. "
                f"Check again with: civ7lab workshop tags {item.id}"
            )
    return 0 if matched else 1


def cmd_description(args, item: workshop.Item) -> int:
    text = Path(args.file).read_text(encoding="utf-8").strip()
    print(f"{item.title} ({item.id})")
    if len(text) > workshop.DESCRIPTION_LIMIT:
        print(
            f"  {args.file} has {len(text)} characters; Steam takes at most "
            f"{workshop.DESCRIPTION_LIMIT}"
        )
        return 1
    if workshop.same_text(item.description, text):
        print(f"  the description already matches {args.file}")
        return 0
    changes = difflib.unified_diff(
        item.description.replace("\r\n", "\n").strip().splitlines(),
        text.splitlines(),
        "on Steam",
        args.file,
        lineterm="",
    )
    for line in changes:
        print(f"  {line}")
    if args.dry_run:
        print("dry run: nothing submitted")
        return 0
    submitted = workshop.submit(item, description=text)
    for app_id, outcome in submitted.attempts:
        print(f"  submit as app {app_id}: {outcome}")
    if not submitted.ok:
        return 1
    after = workshop.read_back(item.id, lambda now: workshop.same_text(now.description, text))
    if not workshop.same_text(after.description, text):
        print(
            "  the web API does not show the new description yet; it can lag. "
            f"Check again with: civ7lab workshop description {item.id} {args.file} --dry-run"
        )
        return 1
    print("  read back: matches")
    return 0


def cmd_upload(args, item: workshop.Item) -> int:
    print(f"{item.title} ({item.id})")
    try:
        mod = workshop.mod_folder(Path(args.folder))
    except workshop.WorkshopError as error:
        print(f"  {error}")
        return 1
    try:
        note = Path(args.note).read_text(encoding="utf-8").strip() if args.note else ""
    except (OSError, UnicodeDecodeError) as error:
        print(f"  cannot read the release notes in {args.note}: {error}")
        return 1
    if len(note) > workshop.DESCRIPTION_LIMIT:
        print(
            f"  {args.note} has {len(note)} characters; Steam takes at most "
            f"{workshop.DESCRIPTION_LIMIT}"
        )
        return 1
    print(f"  mod: {mod.id} {mod.version}")
    print(f"  folder: {mod.path}, {len(mod.files)} files, {mod.size / 1024:.0f} KB")
    for file in mod.files:
        print(f"    {file.relative_to(mod.path).as_posix()}")
    if note:
        print("  release notes:")
        for line in note.splitlines():
            print(f"    {line}")
    else:
        print("  release notes: none")
    if args.dry_run:
        print("dry run: nothing submitted")
        return 0
    shown = [-1]

    # Steam's count drops back to 0 once the files are sent, while it
    # commits the update, so only a rise is shown.
    def progress(done: int, total: int) -> None:
        percent = done * 100 // total if total else 0
        if percent > shown[0]:
            shown[0] = percent
            print(f"\r  uploading: {percent}%", end="", file=sys.stderr, flush=True)

    submitted = workshop.submit(item, content=mod.path, note=note or None, progress=progress)
    if shown[0] >= 0:
        print(file=sys.stderr)
    for app_id, outcome in submitted.attempts:
        print(f"  submit as app {app_id}: {outcome}")
    if not submitted.ok:
        return 1
    after = workshop.read_back(item.id, lambda now: now.updated > item.updated)
    if after.updated <= item.updated:
        print(
            "  the web API does not show the update yet; it can lag. Check the "
            "item's Change Notes page on Steam."
        )
        return 1
    print("  read back: updated")
    return 0


def register(sub) -> None:
    parser = command(
        sub,
        "workshop",
        doc="workshop.md",
        examples="""
Changes the tags, the description or the mod's files, and nothing else.
Needs Steam running and logged on as the item's creator. A submit changes a
public page, so dry-run first.

examples:
  civ7lab workshop tags 1234567890                          show the tags
  civ7lab workshop tags 1234567890 UI --dry-run             show now and new
  civ7lab workshop tags 1234567890 "Game Setup" "Gameplay Tweaks"
  civ7lab workshop description 1234567890 workshop/description.txt --dry-run
  civ7lab workshop upload 1234567890 mod/my-mod --note notes.txt --dry-run""",
    )
    parser.set_defaults(func=cmd_workshop)
    act = actions(parser)
    tags = act.add_parser("tags", help="show or replace an item's tags")
    tags.add_argument("item", help="the Workshop item ID")
    tags.add_argument(
        "tags",
        nargs="*",
        help="the full new tag list; Mod is always kept. Quote names with "
        "spaces, or separate with commas. None: show the current tags",
    )
    tags.add_argument(
        "--dry-run", action="store_true", help="show the current and new tags without submitting"
    )
    tags.add_argument("--json", action="store_true")

    description = act.add_parser(
        "description", help="replace an item's description with a file's text"
    )
    description.add_argument("item", help="the Workshop item ID")
    description.add_argument("file", help="the new description, in Steam's markup")
    description.add_argument(
        "--dry-run", action="store_true", help="show what would change without submitting"
    )

    upload = act.add_parser(
        "upload", help="upload a new version of an item's mod, with release notes"
    )
    upload.add_argument("item", help="the Workshop item ID")
    upload.add_argument("folder", help="the mod's folder, with its .modinfo at the top")
    upload.add_argument("--note", help="a file with the release notes, in Steam's markup")
    upload.add_argument(
        "--dry-run", action="store_true", help="show what would be uploaded without submitting"
    )
