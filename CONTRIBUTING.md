# Contributing

## How it works

A Python package drives the game from outside, and a small probe mod reads it
from inside.

| path | what it is |
|---|---|
| `civ7lab/` | the Python package, one module per route |
| `civ7lab/__main__.py` | the command line |
| `civ7lab/sqlcheck.py`, `modinfo.py` | the offline SQL harness and the modinfo reader |
| `civ7lab/jscheck.py` | the UI script checker |
| `civ7lab/cdp.py`, `live.py` | the DevTools client and the live session |
| `civ7lab/hotswap.py` | `ui watch` and `ui push` |
| `civ7lab/records.py`, `logs.py` | the log record protocol and log handling |
| `civ7lab/runner.py`, `appoptions.py` | unattended runs and the game's switches |
| `civ7lab/check.py`, `diff.py` | specs and snapshot diffs |
| `civ7lab/mock.py`, `mock/panel.html` | the browser mock and its fixtures |
| `civ7lab/workshop.py` | `workshop tags`, over Steam's flat API |
| `mod/civ7lab-probe/` | the probe mod: it only reads and prints |
| `.../ui/lab-core.js` | the collector registry and the log record writer |
| `.../ui/lab-collect.js` | the collectors |
| `.../ui/lab-hooks.js`, `lab-plan.js` | runs a recording plan during unattended runs |
| `specs/` | example expectations |
| `plans/` | example recording plans |
| `tests/` | offline tests, no game needed |
| `reference` | gitignored link to the game's resources folder |

Link the game's resources folder, the one that contains `Base`, as `reference`
in the repo root. It holds the shipped UI code, which is the list of engine
APIs that are safe to call.

## Tests

```bash
tests/run-all.sh                  # every test file, then doctor
python3 tests/test_records.py     # the log protocol, including truncation
python3 tests/test_cdp.py         # the DevTools client, against a fake inspector
python3 tests/test_hotswap.py     # the live-patch loop, against a stub game
```

Each test file runs on its own with no test runner. None of them launch the
game or need it installed: they use a synthetic mod, database and inspector.

## Code rules

- **Standard library only**: the package must run on a bare Python 3.10. A
  missing pip package on the machine where a measurement is wanted is one more
  thing to break. `jscheck` and its tree-sitter parser are the one exception.
- **Probe scripts import nothing**: an unresolved import takes the whole script
  down. This is also what lets `live` inject them into a running game.
- **Log and bail, never throw**: guard every engine call in the probe. A throw
  during startup takes a panel with it. `console.error` reaches UI.log;
  `console.log` does not.
- **Build stamp**: `lab-core.js` has one. Bump it on every probe edit. It is
  logged at load, and `civ7lab logs stamps` reads it back to show which build
  the game ran.
- **Load-time code**: a new file, a modinfo change, or a new top-level
  constant or listener only takes effect after a game restart.
- **Engine APIs**: only call what the shipped code in `reference` calls. An
  invented API fails at the moment a measurement is wanted.
- **Plain data**: every collector returns plain data, so the same value goes
  into the log and comes back over the debugger unchanged.
- **Output**: the answer first, detail on request. Every command that produces
  data takes `--json`, so a result can go straight into a diff or a spec.

## What is confirmed

In a running game, 21 Sep 2026, build 25245002:

- **Inspector port**: with `UIDebugger 1`, line 7 of `UI.log` reads
  `Inspector initialized. Remote debugging available on port: 9444`. The
  client tries 9444 first.
- **Automation**: `-autojson` with a generated suite works. `Automation.log`
  shows `Running Test: LoadGame`, `Load successful` and `[PASS] LoadGame`. A
  save loaded in twelve seconds with nobody touching a menu.
- **LoadGame needs `Test=End`**: without it the game unloads to the main menu
  four seconds after the save loads. `End` stops the automation and leaves the
  game as it is.
- **The probe loads and prints**: `UI.log` carries its build stamp and records,
  and `civ7lab logs records` decodes them.
- **One UI context**: `fs://game/root-game.html` holds the gameplay APIs.
  cohtml's `webSocketDebuggerUrl` echoes the request path into itself, so
  `/json/list` advertises an address that is not an endpoint. The client uses
  the `ws=` parameter of `devtoolsFrontendUrl` instead.
- **Collector numbers**: on a turn 44 Antiquity save, tile (20,7) read
  `YIELD_SCIENCE: 36`, the figure measured by hand. `greatworks` gave Library 4
  and Academy 6. The offline harness predicted 34 `TypeTags` rows for
  Antiquity and the game reported 34.
- **Fix without restart**: a collector fixed and re-injected gave the corrected
  answer seconds later in the same game.
- **Live patches reach importers**: replacing one module changed what a second
  module, which imports it statically, drew. No reload.
- **`ui watch` end to end**: each save patched in under half a second. A save
  with a missing brace came back `REJECTED, did not compile, line 67:1:
  Uncaught SyntaxError` and the game kept the previous version. A patched
  top-level table kept its old value, as the load-time warning predicts.
- **Two clients at once**: a second session can read values while the watcher
  stays attached.
- **What the inspector supports**: the DOM, matched and computed CSS, element
  highlighting, the loaded script list, live edit and dynamic `import()` all
  work. `Page.captureScreenshot` never answers. Chromium's own DevTools
  attaches at
  `devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9444/devtools/page/0`
  but is slow against a 700 KB page.

Offline, with tests: the record protocol, including that a truncated log line
is reported instead of parsed; the DevTools client, including fragmented
replies and events arriving mid-request; the SQL harness and modinfo reader;
the script checker, snapshot diff and spec runner. The SQL harness was also run
against a real mod and the game's own dump.

`workshop tags`, 30 Sep 2026: Mod, UI submitted to a live item as app
3688890 gave `OK`, and the web API read `Mod, UI` back straight away.

Measured and not working: `UIFileWatcher 1` did not reload a mod's UI script
within 45 seconds of an edit. It may watch only the game's own files, or not
follow symlinks. Patching over the debugger is the route that works.

## Known gaps

- Not yet seen in a game: whether `ui watch` reattaches after a restart, or
  after a new age reloads the UI.
- Only Linux and the Steam install have been tried.

## Writing style

This applies to docs, comments, program output and commit messages.

Plain English, blunt, short. If ten words will do, do not write a hundred. The
reader is busy and wants the important bits. The prose stays neutral
international English. Avoid buzzwords and jargon unless there is no other way
to say it.

- **Em-dashes**: do not use them, and do not use a spaced hyphen in their place.
  Use a colon, a semicolon or a separate sentence.
- **Contrasts**: do not over-use "X, not Y". Vary it with "rather than",
  "instead of" or a plain restatement.
- **Asides**: keep brackets rare. Move a secondary thought into its own
  sentence. Terse labels in reference tables are fine.
- **Headings**: sentence case. Write bulleted definitions as
  **term**: description.
- **Program output**: quote it verbatim, including punctuation and symbols.
- **Filler**: every sentence must add a fact, an example or a consequence.
  State the rule and give the case.
- **Names**: do not name individual people in the code, docs or commits.
- **Line length**: wrap prose and comments at about 79 columns.

## Commit messages

Plain English, imperative mood, no Conventional Commit prefixes. A subject line
is often the whole message. Add a body only when the reason is not obvious,
and keep it to a sentence or two. Do not write bulleted essays or restate the
diff.
