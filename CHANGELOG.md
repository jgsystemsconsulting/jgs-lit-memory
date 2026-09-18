<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Changelog

Single-source history for jgs-lit-memory. Tags are three-component semver
(`vMAJOR.MINOR.PATCH`).

## [1.1.0] - 2026-09-18

Paper analysis-brief sidecars. On first successful paper write, the corpus
gains a `pending` brief at `.lit/briefs/<W-id>.json`. The chat agent drains
the enrichment queue and submits validated JSON; the script owns stubs,
validation, stamps, and derived `status` / `basis`. No LLM calls in Python.

- Brief schema, presence rules, stub factory, and script-derived `status` /
  `basis` (stdlib only, single-file `lit_fetch.py`)
- Claim and brief-level validation with atomic writes; failed writes leave
  the previous brief untouched
- Automatic pending stub on first paper write; stub failure surfaces without
  undoing the paper record
- Alias remap for briefs on both 301 merge sites
- Read verbs: `--enrich-pending`, `--brief-status`, `--brief-check`
- Write verbs: `--brief-write`, `--brief-restub`, `--human` (merge-only human
  block unless `--human`)
- Skill procedure and usage docs for the enrichment loop

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
