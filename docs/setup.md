# Setup

## Doctor

```bash
civ7lab doctor
```

Run it first on a new machine and again after a game patch. Each problem it
checks for fails silently everywhere else:

- **Install and user folders**: where the game and its logs, saves and mods
  are.
- **UIDebugger**: off means `live` and `ui` have nothing to connect to.
- **CopyDatabasesToDisk**: off means `sql` has no database to work on.
- **Inspector**: whether a running game is answering, and on which port.
- **Gameplay dump**: a dump written at the main menu holds no age's data, so
  `sql` would find nothing to change.
- **Mods**: what is installed, and whether each link still points somewhere.
- **tree-sitter**: needed only by `jscheck`.

Each failure comes with the command that fixes it.

## Options

The game's developer switches live in `AppOptions.txt`, mostly commented out.
The game reads the file at launch and rewrites it on exit, so change it while
the game is closed.

```bash
civ7lab options                       # the switches civ7lab uses, and their state
civ7lab options --live                # turn them on
civ7lab options --play                # turn the costly ones off again
civ7lab options --set UILogLevel=3    # any switch by name
civ7lab options --live --dry-run      # show the change, write nothing
```

`--live` sets:

| switch | value | for |
|---|---|---|
| `UIDebugger` | 1 | the inspector `live` and `ui` attach to |
| `CopyDatabasesToDisk` | 1 | the database dumps `sql` reads |
| `EnableConsoleOutput` | 1 | logs mirrored to the game's stdout |
| `UILogLevel` | 2 | normal UI logging |

`UIFileWatcher` is meant to reload UI files, but did not reload a mod's
scripts when tried, so `--live` leaves it alone. Use
[`civ7lab ui watch`](ui.md) instead.

The file is backed up to `AppOptions.txt.civ7lab-YYYYMMDD.bak` before the
first write of each day.

`civ7lab run --inspector` turns the inspector on for one launch without
touching the file.

## Mods

The game loads mods from its `Mods` folder. A link from there to your working
copy means an edit reaches the game with no copy step. On Windows, where a
symlink needs admin rights or Developer Mode, civ7lab makes a directory
junction instead, which needs neither.

```bash
civ7lab mod install path/to/my-mod    # link your mod
civ7lab mod install                   # link the civ7lab probe
civ7lab mod list                      # what is there; flags broken links
civ7lab mod uninstall my-mod          # remove the link, not the source
```

`--copy` copies instead of linking. `--force` replaces whatever is already
there under that name.

The probe only reads the game and prints; it changes no rules and does not
affect saves. `live` does not need it installed. `run --plan` does.

## Environment variables

| variable | default | use |
|---|---|---|
| `CIV7_INSTALL` | found through Steam's library list | the folder holding `Base/` |
| `CIV7_USER` | see below | the folder holding `Logs/`, `Mods/`, `Saves/` |
| `CIV7_CDP_PORT` | 9444 | the inspector port, if a game patch moves it |
| `CIV7_CDP_HOST` | 127.0.0.1 | the inspector host |

The user folder civ7lab looks for:

| system | folder |
|---|---|
| Linux | `~/My Games/Sid Meier's Civilization VII` |
| Windows | `%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VII` |
| Linux, Windows build under Proton | the same `AppData/Local` folder, inside the game's Proton prefix |

`civ7lab doctor` shows which one it found.
