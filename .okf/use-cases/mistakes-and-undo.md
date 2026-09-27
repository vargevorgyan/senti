---
type: Use Case
title: Destructive mistakes and one-click undo
description: An agent deletes or overwrites the wrong files; personal folders are protected outright and project changes can be restored.
tags: [use-case, individual]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-27T09:00:00Z' }
sources:
  - id: kb
    resource: /.okf (architecture, research, business sections)
    title: Senti knowledge base — implemented behaviour and test results
    author: claude-code/2.1.283
---

# Who

Anyone running an agent in auto/YOLO mode.

# Situation

The agent "cleans up" with `rm -rf ~/Documents/old` or runs `git reset --hard` over uncommitted work.

# What Senti does

1. Deleting the home folder or personal folders (Documents, Desktop, Pictures…) is a **hard block**, including via globs (`~/*`), wrappers (`timeout`, `nice`) and scripts that call `shutil.rmtree`.
2. Allowed destructive actions inside a project (`rm`, `mv`, overwrites, `git reset --hard`, `git clean`) get an **APFS-clone snapshot** first (instant, no extra space).
3. `senti undo list` / `senti undo restore <id>` brings the files back.

# Features involved

Hard rules, undo snapshots.

# How well it is verified

**Tested** (automated: snapshot + restore round-trip; personal-folder block cases).

# Limits

Snapshots cover files touched through checked actions; changes made inside long-running programs aren't snapshotted.

# Related

- [decision engine](/architecture/decision-engine.md)
