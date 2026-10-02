# Scenarios

Each of these starts from a real question and uses the cheapest command
that answers it: offline first, then the running game, then a launch.

## My SQL change does nothing in game

1. **Did it apply at all?** Check offline, in a second:

   ```bash
   civ7lab sql path/to/mod --age AGE_ANTIQUITY --prefix MYMOD --rows 5
   ```

   A `FAIL` line names the file and the SQLite error. A foreign key error
   here means the row you refer to does not exist in that age.

2. **Did it change what you meant?** Query the database with your mod
   applied:

   ```bash
   civ7lab sql path/to/mod --age AGE_ANTIQUITY \
     --query "SELECT * FROM Modifiers WHERE ModifierId LIKE 'MYMOD%'"
   ```

3. **Did it reach the running game?** With a save loaded:

   ```bash
   civ7lab live collect tags --args '{"prefix":"MYMOD_"}'
   ```

   A count of 0 means the game never loaded your rules in this age. Check
   `civ7lab modinfo path/to/mod` for which files load in which age, and
   `civ7lab logs errors` for what the game complained about.

## Tuning a tooltip or panel

1. Start the game with the inspector on and load a save:

   ```bash
   civ7lab options --live
   civ7lab run --save latest --inspector
   ```

2. Leave the watcher running while you edit:

   ```bash
   civ7lab ui watch path/to/mod/ui
   ```

   Each save reaches the game in about a second. A tooltip shows the change
   the next time it opens. If the watcher warns that a line runs once at
   load, that line needs a restart.

3. To see `console.log` output, which never reaches `UI.log`, run
   `civ7lab live watch --all` in a second terminal.

4. After the next restart, `civ7lab logs stamps` confirms which build of
   your script the game loaded.

For layout work, [the browser mock](mock.md) is faster still: every saved
case on one page, and a change costs a refresh.

## Did my change survive the age transition?

1. On a save shortly before the age ends, take a snapshot:

   ```bash
   civ7lab live snapshot --collect game 'city:{"all":true}' --out before.json
   ```

2. Play into the next age, yourself or with `civ7lab live autoplay 20`,
   which stops when the age ends. Click Continue on the new age's screen,
   then take another snapshot:

   ```bash
   civ7lab live snapshot --collect game 'city:{"all":true}' --out after.json
   civ7lab diff before.json after.json
   ```

3. When you know what should hold, write it down as a
   [spec](live.md#specs), so the next check is one command:

   ```bash
   civ7lab check my-spec.json --snapshot after.json
   ```

## What does this engine object do?

```bash
civ7lab live members 'Players.get(GameContext.localPlayerID)'
civ7lab live eval 'Players.get(GameContext.localPlayerID).Units.getUnitIds().length'
```

`members` lists every property and method, with each method's argument
count. `eval` tries a call and prints the result, or the game's own error
message. For the DOM and CSS, open
[Chromium DevTools](live.md#chromium-devtools) on the same game.

Prefer calls the game's own UI makes. Its code is under
`Base/modules` in the game's install folder.

## What did the game patch change?

Before the patch, copy the database dump:

```bash
cp "$HOME/My Games/Sid Meier's Civilization VII/Debug/gameplay-copy.sqlite" before-patch.sqlite
```

After it, load a save so the game writes a new dump, then:

```bash
civ7lab dbdiff before-patch.sqlite "$HOME/My Games/Sid Meier's Civilization VII/Debug/gameplay-copy.sqlite"
civ7lab text path/to/mod
```

`dbdiff` lists the rows the patch added, removed or changed, table by table.
`text` shows whether any text key your mod relies on has gone.

On Windows the dump is under
`%LOCALAPPDATA%\Firaxis Games\Sid Meier's Civilization VII\Debug`.

## Checking a balance change over 50 turns

```bash
civ7lab run --turns 50 --seed 7 --plan plans/sample-every-five.json --quit --label before
# make the change
civ7lab run --turns 50 --seed 7 --plan plans/sample-every-five.json --quit --label after
```

The same seed gives both runs the same civilizations on the same map. Each
run folder holds `records.jsonl`, one record per collector firing, to
compare. See [runs.md](runs.md).
