# Contributing

## How it works

A Python package drives the game from outside, and a small probe mod reads it
from inside. Each area has one command file, one or more modules that do the
work, and one docs page:

| area | command file | modules | docs |
|---|---|---|---|
| setup | `commands/machine.py` | `doctor.py`, `appoptions.py`, `mod.py`, `paths.py` | `setup.md` |
| offline | `commands/offline.py` | `sqlcheck.py`, `modinfo.py`, `jscheck.py`, `textcheck.py`, `dbdiff.py` | `offline.md` |
| live | `commands/live.py` | `live.py`, `cdp.py`, `check.py`, `diff.py` | `live.md` |
| ui | `commands/ui.py` | `hotswap.py` | `ui.md` |
| runs and logs | `commands/run.py` | `runner.py`, `logs.py`, `records.py` | `runs.md` |
| mock | `commands/mock.py` | `mock.py`, `mock/panel.html` | `mock.md` |
| workshop | `commands/workshop.py` | `workshop.py` | `workshop.md` |

Command files and modules are under `civ7lab/`, docs under `docs/`.

| path | what it is |
|---|---|
| `pyproject.toml`, `uv.lock` | the project, its dev tools and their pinned versions |
| `.github/workflows/checks.yml` | lint, formatting and tests on every push and pull request |
| `.github/dependabot.yml` | weekly updates for the actions the workflow pins to commits |
| `civ7lab/commands/_common.py` | the command list `civ7lab` prints, and the parser helper |
| `civ7lab/cdp.py` | the DevTools client: WebSocket, requests, console events |
| `civ7lab/records.py` | the `[C7LAB]` log record format |
| `mod/civ7lab-probe/` | the probe mod: it only reads and prints |
| `.../ui/lab-core.js` | the `C7Lab` global: collector registry and record writer |
| `.../ui/lab-collect.js` | the collectors |
| `.../ui/lab-hooks.js`, `lab-plan.js` | runs a recording plan during autoplay |
| `specs/` | example specs |
| `plans/` | example recording plans |
| `tests/` | tests, no game needed |
| `tests/conftest.py` | the fake game folder and the Node runner the tests share |
| `reference` | gitignored link to the game's resources folder |

Link the game's resources folder, the one that contains `Base`, as `reference`
in the repo root. It holds the shipped UI code, which is the list of engine
APIs that are safe to call.

## Adding a command

- **Command file**: add the parser and handler to the area's file in
  `civ7lab/commands/`. Give the parser examples, as the others do.
- **Command list**: add the command to `GROUPS` in `_common.py`. The parser
  refuses to build if the two differ.
- **Docs**: add it to the area's page in `docs/`, and to the task tables in
  `README.md` if it answers a new question.
- **Old command lines**: keep them working. Other mods' docs quote them.

## Tests

```bash
uv sync
uv run pytest                     # every test
uv run pytest tests/test_probe.py # one file
uv run ruff check                 # lint
uv run ruff format                # format
```

The tests need Node, for the probe's JavaScript. CI runs all four on every
push and pull request, and fails on any of them.

No test launches the game or needs it installed. They avoid mocks:

- **Game folders**: the `game` fixture lays out an install folder and a user
  folder on disk, with logs, saves and mods, and points `CIV7_INSTALL` and
  `CIV7_USER` at them. The code under test runs unchanged.
- **The probe**: the `js` fixture runs the real probe scripts in Node, and the
  Python side reads what they print. `test_live.py` uses Node as the game's
  UI, so injecting the probe is tested against the real probe.
- **Boundaries**: the DevTools client is tested against a real WebSocket
  server. Only Steam and its web API are replaced, in `test_workshop.py`.

Keep new code testable the same way: a function that takes paths or data and
returns a result, called by a command handler that only parses and prints.
`runner.suite_for` and `commands/run.py` show the split.

## Code rules

- **Standard library only**: the package must run on a bare Python 3.14. A
  missing package on the machine where a measurement is wanted is one more
  thing to break. `jscheck` and its tree-sitter parser are the one exception.
  Dev tools go in the `dev` group in `pyproject.toml`.
- **Probe scripts import nothing**: an unresolved import takes the whole script
  down. This is also what lets `live` inject them into a running game.
