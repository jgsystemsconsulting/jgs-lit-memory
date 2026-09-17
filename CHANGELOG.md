<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Changelog

Single-source history for jgs-lit-memory. Tags are three-component semver
(`vMAJOR.MINOR.PATCH`).

## [1.0.0] - 2026-09-17

First public release. `lit_fetch.py` captures scholarly papers from OpenAlex
into a per-project `.lit/` corpus, driven by the `lit-capture` skill from
research conversations.

- One normalized JSON record per paper (`papers/<W-id>.json`), citation edges
  between them (`graph/edges.jsonl`), alias remap for merged works, optional
  findings notes, and an offline capture inbox
- Resolution verbs: DOI, OpenAlex W-id, arXiv id through verified title
  search, budgeted title search with client-side verification, batch fetch
  (100 per call), inbox triage, corpus status, endpoint smoke check
- Atomic corpus writes (temp file plus `os.replace`); a crash mid-batch
  leaves completed records and no half-written files; edges are an idempotent
  full-rewrite union that heals partial runs
- OpenAlex budget guard with exponential backoff and keyless daily-budget
  warnings; singleton DOI and W-id lookups are free
- Offline test suite (stdlib only, network faked)
- Release Repo Standard (Base + RR-S): LICENSE, SECURITY.md, installers,
  host manifests, GitHub Pages landing page, CI integrity gate
- Licence-enquiry page linked from the landing page, README, and GitHub
  Release notes
- Paste-ready agent install prompt in the README
