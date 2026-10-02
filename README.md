# civ7lab

[![checks](https://github.com/don-pablo-bablo/civ7lab/actions/workflows/checks.yml/badge.svg)](https://github.com/don-pablo-bablo/civ7lab/actions/workflows/checks.yml)

A command-line test bench for Civilization VII mods.

Checking a mod change usually means restarting the game, playing until the
situation exists, then reading a number off the screen or out of a log.
civ7lab answers most of those questions without a restart, and many without
starting the game at all.

It works with any mod. Point it at a mod folder and it reads that mod's
modinfo for what to apply and what to check.

**Linux and Windows.** It works with the Steam version of the game. It has
been used against the game on Linux. On Windows its tests pass, but it has
not yet been tried against the game itself, so treat it as a first version
and [report problems](https://github.com/don-pablo-bablo/civ7lab/issues).
macOS is not supported.

## What it can do

[docs/scenarios.md](docs/scenarios.md) walks through common jobs from start
to finish. The tables below list single tasks.

### Without starting the game

| I want to | Command |
|---|---|
| [See which rows my SQL and XML add or remove](docs/offline.md#sql) | `civ7lab sql MOD --age AGE_ANTIQUITY` |
| [Catch a foreign key error before a launch](docs/offline.md#sql) | `civ7lab sql MOD` |
| [Query the game's database, with or without my mod](docs/offline.md#queries) | `civ7lab sql --query "SELECT ..."` |
| [Find text keys my mod uses that nothing defines](docs/offline.md#text) | `civ7lab text MOD` |
| [See what a game patch changed in the database](docs/offline.md#dbdiff) | `civ7lab dbdiff BEFORE AFTER` |
| [List which files load in each age, in order](docs/offline.md#modinfo) | `civ7lab modinfo MOD` |
| [Find items left commented out in the modinfo](docs/offline.md#modinfo) | `civ7lab modinfo MOD` |
| [Find UI scripts that never load, or break on import](docs/offline.md#jscheck) | `civ7lab jscheck MOD` |

### With the game running

| I want to | Command |
|---|---|
| [Read a tile's yields, terrain and buildings](docs/live.md#collectors) | `civ7lab live collect tile --args '{"x":20,"y":7}'` |
| [Read a city's yields, buildings and Great Works](docs/live.md#collectors) | `civ7lab live collect city --args '{"name":"Rome"}'` |
| [See every source behind a city's yield](docs/live.md#collectors) | `civ7lab live collect yieldtree --args '{"name":"Rome"}'` |
| [Check my mod's data reached the game](docs/live.md#collectors) | `civ7lab live collect tags --args '{"prefix":"MYMOD_"}'` |
| [Run any JavaScript in the game's UI](docs/live.md#run-javascript) | `civ7lab live eval 'Game.turn'` |
| [See `console.log` output, which UI.log never gets](docs/live.md#watch-the-console) | `civ7lab live watch --all` |
| [List the methods on an engine object](docs/live.md#run-javascript) | `civ7lab live members 'Players.get(0)'` |
| [See a UI script change without restarting](docs/ui.md) | `civ7lab ui watch MOD/ui` |
| [Inspect the game's UI in Chromium DevTools](docs/live.md#chromium-devtools) | a browser address |
| [Let the AI play my save for a number of turns](docs/live.md#autoplay) | `civ7lab live autoplay 20` |
| [Save the game state and compare it later](docs/live.md#snapshots-and-diffs) | `civ7lab live snapshot`, `civ7lab diff` |
| [Write a check down and run it again](docs/live.md#specs) | `civ7lab check SPEC` |

### Launching and logs

| I want to | Command |
|---|---|
| [Open my newest save from the command line](docs/runs.md) | `civ7lab run --save latest --inspector` |
| [Autoplay a seeded game and keep its logs](docs/runs.md#autoplay) | `civ7lab run --turns 40 --seed 1 --quit` |
| [Find the error lines in the logs](docs/runs.md#logs) | `civ7lab logs errors` |
| [Check which build of my script the game ran](docs/runs.md#build-stamps) | `civ7lab logs stamps` |
| [Keep the logs before the next launch empties them](docs/runs.md#logs) | `civ7lab logs snapshot` |
| [Get my mod's own data out of UI.log](docs/probe.md#records) | `civ7lab logs records` |

### Other

| I want to | Command |
|---|---|
| [Lay out a panel in a browser instead of in game](docs/mock.md) | `civ7lab mock serve` |
| [Set Workshop tags when the uploader will not](docs/workshop.md) | `civ7lab workshop tags ITEM TAGS` |
| [Update a Workshop description from a file](docs/workshop.md#description) | `civ7lab workshop description ITEM FILE` |

[CONTRIBUTING.md](CONTRIBUTING.md#confirmed-in-game) lists what has been
confirmed in a running game.

`civ7lab` on its own lists the commands, and `civ7lab COMMAND -h` gives
examples for each.

## Install

It needs Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/don-pablo-bablo/civ7lab
cd civ7lab
uv tool install --editable '.[jscheck]'
```

This puts a `civ7lab` command on your PATH that runs from the clone, so a
`git pull` takes effect with no reinstall. uv fetches Python 3.14 if you do
not have it. `[jscheck]` adds the JavaScript parser `jscheck` uses; everything
else needs only the standard library. If uv says its tool folder is not on
your PATH, run `uv tool update-shell`.

Paths you give `civ7lab` are relative to the folder you run it from. If you
move the clone, run the install again. `uv tool uninstall civ7lab` removes it.

## Start here

```bash
civ7lab doctor            # what works on this machine, and the fix for what does not
civ7lab options --live    # turn on the game's inspector and database dumps
```

Restart the game after `options`: it reads them at launch. Run `doctor` again
after a game patch. See [docs/setup.md](docs/setup.md).

## AI use

The code and docs were written with AI, using Claude Code. The tool is
tested against the running game, and CONTRIBUTING.md lists what has been
confirmed there.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT. See [LICENSE](LICENSE).
