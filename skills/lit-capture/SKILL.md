---
name: lit-capture
description: Capture scholarly papers met in research conversations into this project's .lit corpus, triage the capture inbox, and answer literature questions from the local corpus before re-searching. Use when a paper with a DOI, arXiv id, OpenAlex W-id, or exact title plus author or year comes up and looks worth keeping, when the user asks to capture, save, or file a paper, or when a literature question may already be answered by the corpus. Not for casual mentions the user has not asked to keep.
---

<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# lit-capture

Run this as a procedure. The corpus lives in `.lit/` at the root of the current
project repo and is git-tracked there. The script `lit_fetch.py` is the only
component that touches the network, and it talks to OpenAlex only. Everything
else is agent reading and writing.

Invoke the script by its installed path so no PATH setup is needed:

```bash
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --status
```

Common flags: `--dir <path>` (corpus root, default `.lit`; always run from the
repo root), `--api-key <key>` (default env `OPENALEX_API_KEY`).

## Prerequisites

- Python 3.9+ (standard library only; no pip packages) reachable as `python`.
- Network access to `api.openalex.org`. Singleton DOI and W-id lookups are
  free; title searches, batches, and inbox triage draw on a daily budget, so
  set `OPENALEX_API_KEY` (from OpenAlex) for the full budget.
- The script ships inside this skill folder. The default install is ZCode
  (`~/.zcode/skills/lit-capture/lit_fetch.py`); on other hosts substitute
  that host's installed path (for example
  `~/.claude/skills/jgs/lit-capture/lit_fetch.py`).

## When to use

A paper enters the conversation with enough identity to fetch (DOI, arXiv id,
W-id, or exact title plus author and/or year) and looks worth keeping. Capture
takes under a minute and never leaves the chat.

## Extract, do not fetch blindly

Scan the conversation for DOIs (`10.xxxx/...`), arXiv ids, OpenAlex W-ids, and
full titles. This is agent-driven reading, not code-based NLP; the script never
parses prose. Dedupe against the corpus before capture: read the generated
`.lit/SKILL.md` for counts and last-synced, then grep `papers/` for the
identifiers you found.

## Capture offline first

Append one JSONL line per item to `.lit/inbox.jsonl`. The `ref` grammar is
exactly one of:

```json
{"ref": "doi:10.1038/nature12373"}
{"ref": "W2741809807"}
{"ref": "arxiv:2401.12345", "title": "<verbatim title>"}
{"ref": "title:<verbatim title>"}
```

Title-form and arxiv-form entries also carry `"title"` (verbatim), plus
optional `"author"` (surname) and `"year"`. Every entry carries `"note"` (why
it came up) and `"added_at"` (ISO timestamp). This works with no network and
survives the session.

## Fetch now when online

With user consent or standing habit, run the script per item, or as one batch:

```bash
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --ids "W2741809807|W2100837265"
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --doi 10.1038/nature12373
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --title "Exact Title" --author Surname --year 2024
```

Report the `written=N skipped=M failed=K` summary block to the user. Then stage
the capture: `git add .lit`.

Title searches and batches are budgeted calls; without an API key the script
warns and draws on the small keyless daily budget. Singleton DOI and W-id
lookups are free.

## Findings stub (optional)

For papers worth a note, write `findings/<YYYY>-<slug>.md` from this template:

```markdown
# <paper title>

- W-id: <W-id>
- Captured: <YYYY-MM-DD>, why: <one line on why it came up>
- Claim worth remembering: <one sentence>
```

Prose in findings follows the Written Prose Standard: lead with the finding,
no em dashes, no filler.

## Triage

Periodically run:

```bash
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --inbox
```

Title-form and arxiv-form entries resolve through their `"title"` field
(arXiv entries get theirs from the paper as captured); supply `"author"` and
`"year"` to disambiguate. Drop entries no longer wanted by deleting their
lines. Failures stay queued with their reason in `last_error`; fix the entry
or delete it, then re-run.

## Query the corpus

Read `.lit/SKILL.md` first each session (counts, recipes, last-synced), then
answer literature questions from `papers/` and `graph/edges.jsonl` before
re-searching. The index carries copy-pasteable recipes: title grep, boundary
ID extraction, edges per paper, papers citing a given W-id.

## Limits

Abstracts are often null (OpenAlex stores them only as an inverted index and
only for roughly half of works). Use the corpus for identity, graph, and
retrieval, not as a full-text store. `referenced_works` is lossy relative to
printed reference lists; treat the graph as biased, not authoritative.
