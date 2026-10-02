# Drawing a panel in a browser

A layout change in game costs a restart, or a `ui watch` patch and a hover.
In a browser it costs a refresh, and every saved case is on screen at once.

This works for a panel whose drawing code is kept apart from the rest:

- **Renderer**: a module that imports nothing from the game, takes plain data
  and returns a DOM node, a list of nodes, or an HTML string.
- **Fixtures**: the panel logs the data for each case it draws, as a record.
  Those records become the mock's cases, so they are real tiles rather than
  invented ones.

## In the mod

Log each case the panel draws, in the [record format](probe.md#records):

```js
console.error("[C7LAB] " + JSON.stringify({ v: 1, kind: "my-panel", data: panelData }));
```

`UI.log` cuts long lines at a length the game does not document. With the
probe installed, `C7Lab.emit("my-panel", panelData)` splits a long record into
fragments that `civ7lab` puts back together. A mod that must work without the
probe can copy `emit` from `lab-core.js`.

## Harvest and serve

After a session in which the panel was drawn:

```bash
civ7lab mock fixtures --kind my-panel --out path/to/mod/fixtures.js
civ7lab mock serve --root path/to/mod --renderer ui/my-panel-render.js --open
```

The page calls the renderer's `render` export once per fixture. `--export`
names another. A fixture's `label` or `name` field titles its box.

`--latest-by cityName,loc.x,loc.y` keeps only the last record of each case,
since a panel logs the same tile every time it opens. The fields are dotted
paths into the data.

## Limits

- **Icons**: they show as coloured discs, because `blp:` is the engine's own
  protocol. Check icon art in game.
- **Styles**: the page does not load the game's stylesheet. A panel that
  relies on it needs its own mock page that links the game's CSS, as
  [Better Yield Tooltip](https://github.com/don-pablo-bablo/civ7_better_yield_tooltip)
  does.
- **Fonts**: the game has no italic face. The browser does, so italics look
  fine here and vanish in game.
