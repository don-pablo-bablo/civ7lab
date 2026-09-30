# civ7lab

A test bench for Civilization VII mods.

Checking a mod change usually means editing a file, restarting the game,
playing until the situation exists, then reading a number off a screenshot or
out of a four-megabyte log. That costs an evening per question, and the answer
cannot be reproduced afterwards. civ7lab answers most of those questions
without a restart, and many without the game.

It works with any mod. Point it at a mod folder and it reads that mod's modinfo
for what to apply and what to check.

## Five routes

Use the cheapest one that answers the question.

| route | what it does | cost |
|---|---|---|
| **offline** | apply a mod's SQL and XML to a copy of the game's database; parse its UI scripts | a second, no game |
| **live** | attach to a running game and ask a collector a question | a round trip, no restart |
| **ui** | patch a mod's UI scripts into the running game on every save | a second, no restart |
| **logs** | read the structured records the probe printed | free, survives the game exiting |
| **run** | launch the game unattended, play or load a save, harvest everything | minutes, nobody watching |

## Start here

```bash
python3 -m civ7lab doctor            # what works, what does not, and why
python3 -m civ7lab options --live    # turn on the inspector and database dumps
python3 -m civ7lab mod install       # link the probe mod into the game
```

Run `doctor` first on any machine and after any game patch. Every failure here
is silent from the outside, so it names them: the inspector is off, the
database dump was taken at the main menu and is empty, the mod is not linked,
the probe never loaded.

`civ7lab.sh` runs the tool from any folder without installing it.

## Offline: no game needed

```bash
python3 -m civ7lab sql  path/to/mod --age AGE_ANTIQUITY --prefix C69 --rows 5
python3 -m civ7lab jscheck path/to/mod
python3 -m civ7lab modinfo path/to/mod
```

`sql` copies the game's `Debug/gameplay-copy.sqlite`, turns foreign keys on,
and applies every database item the modinfo gives for that age, in the order
the game applies them. It then reports the changed rows per table, so
`TypeTags: +34` is a number a later run can be held against.

It catches three traps, each of which has cost a real playthrough:

- **Foreign keys**: `INSERT OR IGNORE` does not cover them. An insert against a
  row this age does not load fails here in a second, instead of in
  `Database.log` after a launch.
- **Dirty baseline**: a dump taken with the mod loaded already holds the mod's
  output. `--prefix` strips those rows and says how many.
- **Wrong age**: the dump holds one age's buildings. Asking about another age
  gets a warning.

`jscheck` parses every UI script and checks it against the modinfo. It reports
a file that no ActionGroup lists, since the game never loads it; a sibling
import the modinfo does not serve, which takes the importing script down;
`console.log`, which never reaches `UI.log`; and a missing build stamp, without
which nobody can tell which build ran.

## Live: ask a running game

```bash
python3 -m civ7lab live attach
python3 -m civ7lab live collect tile --args '{"x":20,"y":7}'
python3 -m civ7lab live snapshot --collect game "city:{\"all\":true}" --out before.json
python3 -m civ7lab live members --expression "Cities.get(cityID).Yields"
python3 -m civ7lab diff before.json after.json
```

The game's UI runs on Coherent cohtml, which embeds the Chrome DevTools
protocol. The `UIDebugger` switch in `AppOptions.txt` starts that server. With
it on, a question is one round trip with no restart, screenshot or log parsing.

The probe mod need not be installed for this. Its scripts import nothing, so
`live` pushes them into the running game and registers the collectors on the
spot. That works on a game already in progress, with any mods or none.

Collectors: `game`, `tile`, `tiles`, `cities`, `city`, `yieldtree`,
`greatworks`, `tags`, `def`. `members` lists what an engine object has on it.

## UI: change a panel while the game runs

```bash
python3 -m civ7lab ui watch path/to/mod/ui/panel.js     # or a whole ui/ folder
python3 -m civ7lab ui push  path/to/mod/ui              # once, then exit
```

Save the file and the game runs the new version about a second later. Each
save goes to the game's V8 engine as a live edit: the loaded module's functions
are replaced in place, and every module that imported them calls the new code
from then on. The mod needs no changes for this. The file on disk stays the
only copy; a restart reloads it.

