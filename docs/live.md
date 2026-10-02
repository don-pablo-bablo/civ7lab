# Asking a running game

The game's UI runs on Coherent cohtml, which embeds the Chrome DevTools
protocol. The `UIDebugger` switch starts its server on port 9444. With it on,
civ7lab can run JavaScript in the game and read back the result: no restart,
no screenshot, no log.

Turn it on once with `civ7lab options --live`, then start the game and load
a save. `civ7lab run --save latest --inspector` does both.

```bash
civ7lab live attach
```

`attach` connects, makes sure the game has the probe's collectors, and lists
them. The probe need not be installed as a mod: its scripts import nothing,
so they can be added to any game in progress, with any mods or none. Every
`live` command does this first, and pushes the probe in only when the game
has none or an older copy.

## Collectors

A collector reads one thing from the game and returns plain JSON.

```bash
civ7lab live collect tile --args '{"x":20,"y":7}'
civ7lab live collect city --args '{"name":"Rome"}' --out rome.json
civ7lab live attach             # the list, from the game
```

| collector | arguments | returns |
|---|---|---|
| `game` | none | turn, age, map size, players |
| `tile` | `x`, `y`, optional `player` | yields, terrain, biome, feature, resource, owner, district, city, and what stands on it |
| `tiles` | `x`, `y`, `radius`, or `rect: [x0,y0,x1,y1]`; `all` to keep empty tiles | many tiles at once |
| `cities` | optional `player`, `name` | each city's name, position, population |
| `city` | optional `name`, matching part of the name; `all` to keep empty tiles; `tree` to add the yield tree | yields, Great Works and tiles, for every matching city |
| `yieldtree` | `name`, optional `yield` such as `YIELD_SCIENCE` | the city's full yield breakdown, as the City Details screen walks it |
| `greatworks` | optional `name` | Great Work slots and what each building's works pay |
| `tags` | `prefix`, optional `type`, `limit` | TypeTags rows in the running game's database |
| `def` | `table`, `type` | one GameInfo row, such as `{"table":"Units","type":"UNIT_SCOUT"}` |

`tags` is the quickest way to tell "my rule is wrong" from "my rule never
loaded". No rows with your prefix means your SQL did not reach the game.

In `yieldtree`, a node whose children do not add up to its value carries an
`unexplained` amount. The engine gives some totals without a full breakdown.

`--also-log` prints the result to `UI.log` as well, so it survives the game
closing. To add your own collectors, see [probe.md](probe.md).

## Run JavaScript

```bash
civ7lab live eval 'Game.turn'
civ7lab live eval 'GameInfo.Units.lookup("UNIT_SCOUT")'
civ7lab live members 'Players.get(0)'
```

`eval` runs any expression in the game's UI and prints the result as JSON.
`--file script.js` runs a whole file and prints the value of its last
statement, so a script can end with the value it wants to show.
Objects that do not serialise, such as DOM nodes, come back as `{}`. A throw
comes back as the game's own message, such as `X is not defined`.

`members` lists every property and method of an engine object, up its
prototype chain, with each method's argument count. Use it to find out what
an API offers.

Only call engine APIs that the game's own UI calls. Its code is in the
game's resources folder, under `Base/modules`.

## Watch the console

```bash
civ7lab live watch --seconds 60    # the probe's records
civ7lab live watch --all           # every console line
```

`--all` shows every line the game's UI prints, including `console.log`,
which never reaches `UI.log`. It is the only way to see those lines. It
starts with every line printed since the game started, then follows new
ones.

## Autoplay

```bash
civ7lab live autoplay 20       # the AI plays 20 turns of the open game
civ7lab live autoplay --stop   # hand it back at the end of this turn
```

The AI plays every player, you included, then hands the game back to you. It
uses the same calls as the game's own automation. Autoplay stops by itself
when an age ends; the new age then waits on its Continue button.

This is the way to autoplay a save: `civ7lab run --save` cannot, because the
game's load test ignores a turn count when it opens a save.

## Snapshots and diffs

```bash
civ7lab live snapshot --collect game tile:'{"x":20,"y":7}' 'city:{"all":true}' --out before.json
# make the change, play a turn
civ7lab live snapshot --collect game tile:'{"x":20,"y":7}' 'city:{"all":true}' --out after.json
civ7lab diff before.json after.json
```

A snapshot runs several collectors and stamps the result with the time, turn,
age and probe build. `diff` prints a count, then one line per changed path:
`~ path: before -> after`, `+ path = value` or `- path = value`.

Items in a list are matched by x and y, type or name, so one added building
is one change. `--path` compares one part, `--json` gives the full list.

## Specs

A spec writes a check down so it can be run again the same way.

```json
{
  "name": "a tile's science held up",
  "collect": [{ "as": "tile", "collector": "tile", "args": { "x": 20, "y": 7 } }],
  "expect": [
    { "path": "tile.yields.YIELD_SCIENCE", "op": ">=", "value": 30,
      "why": "36 when measured" },
    { "path": "tile.constructibles[type=BUILDING_LIBRARY]", "op": "present" }
  ]
}
```

```bash
civ7lab check specs/example-tile-yield.json                         # live game
civ7lab check specs/example-tile-yield.json --snapshot before.json  # saved snapshot
```

- **Paths**: dots for keys, `[2]` for an index, `[type=X]` for the list item
  whose `type` is X, and `[x=3,y=4]` to match several fields. A path `diff`
  prints can be pasted into a spec as it is.
- **Operators**: `==`, `!=`, `>`, `>=`, `<`, `<=`, `contains`, `len`,
  `present`, `absent`.
- **why**: printed when the expectation fails.

The exit code is 0 when every expectation passes. `specs/` has examples.

## Chromium DevTools

For the DOM, the CSS and the list of loaded scripts, open this in Chromium or
Chrome while the game runs:

```
devtools://devtools/bundled/inspector.html?ws=127.0.0.1:9444/devtools/page/0
```

It is slow against the game's 700 KB page. Screenshots from the inspector do
not work.

## Contexts

`civ7lab live targets` lists the UI contexts the game offers. The gameplay
APIs are in `fs://game/root-game.html`, which civ7lab picks by default.
`--target` picks another by part of its URL.

A second session can attach while `ui watch` runs.
