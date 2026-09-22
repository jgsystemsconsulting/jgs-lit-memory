<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Changelog

Single-source history for jgs-lit-memory. Tags are three-component semver
(`vMAJOR.MINOR.PATCH`).

## [Unreleased]

## [1.2.1] - 2026-09-22

Gemini installs now run. The extension destination gains `lit_fetch.py`
beside `SKILL.md`, the install docs state per-host reality, and CI fails if
the script ever drops out of the Gemini path again. Brief checking gets
harder to fool and the marketplace blurbs match what ships.

- `install_gemini` copies `lit_fetch.py` into the extension dest, so
  `--agent gemini` and `--agent all` produce a runnable extension
  (`GEMINI.md`, `SKILL.md`, `gemini-extension.json`, `lit_fetch.py`)
- README, `docs/other-agents.md`, and `docs/skill-usage.md` now describe
  native whole-folder, Gemini four-file extension, and Cursor rule-only
  installs, including the installed Gemini script path
- CI packaging smoke asserts the four-file Gemini layout under
  `.tmp-install-check-gemini/jgs-lit-capture/`
- `--brief-check` fails when a brief's `id` does not equal its
  `briefs/<stem>.json` filename; the comparison uses the file stem, never
  the alias-resolved label, and single-mode lookup uppercases the resolved
  id; `docs/skill-usage.md` names the new check
- SKILLS.md index row and the five plugin/marketplace descriptions name the
  three-layer corpus (records, citation edges, analysis briefs)

## [1.2.0] - 2026-09-22

OpenAlex-unavailable fallback. The lit-capture skill now prescribes what to
do when OpenAlex is unreachable, rate-limited, or out of budget: diagnose
with `--check`, suggest a free OpenAlex API key, and fetch the paper
directly from the open web until OpenAlex answers again. Corpus identity
stays intact: no invented W-ids, offline inbox queue in the meantime,
idempotent re-run on recovery.

- New "When OpenAlex is unavailable" section in the lit-capture skill:
  `--check` diagnosis, API-key suggestion, direct web fallback (arXiv PDF,
  arXiv Atom metadata, DOI landing page, Crossref), offline inbox queue
  instead of hand-written records, `--inbox` plus `--enrich-pending` on
  recovery
- Favicon: the landing page ships `docs/favicon.svg` (three-layer mark on a
  paper badge) linked from the page head, replacing the empty `data:` stub.
  Meets `RR-B-20` as of release-repo-standard 1.15
- lit_fetch stops inbox and title runs when a response carries
  `x-ratelimit-remaining: 0`; completed writes stand, remaining work fails
  with a budget reason
- lit_fetch redacts the `api_key` query value in BackoffExhausted messages,
  so failure text is safe to print and store in the corpus
- Docs: README mirrors the reader contract, the landing page leads with the
  three-layer product (verb table, limits), skill-usage gains an OpenAlex
  API key setup section; maintainer-only trees (docs/superpowers, .zcode)
  are gitignored

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
