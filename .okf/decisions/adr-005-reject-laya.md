---
type: Decision
title: "ADR-005: Reject Laya as the command judge"
description: "Laya was rejected for command and access limiting because it missed dangerous actions, gave no explanations and was slower on M1 than claimed."
tags: [decision, laya, rejected]
status: stable
generated: { by: claude-code/2.1.283, at: '2026-09-26T18:30:00Z' }
sources:
  - id: session
    resource: claude-code session 973dd678-f568-4b80-aeca-b6d8963be82d (2026-09-26)
    title: Ideathon planning session
    author: claude-code/2.1.283
---

# Decision
Do not use Laya. It is a classifier (no enforcement), zero-shot accuracy on agent actions was 44–49%, it let the hidden-exfil script through,
and ran 125–415 ms on M1. See [Laya evaluation](/research/laya-evaluation.md).
