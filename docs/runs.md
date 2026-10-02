# Launching the game, and its logs

## Open a save

```bash
civ7lab run --save latest --inspector    # the newest save in Saves/Single
civ7lab run --save MySave                # a save by name
civ7lab run --save MySave --dry-run      # print the command, launch nothing
```

The game loads the save with nobody touching a menu, then waits on its
Begin Game screen: click it to start playing. It stays open until you quit.
`--inspector` turns `UIDebugger` on for this launch only, so `live` and `ui`
can attach, and leaves your own settings file alone.

On Linux the game gets Steam's overlay as it would when Steam starts it, so
F12 screenshots and Shift+Tab work. On Windows, Steam adds its overlay only
to games it starts itself.

`--turns` does not work with `--save`: the game's load test ignores it. Open
the save, then run [`civ7lab live autoplay`](live.md#autoplay).

Autosaves cannot be loaded this way. The game's load test only takes saves
from `Saves/Single`. `latest` also skips the saves autoplay leaves there,
named `Automation_<date>`.

This uses the game's own automation: a suite of test scripts with parameters
such as `{ Test=LoadGame, SaveName=X }`, passed to the game with
`-autojson`. Steam must be running.

## Autoplay

```bash
civ7lab run --turns 40 --seed 12345 --quit
civ7lab run --turns 40 --seed 12345 --plan plans/sample-every-five.json --quit
```

Starts a new game and lets the AI play it. `--seed` sets the game's map and
game seeds, so two runs with the same seed play the same game: the same
civilizations on the same map. A number that changes between them is down to
your change.

`--quit` exits the game when the turns are done. A new game stops after 30
minutes unless `--timeout` says otherwise. The game logs each turn to
`Automation.log`.

### Recording plans

Nobody is watching an autoplay run, so what to record must be decided before
launch. A plan lists collectors and when each fires:

```json
{
  "onTurn":       [{ "collector": "cities", "args": { "player": 0 }, "every": 5, "from": 10, "to": 40 }],
  "onCitySelect": [],
  "onAgeEnd":     [{ "collector": "city", "args": { "player": 0, "all": true } }]
}
```

In autoplay nobody is the local player: the game reports it as `-1`. So a
collector that reads a player's cities needs `"player"` set, or it finds none.

`onCitySelect` fires when you select one of your cities, and its entries get
that city's `name` unless their `args` give one. Each firing is written to
`UI.log` as a record. `--plan` writes the plan into the probe, so the probe
must be installed with `civ7lab mod install`. `plans/` has examples, and
[live.md](live.md#collectors) lists the collectors.

## What a run leaves

Each run gets a folder under `./runs`:

| file | what it is |
|---|---|
| `suite.json`, `command.txt` | what was launched |
| `logs-before/` | the previous session's logs, copied before launch |
| `logs-after/` | this session's logs |
| `records.jsonl` | every record from `UI.log`, one per line |
| `summary.json` | exit code, duration, game build, record and error counts |
| `stdout.log` | the game's console output |

## Logs

The game empties every log when it starts. Copy them first.

```bash
civ7lab logs snapshot --out keep/        # copy the whole log folder
civ7lab logs errors                      # only the lines that report an error
civ7lab logs errors --dir keep/          # the same, on a copy
civ7lab logs marker --marker "[MYMOD]"   # every UI.log line with your tag
civ7lab logs records                     # decode records printed with the probe's format
```

`errors` reads `Database.log`, `Modding.log` and `UI.log`, and reports
foreign key and unique constraint failures, SQL errors, failed loads,
script exceptions and asserts, each with its file and line.

Only `console.error` reaches `UI.log`. `console.log` does not.

### Build stamps

Mod files are read at game start. A check against a stale build looks
exactly like a check against the fresh one, so each script should print a
stamp when it loads:

```js
const MYMOD_BUILD = "12";
console.error("civ7lab:build my-panel " + MYMOD_BUILD);
```

Bump the constant on every edit. Then:

```bash
civ7lab logs stamps
```

```
my-panel             12
probe                probe-53aea152
```

`jscheck` warns about scripts with no stamp.
