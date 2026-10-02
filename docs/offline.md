# Without the game

These commands take a second and need no running game. Use them before any
launch.

## sql

```bash
civ7lab sql path/to/mod --age AGE_ANTIQUITY
civ7lab sql path/to/mod --age AGE_ANTIQUITY --prefix MYMOD --rows 5
civ7lab sql path/to/mod --db my-dump.sqlite --json
```

It copies the game's `Debug/gameplay-copy.sqlite`, turns foreign keys on,
and applies every database file the modinfo lists for that age, in the order
the game applies them. It then reports the rows each table gained or lost:

```
  TypeTags: +34 -0
```

The dump comes from `CopyDatabasesToDisk`, and must be written with a save
loaded. One written at the main menu holds no age's data, and `sql` warns.

It catches three mistakes:

- **Foreign keys**: `INSERT OR IGNORE` does not cover them. An insert naming
  a row this age does not load fails here, instead of in `Database.log` after
  a launch.
- **Dirty baseline**: a dump taken while your mod was loaded already holds
  its rows, so applying it again changes nothing. `--prefix MYMOD` deletes
  tags and types starting with `MYMOD` first, and says how many.
- **Wrong age**: the dump holds only the age it was taken in. Asking about
  another age gets a warning.

GameEffects files are read by the engine's effects system, which is not
reproduced here. They are checked for structure, and for `<GameModifiers>`
rows naming a modifier no file defines.

`--db` applies to another database, such as a dump you copied during play.
`--json` gives the full result for a script or a diff.

### Queries

`--query` runs SQL against the database and prints the rows. With a mod, it
runs on the copy after the mod is applied, so it shows what the game would
end up with. Without one, it reads the game's own dump, which it cannot
change.

```bash
civ7lab sql path/to/mod --query "SELECT * FROM Types WHERE Type LIKE 'MYMOD%'"
civ7lab sql --query "SELECT UnitType, BaseMoves FROM Units ORDER BY BaseMoves DESC"
civ7lab sql --query "SELECT name FROM pragma_table_info('Units')"    # a table's columns
```

## text

```bash
civ7lab text path/to/mod
civ7lab text path/to/mod --prefix LOC_MYMOD
```

Lists `LOC_` keys the mod uses but nothing defines. In game those show as the
raw key, and the only other sign is a line in `Localization.log` after a
launch. It also lists keys the mod defines but never uses.

- **Used**: every `LOC_` key in the mod's scripts, data and modinfo. A key
  built in code, such as `"LOC_UNIT_" + name`, cannot be checked and is
  skipped.
- **Defined**: the rows in the files the modinfo lists under UpdateText, and
  the game's own text from `Debug/localization-copy.sqlite`.
- **--prefix**: a dump taken with the mod loaded holds the mod's own keys, so
  a key the mod no longer defines looks defined. `--prefix LOC_MYMOD` leaves
  the game's keys starting with it out.

## dbdiff

```bash
civ7lab dbdiff before-patch.sqlite after-patch.sqlite
civ7lab dbdiff before-patch.sqlite after-patch.sqlite --table Units --rows 50
```

Compares two game databases and lists what changed in each table. The usual
use is a game patch: copy `Debug/gameplay-copy.sqlite` before the patch, let
the game write a new one after it, and compare the two. Rows are paired by
the table's primary key:

```
Units: 1 changed, 1 removed
  ~ UNIT_SCOUT: BaseMoves 2 -> 3
  - UNIT_SANDBOX
```

New and removed columns and tables are listed too. `--json` gives every
change.

## modinfo

```bash
civ7lab modinfo path/to/mod
civ7lab modinfo path/to/mod --age AGE_EXPLORATION
```

Lists what the mod loads in each age, in apply order, with each group's
LoadOrder, and its UI scripts. It also lists:

- **Commented-out items**: files inside XML comments, which the game skips.
- **Ambiguous criteria**: `AgeAtOrBefore` and `AgeAtOrAfter` can be read
  either way round. civ7lab reads them literally and says so. Explicit
  `AgeInUse` rows remove the doubt.

## jscheck

```bash
civ7lab jscheck path/to/mod
```

Checks each UI script against the modinfo that serves it. It reports:

- **Syntax errors**: each with its line number.
- **Unlisted scripts**: on disk, but in no ActionGroup, so never loaded.
- **Unserved imports**: an `import` of a mod script the modinfo does not
  list. The importing script fails to load.
- **console.log**: it does not reach `UI.log`. Use `console.error`.
- **Missing build stamp**: without one, `UI.log` cannot show which build ran.
  See [build stamps](runs.md#build-stamps).

Finding syntax errors needs the tree-sitter parser, which the install in the
README includes as `[jscheck]`. Without it, every other check still runs.
