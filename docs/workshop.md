# Workshop tags and description

`civ7lab workshop` changes a published item's tags or description, the way
the SDK's Workshop Uploader does, and nothing else: the title, content and
visibility stay as they are.

## Tags

Under Proton, the uploader will not tick its tag checkboxes, and Steam's web
page has no tag editor for this game.

```bash
civ7lab workshop tags 1234567890                              # show the tags
civ7lab workshop tags 1234567890 UI --dry-run                 # show now and new
civ7lab workshop tags 1234567890 "Game Setup" "Gameplay Tweaks"
```

The list you give is the whole new list. `Mod` is always kept, since without
it the item drops out of the Mod filter. Case does not matter, and commas work
as separators. A name outside the uploader's lists is refused, and the error
lists the valid ones.

A submit changes a public page, so dry-run first.

## Description

```bash
civ7lab workshop description 1234567890 workshop/description.txt --dry-run
civ7lab workshop description 1234567890 workshop/description.txt
```

Replaces the item's description with the file's text, in Steam's markup, and
changes nothing else. It shows the change as a diff first, and does nothing
if the two already match. Steam allows at most 8000 characters.

This keeps the Workshop page in step with a `description.txt` kept in the
mod's repository.

## Requirements

- **Steam**: running, and logged on as the item's creator. The command checks
  and refuses otherwise.
- **Steam's API library**: on Linux the Steam runtime's `libsteam_api.so`,
  under the Steam folder's `steamrt64/`. On Windows the `steam_api64.dll` the
  game ships in `Base\Binaries\Win64`. No SDK download is needed.

It submits as the SDK's app, 3688890, as the uploader does, and falls back to
the game's, 1295660. Afterwards it reads the tags or description back from
Steam's public web API, which can lag a minute behind.
