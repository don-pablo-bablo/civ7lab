"""doctor, options and mod: getting a machine ready."""

from __future__ import annotations

from .. import appoptions, doctor, mod
from ._common import actions, command, print_json


def cmd_doctor(args) -> int:
    if args.json:
        print_json([finding.__dict__ for finding in doctor.check()])
        return 0
    print(doctor.report())
    return 0


def cmd_options(args) -> int:
    if args.live or args.play:
        preset = appoptions.LIVE_PRESET if args.live else appoptions.PLAY_PRESET
        lines, changed = appoptions.apply_preset(preset, dry_run=args.dry_run)
        for line in lines:
            print(("would set " if args.dry_run else "") + line)
        if not changed:
            print("\nnothing to change; the file was not written")
        elif not args.dry_run:
            print("\nAppOptions is read at launch, so restart the game for these to take effect.")
        return 0
    if args.set:
        options = appoptions.load()
        for pair in args.set:
            name, _, value = pair.partition("=")
            print(options.set(name, value))
        if not options.changed:
            print("nothing to change; the file was not written")
        elif not args.dry_run:
            backup = options.save()
            print(f"saved (backup: {backup})")
            print("Restart the game: AppOptions is read at launch.")
        return 0
    options = appoptions.load()
    for name in sorted(
        {
            *appoptions.LIVE_PRESET,
            *appoptions.PLAY_PRESET,
            "EnableTuner",
            "UILogLevel",
            "ModdingLogLevel",
        }
    ):
        option = options.get(name)
        state = (
            "unset"
            if not option
            else (option.value if option.enabled else f"{option.value} (commented out)")
        )
        print(f"{name:24} {state}")
    return 0


def cmd_mod(args) -> int:
    if args.action == "list":
        rows = mod.installed()
        if not rows:
            print("no mods installed")
            return 0
        for row in rows:
            target = f" -> {row.target}" if row.target else ""
            state = "" if row.valid else "   BROKEN"
            print(f"{row.name:28} {row.kind}{target}{state}")
        return 0
    if args.action == "install":
        print(mod.install(args.path, link=not args.copy, force=args.force))
        return 0
    print(mod.uninstall(args.name or "civ7lab-probe"))
    return 0


def register(sub) -> None:
    parser = command(
        sub,
        "doctor",
        doc="setup.md",
        examples="""
examples:
  civ7lab doctor           every check, with a fix for each failure
  civ7lab doctor --json""",
    )
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(func=cmd_doctor)

    parser = command(
        sub,
        "options",
        doc="setup.md",
        examples="""
The switches live in AppOptions.txt and are read at launch, so restart the
game after a change. The file is backed up once a day before it is written.

examples:
  civ7lab options                      show the switches civ7lab cares about
  civ7lab options --live               inspector and database dumps on
  civ7lab options --play               inspector off again
  civ7lab options --set UILogLevel=3   any switch by name""",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="turn on the inspector, database dumps and console output",
    )
    parser.add_argument("--play", action="store_true", help="turn them off again")
    parser.add_argument("--set", nargs="+", metavar="NAME=VALUE", help="set any switch by name")
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would change without writing"
    )
    parser.set_defaults(func=cmd_options)

    parser = command(
        sub,
        "mod",
        doc="setup.md",
        examples="""
examples:
  civ7lab mod list                      what is in Mods, and which links are broken
  civ7lab mod install                   link the civ7lab probe
  civ7lab mod install path/to/my-mod    link your own mod, so edits need no copy
  civ7lab mod uninstall my-mod          remove the link; the source is untouched""",
    )
    parser.set_defaults(func=cmd_mod)
    act = actions(parser)
    act.add_parser("list", help="list the installed mods and where each links to")
    install = act.add_parser("install", help="symlink or copy a mod into Mods")
    install.add_argument("path", nargs="?", help="mod directory (default: the civ7lab probe)")
    install.add_argument("--copy", action="store_true", help="copy instead of symlinking")
    install.add_argument(
        "--force", action="store_true", help="replace whatever is there under the same name"
    )
    uninstall = act.add_parser("uninstall", help="remove a mod from Mods")
    uninstall.add_argument("name", nargs="?", help="folder name in Mods (default: civ7lab-probe)")
