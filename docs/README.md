# civ7lab docs

One page per area. The [main README](../README.md) lists tasks and the
command for each, and [scenarios.md](scenarios.md) walks through common jobs
from start to finish.

| page | commands | covers |
|---|---|---|
| [setup.md](setup.md) | `doctor`, `options`, `mod` | a new machine, the game's developer switches, linking mods, environment variables |
| [offline.md](offline.md) | `sql`, `modinfo`, `jscheck`, `text`, `dbdiff` | checking a mod's data and scripts without starting the game |
| [live.md](live.md) | `live`, `check`, `diff` | reading a running game, running JavaScript in it, snapshots, specs, Chromium DevTools |
| [ui.md](ui.md) | `ui` | changing UI scripts in a running game on save |
| [runs.md](runs.md) | `run`, `logs` | opening saves and autoplaying from the command line, recording plans, logs, build stamps |
| [mock.md](mock.md) | `mock` | laying out a panel in a browser from cases the game drew |
| [workshop.md](workshop.md) | `workshop` | setting Steam Workshop tags, descriptions and preview images, and uploading a new version |
| [probe.md](probe.md) | | the in-game half: its API, your own collectors, the record format |
| [dev-speed-boost.md](dev-speed-boost.md) | `mod install dev-speed-boost` | the mod that speeds a test game up: its options, and changing them |

Pick the cheapest route that answers the question: offline first, then live,
then logs, then a full run.
