<!-- Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE. -->
<!-- SPDX-License-Identifier: MIT -->

# Using jgs-lit-memory

## Prerequisites

- Python 3.9+ on PATH (standard library only; no pip packages).
- Network access to `api.openalex.org`. Singleton DOI and W-id lookups are
  free. Title searches, batches, and inbox triage draw on a daily budget;
  set `OPENALEX_API_KEY` for the full budget (setup:
  [The OpenAlex API key](#the-openalex-api-key)).
- A host that can load Agent Skills (`SKILL.md`). ZCode is the default
  install target. Claude Code, Copilot CLI, OpenClaw, and Codex read the
  folder natively. Gemini gets a small extension install that still includes
  `lit_fetch.py`. Cursor uses the installer transform (rule file only). See
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

## The OpenAlex API key

The script runs without a key. Singleton DOI and W-id lookups are free, and
budgeted calls (title searches, batches, inbox triage with search entries)
draw on a small keyless daily budget, with a warning printed before the first
budgeted call. A key raises the daily budget tenfold and lets you track
usage.

To get and install one:

1. Sign in at [openalex.org](https://openalex.org) (email or ORCID; the
   account is free).
2. Copy your key at [openalex.org/settings/api](https://openalex.org/settings/api).
3. Set it as an environment variable named `OPENALEX_API_KEY`:

   ```bash
   setx OPENALEX_API_KEY "<key>"    # Windows: persistent user variable; new processes only
   export OPENALEX_API_KEY="<key>"  # macOS/Linux: add the line to .bashrc or .zshrc to persist
   ```

Processes already running keep the environment they started with, so open a
new terminal or restart the agent session afterwards. Then verify:

```bash
python "$HOME/.zcode/skills/lit-capture/lit_fetch.py" --check
```

`--check` smoke-tests all four endpoint forms with the key active. Your daily
usage is visible at [openalex.org/settings/usage](https://openalex.org/settings/usage).

The key is optional per project and per machine: set it once per account
where you research, and every repo running `lit_fetch.py` picks it up. It is
read from the `OPENALEX_API_KEY` environment variable or accepted by the
`--api-key` flag, and it is never written into the corpus. The key doubles as
your openalex.org sign-in credential, so treat it like a password: never
commit it, and expect rotating it (Settings, API key) to end other sessions
immediately. See [SECURITY.md](../SECURITY.md).

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
| `--enrich-pending` | List briefs awaiting enrichment: `pending` and `partial` as JSONL rows; unreadable files are labeled `invalid`. Read-only. |
| `--brief-status [W-id]` | Brief counts by status and basis; with an id, print that brief's JSON. Read-only. |
| `--brief-check [W-id]` | Validate one brief or all (schema, id vs filename, claim graph, derived fields). Exit 1 when invalid. |
| `--brief-write --id <W-id> --file <payload.json> [--human]` | Validate and atomically write a brief. Replaces the `agent` block, keeps `human` unless `--human`, derives `status` and `basis`. |
| `--brief-restub --id <W-id>` | Reset the brief's agent shell and enrich stamps to pending. Keeps `human`. |

Common flags: `--dir <path>` (default `.lit`), `--api-key <key>` (default env
`OPENALEX_API_KEY`), `--seed`, `--author`, `--year`. Exit codes: 0 success or
already present, 1 any failure (including an invalid `--brief-check` result
or a rejected `--brief-write`), 2 usage error.

## Paper briefs

First load of a paper also creates `.lit/briefs/<W-id>.json`, a `pending`
stub the chat agent fills by draining the enrichment queue. The Python
script never calls an LLM; it stubs, lists, validates, and atomically
writes. The agent drafts brief content (overview, claims with an in-paper
`supports` / `contradicts` graph, methods, limits, why it matters) and
submits it through `--brief-write`; `status` and `basis` are derived by the
script and never taken from the payload. `human` fields are merge-only: a
normal write preserves them, and `--human` replaces them only when the user
dictated human notes this turn. After updating this repo, re-run
`python install.py` so installed skill copies pick up the new verbs.

## Corpus layout

`.lit/` lives in the project that produced it and is git-tracked there:

```
.lit/
  papers/<W-id>.json      one normalized record per paper
  briefs/<W-id>.json      analysis sidecar per paper (agent-authored, script-validated)
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
