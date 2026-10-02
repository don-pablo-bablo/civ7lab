"""`civ7lab diff`: compare two snapshots as a flat list of changed paths.

Items in a list are matched by identity where they have one: a tile by x and
y, a building by type. One building added mid-list is then one change rather
than a change to every later entry.
"""

from __future__ import annotations

from dataclasses import dataclass

# Keys that identify an item in a list, most specific first.
IDENTITY_KEYS = [("x", "y"), ("type",), ("building",), ("name",), ("tag", "type"), ("label",)]


@dataclass
class Change:
    path: str
    before: object
    after: object

    @property
    def kind(self) -> str:
        if self.before is None and self.after is not None:
            return "added"
        if self.after is None and self.before is not None:
            return "removed"
        return "changed"

    def __str__(self) -> str:
        if self.kind == "added":
            return f"+ {self.path} = {_short(self.after)}"
        if self.kind == "removed":
            return f"- {self.path} = {_short(self.before)}"
        return f"~ {self.path}: {_short(self.before)} -> {_short(self.after)}"


def _short(value, limit: int = 80) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _identity(item):
    if not isinstance(item, dict):
        return None
    for keys in IDENTITY_KEYS:
        if all(key in item for key in keys):
            return tuple((key, item[key]) for key in keys)
    return None


def compare(before, after, path: str = "") -> list[Change]:
    changes: list[Change] = []

    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            child = f"{path}.{key}" if path else str(key)
            if key not in before:
                changes.append(Change(child, None, after[key]))
            elif key not in after:
                changes.append(Change(child, before[key], None))
            else:
                changes.extend(compare(before[key], after[key], child))
        return changes

    if isinstance(before, list) and isinstance(after, list):
        before_keyed = {_identity(item): item for item in before if _identity(item)}
        after_keyed = {_identity(item): item for item in after if _identity(item)}
        if before_keyed and after_keyed:
            for key in sorted(set(before_keyed) | set(after_keyed), key=repr):
                label = ",".join(f"{name}={value}" for name, value in key)
                child = f"{path}[{label}]"
                if key not in before_keyed:
                    changes.append(Change(child, None, after_keyed[key]))
                elif key not in after_keyed:
                    changes.append(Change(child, before_keyed[key], None))
                else:
                    changes.extend(compare(before_keyed[key], after_keyed[key], child))
            # Anything without an identity falls back to position.
            rest_before = [item for item in before if not _identity(item)]
            rest_after = [item for item in after if not _identity(item)]
            for index in range(max(len(rest_before), len(rest_after))):
                child = f"{path}[{index}]"
                changes.extend(
                    compare(
                        rest_before[index] if index < len(rest_before) else None,
                        rest_after[index] if index < len(rest_after) else None,
                        child,
                    )
                )
            return changes
        for index in range(max(len(before), len(after))):
            child = f"{path}[{index}]"
            changes.extend(
                compare(
                    before[index] if index < len(before) else None,
                    after[index] if index < len(after) else None,
                    child,
                )
            )
        return changes

    if before != after:
        changes.append(Change(path, before, after))
    return changes


def summarise(changes: list[Change], limit: int = 60) -> str:
    if not changes:
        return "no differences"
    counts = {"added": 0, "removed": 0, "changed": 0}
    for change in changes:
        counts[change.kind] += 1
    head = (
        f"{len(changes)} difference(s): {counts['changed']} changed, "
        f"{counts['added']} added, {counts['removed']} removed"
    )
    body = "\n".join(str(change) for change in changes[:limit])
    if len(changes) > limit:
        body += f"\n... and {len(changes) - limit} more"
    return head + "\n" + body