A patch cannot run anything again. Constants, lookup tables, registration
calls and the body of a `(function () { ... })()` wrapper ran once when the
game loaded the file. The watcher still patches such edits, but warns by line
that they need a restart. Edits inside functions take effect on the next call.

A panel already on screen is not redrawn. A tooltip picks up the change the
next time it opens. A panel can redraw at once by listening for the
`civ7lab-patched` window event, or with `--after 'JS'`.

A file the game did not load at start cannot be patched. A new script needs a
modinfo entry and a restart, and the watcher says so.

Between games the watcher waits and reattaches when a save loads.

## Run: launch the game unattended

```bash
python3 -m civ7lab run --save MySave --inspector       # boot into a save
python3 -m civ7lab run --save latest --inspector       # the newest one in Saves/Single
python3 -m civ7lab run --turns 40 --seed 12345 --quit \
        --plan plans/age-turn.json                     # play, record, exit
```

Loading a save stops there, with no autoplay and no timeout unless `--turns`
or `--timeout` asks for them. A new game plays 10 turns and stops after 30
minutes by default. Autosaves cannot be loaded this way, because the game's
LoadGame test hard-codes `IsAutosave=false`.

This uses the game's own automation: a suite of scripts with parameters such
as `{ Test=PlayGame, Turns=40 }` or `{ Test=LoadGame, SaveName=X }`. Seeds make
two runs the same game, so a changed number points at the change instead of the
map.

A run leaves one folder with the suite, the command line, the logs from before
and after, the decoded records and a summary. **The game empties every log at
launch**, so the previous session's logs are copied before anything starts.

`--plan` installs a recording plan before launch: which collectors fire on
which turns. It must be in place before turn one, because nobody is there to
type it.

## Specs: write a measurement down

```bash
python3 -m civ7lab check specs/example-tile-yield.json
python3 -m civ7lab check specs/example-tile-yield.json --snapshot before.json
```

A spec names what to collect and what should be true of it, with a `why` on
each expectation. The next person then asks the same question the same way.
Specs run against a live game or a saved snapshot.

## Mock: draw a panel without the game

```bash
python3 -m civ7lab mock serve --root path/to/mod --renderer ui/panel.js --export render
```

If a panel's rendering code calls no engine API, it runs in a browser, and a
layout change costs a refresh instead of a restart. `civ7lab mock fixtures`
harvests the panels the game drew out of the log, so the cases are real tiles
rather than invented ones. `--latest-by cityName,loc.x,loc.y` keeps only the
last reading of each case; any dotted fields of the data work.

Icons show as coloured discs, because `blp:` is the engine's own protocol.
Check icon art in the game.

## Workshop: set an item's tags

```bash
python3 -m civ7lab workshop tags ITEM_ID                 # show them
python3 -m civ7lab workshop tags ITEM_ID UI --dry-run    # now and new
python3 -m civ7lab workshop tags ITEM_ID "Game Setup" "Gameplay Tweaks"
```

Under Proton, the SDK's Workshop Uploader will not tick its tag checkboxes,
and Steam's web page has no tag editor for this game. This command does what
the uploader does on upload, and nothing else: it replaces the tag list and
leaves the title, description, content and visibility as they are.

The list you give is the whole new list. Mod is always kept, since without it
the item leaves the Mod filter. Names outside the uploader's lists are refused;
case does not matter. A submit changes a public page, so dry-run first.

It needs Steam running and logged on as the item's creator. It loads the Steam
runtime's `libsteam_api.so` and runs as the SDK's app, 3688890, as the uploader
does, falling back to the game's, 1295660. Afterwards it reads the tags back
from Steam's public web API, which can lag a minute behind.

## Requirements

- Python 3.10 or newer. The DevTools client uses only the standard library.
- For `jscheck` only: `pip install tree_sitter tree_sitter_javascript`.
- The game, for every route except offline.

It runs on Linux against the Steam version of the game. The game paths assume
that install.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). It also lists what has been confirmed
in a running game and what has not.

## Licence

MIT. See [LICENSE](LICENSE).
