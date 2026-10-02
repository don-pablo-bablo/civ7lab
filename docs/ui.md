# Changing UI scripts without a restart

```bash
civ7lab ui watch path/to/mod/ui              # every .js under it, until Ctrl-C
civ7lab ui watch path/to/mod/ui/panel.js     # one file
civ7lab ui push path/to/mod/ui               # bring the game level once, then exit
```

Needs the game running with `UIDebugger` on. See [setup.md](setup.md).

Save a file and the game runs the new version about a second later. Each save
is sent to the game's JavaScript engine as a live edit: the loaded module's
functions are replaced in place, and every module that imports them calls the
new code from then on. The mod needs no changes for this. The file on disk
stays the only copy, and a restart loads it.

```
14:02:11  panel.js  patched (0.31s)
```

## What a patch cannot change

A patch does not run anything again. Constants, lookup tables, registration
calls and the body of a `(function () { ... })()` wrapper ran once when the
game loaded the file. The watcher still sends such edits, and warns which
lines need a restart:

```
14:03:40  panel.js    warning: load-time code differs from what the game loaded (line 12). It ran once, outside any function, and a patch does not run it again: restart the game for it.
```

Edits inside functions take effect on the next call.

A file the game did not load at start cannot be patched. A new script needs
a modinfo entry and a restart, and the watcher says so.

A save that does not compile is rejected with its line number, as in
`REJECTED, did not compile, line 67:1: Uncaught SyntaxError`, and the game
keeps the previous version.

## Redrawing a panel

A panel already on screen is not redrawn by a patch. A tooltip picks up the
change the next time it opens. For a panel that stays open, either:

- **Listen for the event**: after every patch the game's `window` receives a
  `civ7lab-patched` event, with the file's URL in `detail.url`.
- **Pass `--after`**: `civ7lab ui watch MOD/ui --after 'MyPanel.redraw()'`
  runs that JavaScript after each patch.

## Between games

With no save loaded, the watcher waits and tries to attach every two seconds.
It attaches by itself when a save loads, after the game restarts, and when a
new age reloads the UI.