- **Log and bail, never throw**: guard every engine call in the probe. A throw
  during startup takes a panel with it. `console.error` reaches UI.log;
  `console.log` does not.
- **Build stamp**: `lab-core.js` prints a hash of the probe's files at load,
  and `civ7lab logs stamps` reads it back. After a probe edit,
  `test_build_stamp_matches_the_files` fails and prints the new line to paste.
  `live` decides whether to inject from the files themselves, so a stale stamp
  never leaves a running game on the old probe.
- **Load-time code**: a new file, a modinfo change, or a new top-level
  constant or listener only takes effect after a game restart.
- **Engine APIs**: only call what the shipped code in `reference` calls. An
  invented API fails at the moment a measurement is wanted.
- **Plain data**: every collector returns plain data, so the same value goes
  into the log and comes back over the debugger unchanged.
- **Output**: the answer first, detail on request. A new command that
  produces data takes `--json`, so its result can go straight into a diff or
  a spec.
- **Docs**: keep `-h` examples, the docs pages and the README task tables in
  step with the code. Quote program output verbatim.

## Confirmed in game

On Linux, against the Steam version, build 25516395:

- **Setup**: `doctor`, `options --live` and `--set`, `mod install`.
- **Offline**: `sql` with and without `--query`, `modinfo`, `jscheck`,
  `text` and `dbdiff`, on real mods and the game's own database.
- **Runs**: opening a save, `--inspector`, autoplaying a new game, `--quit`,
  recording plans with all three triggers, `--seed`, and the Steam overlay.
- **Live**: `targets`, `attach`, `collect` with every collector, `eval`,
  `members`, `snapshot`, `watch --all` and `autoplay`, and injecting an
  edited probe.
- **UI patching**: `ui watch` and `ui push`, including a rejected save and
  attaching again after a restart and after an age change.
- **Comparing**: `check` and `diff`, against the game and against snapshots.
- **Logs**: `errors`, `stamps`, `records` and `marker`.
- **Mock**: `serve` and `fixtures`, with a real mod's panel.
- **Workshop**: `tags` and `description`, on a published item.

## How the game behaves

Facts the code depends on, found by trying them.

- **Inspector**: with `UIDebugger 1` it listens on port 9444. The gameplay
  APIs are in one context, `fs://game/root-game.html`.
- **Target address**: `webSocketDebuggerUrl` repeats the request path, so it
  is not a real address. The `ws=` parameter of `devtoolsFrontendUrl` is.
- **Console**: `console.log` reaches the inspector but not `UI.log`;
  `console.error` reaches both. A new console session first replays every
  line since the game started.
- **Inspector limits**: `Page.captureScreenshot` never answers.
- **Live edit**: replaces a module's functions in place, and modules that
  import it call the new code. Code that ran at load does not run again. A
  save that does not compile is rejected and the old version kept.
- **UIFileWatcher**: does not reload a mod's scripts.
- **AppOptions.txt**: the game writes it with CRLF line endings, even on
  Linux, and rewrites it on exit.
- **LoadGame**: without a final `Test=End` the game unloads to the main menu
  four seconds after loading. It ignores `Turns` when given a save, and the
  game then waits on its Begin Game screen for a click.
- **Autoplay**: the local player is `-1`. It stops by itself at the end of an
  age, the new age waits on its Continue button, and the UI reloads. It
  leaves a save named `Automation_<date>` in `Saves/Single`.
- **Steam overlay**: a game Steam starts gets `LD_PRELOAD` of
  `gameoverlayrenderer.so`, `ENABLE_VK_LAYER_VALVE_steam_overlay_1=1`,
  `SteamGameId` and `SteamOverlayGameId`. Without them F12 does nothing.

## Known gaps

- **Windows**: built from the game's community documentation and tested on a
  Windows runner, but not tried against the game there.

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

## Pull requests

Every change reaches `main` through a pull request. Nobody can push to it
directly.

- **Branch**: from `main`, with one change per pull request.
- **Title**: write it as a commit message. Pull requests are squash-merged, so
  the title becomes the commit's subject line.
- **Checks**: CI must pass on Linux and Windows before a merge. Greptile also
  reviews each pull request.
- **Merging**: the maintainer merges.
