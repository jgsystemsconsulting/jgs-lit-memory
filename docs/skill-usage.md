<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Using jgs-lit-memory

## Prerequisites

- Python 3.9+ on PATH (standard library only; no pip packages).
- Network access to `api.openalex.org`. Singleton DOI and W-id lookups are
  free. Title searches, batches, and inbox triage draw on a daily budget;
  set `OPENALEX_API_KEY` (get a key from OpenAlex) for the full budget.
- A host that can load Agent Skills (`SKILL.md`). ZCode is the default
  install target. Claude Code, Copilot CLI, OpenClaw, and Codex read the
  folder natively; Gemini and Cursor use the installer transform. See
  [other-agents.md](other-agents.md).
- A project repo you run research conversations in. The `.lit/` corpus lives
  at that repo's root and is git-tracked there.

## Install

```bash
python install.py                 # ZCode, flat ~/.zcode/skills/lit-capture/
python install.py --dry-run       # preview, write nothing
python install.py --agent claude  # namespaced ~/.claude/skills/jgs/lit-capture/
python install.py --agent all     # every user-global agent
python install.py --list-agents
```

Restart the agent session so it discovers the skill.

## Invoke / first run

The `lit-capture` skill is conversational, not a slash command. It triggers
when a paper comes up in a research conversation with enough identity to
fetch (DOI, arXiv id, OpenAlex W-id, or exact title plus author and/or year)
and looks worth keeping, or when you ask to capture, save, or file a paper.

```text
Capture this one: 10.1038/nature12373
Save that arXiv paper, 2401.12345, "Attention Is All You Need"
What do we have on citation graph bias? Check the corpus first.
```

The skill scans the conversation for identifiers, dedupes against the
corpus, then either appends JSONL lines to `.lit/inbox.jsonl` (offline
capture) or runs `lit_fetch.py` (online capture) with your consent. All
script invocations go through the installed skill folder, for example:

```bash
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --status
```

## Resolution verbs

One resolution verb per invocation.

| Invocation | Behavior |
|---|---|
| `--doi <doi>` | Singleton capture by DOI (free). seed=true, source="capture". |
| `--openalex <W-id>` | Singleton capture by W-id (free). Same write semantics. |
| `--arxiv <id> --title <t>` | No arXiv lookup exists in OpenAlex; resolves through the verified title search. Bare `--arxiv` is a usage error. |
| `--title <t> [--author <surname>] [--year <yyyy>]` | Budgeted search with client-side verification. Near-misses print as candidates and write nothing. |
| `--ids "W1\|W2\|..."` | Batch fetch, 100 per call, skips existing records. seed=false, source="fetch"; `--seed` overrides. |
| `--inbox` | Triage `.lit/inbox.jsonl`: dedupe, resolve, rewrite the queue once. Failures stay queued with their reason. |
| `--status` | Corpus summary. Read-only. |
| `--check` | Live smoke test of the four endpoint forms. |

Common flags: `--dir <path>` (default `.lit`), `--api-key <key>` (default env
`OPENALEX_API_KEY`), `--seed`, `--author`, `--year`. Exit codes: 0 success or
already present, 1 any failure, 2 usage error.

## Corpus layout

`.lit/` lives in the project that produced it and is git-tracked there:

```
.lit/
  papers/<W-id>.json      one normalized record per paper
  graph/edges.jsonl       {"source": citing W-id, "target": cited W-id}, one per line
  graph/aliases.json      {"alias W-id": "canonical W-id"} recorded on 301 merges
  findings/<YYYY>-<slug>.md  optional human notes
  inbox.jsonl             offline capture queue
  SKILL.md                generated corpus contract; never hand-edited
```

All writes are atomic (temp file plus `os.replace`). A crash mid-batch
leaves completed records on disk and never a half-written file. Edges are a
full-rewrite idempotent union, so the next successful run heals partial runs.

## Limits

- Abstracts come only from `abstract_inverted_index`, are null on roughly 40
  to 55 percent of works, and keep their trailing junk verbatim. The corpus
  is for identity, graph, and retrieval, not full text.
- `referenced_works` is lossy relative to printed reference lists; the graph
  is biased toward DOI-matchable citations.
- OpenAlex metadata is CC0. Reconstructed abstracts are for local corpus
  use.

Skill index: [SKILLS.md](../SKILLS.md).
