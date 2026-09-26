"""Parse Codex / OpenCode ``apply_patch`` text into per-file Write/Edit/Delete actions."""
from __future__ import annotations


def parse_patch(text: str) -> list[dict]:
    """Returns [{op: add|update|delete, path, content, old, new, move_to}]."""
    files: list[dict] = []
    cur: dict | None = None
    for line in (text or "").splitlines():
        if line.startswith("*** Add File: "):
            cur = {"op": "add", "path": line[14:].strip(), "plus": [], "minus": []}
            files.append(cur)
        elif line.startswith("*** Update File: "):
            cur = {"op": "update", "path": line[17:].strip(), "plus": [], "minus": []}
            files.append(cur)
        elif line.startswith("*** Delete File: "):
            files.append({"op": "delete", "path": line[17:].strip(), "plus": [], "minus": []})
            cur = None
        elif line.startswith("*** Move to: ") and cur is not None:
            cur["move_to"] = line[13:].strip()
        elif line.startswith(("*** Begin Patch", "*** End Patch", "*** End of File")):
            continue
        elif cur is not None:
            if line.startswith("+"):
                cur["plus"].append(line[1:])
            elif line.startswith("-"):
                cur["minus"].append(line[1:])
    out = []
    for f in files:
        out.append({"op": f["op"], "path": f["path"], "content": "\n".join(f["plus"]), "old": "\n".join(f["minus"]),
                    "move_to": f.get("move_to")})
    return out


def patch_to_actions(text: str) -> list[tuple[str, dict]]:
    acts: list[tuple[str, dict]] = []
    for f in parse_patch(text):
        if f["op"] == "add":
            acts.append(("Write", {"file_path": f["path"], "content": f["content"]}))
        elif f["op"] == "update":
            acts.append(("Edit", {"file_path": f["path"], "old_string": f["old"], "new_string": f["content"]}))
            if f.get("move_to"):
                acts.append(("Write", {"file_path": f["move_to"], "content": f["content"]}))
        elif f["op"] == "delete":
            acts.append(("Bash", {"command": f"rm {f['path']!r}"}))
    return acts
