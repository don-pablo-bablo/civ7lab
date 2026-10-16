# Workshop tags, description and uploads

`civ7lab workshop` changes a published item's tags or description, or uploads
a new version of its mod with release notes, the way the SDK's Workshop
Uploader does. Nothing else changes: the title, preview image and visibility
stay as they are.

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

## Upload

```bash
civ7lab workshop upload 1234567890 mod/my-mod --note notes.txt --dry-run
civ7lab workshop upload 1234567890 mod/my-mod --note notes.txt
```

Uploads the folder as the item's new version, with the file's text as its
release notes on the item's Change Notes page. The notes are in Steam's
markup, at most 8000 characters. Without `--note` the version goes up with
none.

The folder is the mod's own: once subscribed, the game finds the mod by the
`.modinfo` at the top of the item, so a folder without exactly one there is
refused. So is a modinfo whose version starts with 0, which the game lists
but never loads. Every file in the folder is uploaded, so the dry run lists
them all.

A dry run shows the mod's id and version, the files and the notes, and
submits nothing. The upload shows its progress, then waits for the web API's
update time to move.

## Requirements

- **Steam**: running, and logged on as the item's creator. The command checks
  and refuses otherwise.
- **Steam's API library**: on Linux the Steam runtime's `libsteam_api.so`,
  under the Steam folder's `steamrt64/`, or else the one the game ships in
  `Base/Binaries/linux`, which Steam's update of 2026-10-15 left as the only
  one. On Windows the `steam_api64.dll` the game ships in
  `Base\Binaries\Win64`. No SDK download is needed.

It submits as the SDK's app, 3688890, as the uploader does, and falls back to
the game's, 1295660. Afterwards it reads the tags or description back from
Steam's public web API, which can lag a minute behind.
