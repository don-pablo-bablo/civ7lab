# The probe

The probe is the part of civ7lab that runs inside the game. It is plain
JavaScript that imports nothing, in `mod/civ7lab-probe/ui/`, and it installs
one global, `C7Lab`. It reads the game and prints; it changes nothing.

It gets into the game in one of two ways:

- **Injected**: every `civ7lab live` command pushes it into the running game.
  Nothing is installed, and it is gone at the next restart.
- **Installed**: `civ7lab mod install` links it into `Mods`, so it loads with
  every game. Autoplay runs with a `--plan` need this.

## C7Lab

| call | does |
|---|---|
| `C7Lab.collect(name, args)` | runs a collector and returns its data |
| `C7Lab.dump(name, args)` | the same, and prints it to `UI.log` as a record |
| `C7Lab.emit(kind, data)` | prints any data to `UI.log` as a record |
| `C7Lab.log(text)` | prints a line of text as a record of kind `log` |
| `C7Lab.register(name, fn, description)` | adds a collector |
| `C7Lab.members(expression)` | lists what an engine object has on it |
| `C7Lab.list()` | the collectors and their descriptions |
| `C7Lab.build` | the probe's build stamp |

[live.md](live.md#collectors) lists the collectors it ships with.

## Your own collectors

A collector is a function that takes an arguments object and returns plain
data: no engine objects and no cycles. Register one over the inspector:

```bash
civ7lab live eval 'C7Lab.register("units", function (args) {
  return { count: Players.get(GameContext.localPlayerID).Units.getUnitIds().length };
}, "how many units the local player has")'
civ7lab live collect units
```

It lasts until the game restarts. For a permanent one, add it to
`lab-collect.js`. The next `live` command sees the file changed and injects
the new version. Run `uv run pytest` too: it gives the new build stamp to put
in `lab-core.js`.

Wrap each engine call in `C7Lab.safe(function () { ... })`. A failure then
comes back as `{error: ...}` in that field, and the rest of the result still
arrives. Only call engine APIs the game's own UI code calls.

## Records

A record is how a script in the game gets data out through `UI.log`. Any mod
can print them; the probe need not be loaded.

```
[C7LAB] {"v":1,"seq":7,"kind":"tile","turn":44,"data":{...}}
```

- **v**: format version, 1.
- **kind**: what the data is. Readers filter on it.
- **data**: any JSON.
- **seq**: optional. A gap in the numbers is reported as a lost record.
- **turn**, **run**: optional.

Print records with `console.error`, since `console.log` does not reach
`UI.log`.

`UI.log` cuts long lines. `C7Lab.emit` splits a long record into fragments
tagged `[C7LAB#]`, each stating its own length, and the readers put them back
together. A fragment that was cut is reported as an error on that record
rather than parsed as wrong data.

Records can be read back with:

- `civ7lab logs records`, a count per kind, or `--json` for all of them;
- `records.jsonl` in a [run folder](runs.md#what-a-run-leaves);
- `civ7lab mock fixtures`, to turn one kind into [mock](mock.md) cases.
