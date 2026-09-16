# jgs-lit-memory

`lit_fetch.py` captures scholarly papers from OpenAlex into a per-project
`.lit/` corpus: one normalized JSON record per paper, citation edges between
them, optional findings notes, and a low-friction inbox for offline capture.
The companion `lit-capture` skill drives the capture procedure from research
conversations, so the next session queries the local corpus instead of
re-searching the same papers.

## Install

Copy, do not link, matching the existing skill mirror pattern. Run from the
repo root:

```bash
mkdir -p "$HOME/.zcode/skills/lit-capture" "$HOME/.claude/skills/lit-capture" "$HOME/.agents/skills/lit-capture"
cp skills/lit-capture/SKILL.md lit_fetch.py "$HOME/.zcode/skills/lit-capture/"
cp skills/lit-capture/SKILL.md lit_fetch.py "$HOME/.claude/skills/lit-capture/"
cp skills/lit-capture/SKILL.md lit_fetch.py "$HOME/.agents/skills/lit-capture/"
```

Edits happen in this repo, then get re-copied to the three mirrors. The skill
invokes the script by the `.zcode` absolute path, so all three mirrors stay
interchangeable and no PATH setup is needed.

## Usage

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
`OPENALEX_API_KEY`), `--seed`, `--author`, `--year`.

Exit codes: 0 success or already present, 1 any failure, 2 usage error.

## Corpus layout

`.lit/` lives in the project that produced it and is git-tracked there:

```
.lit/
  papers/<W-id>.json      one normalized record per paper
  graph/edges.jsonl       {"source": citing W-id, "target": cited W-id}, one per line
  graph/aliases.json      {"alias W-id": "canonical W-id"} recorded on 301 merges
  findings/<year>-<slug>.md  optional human notes
  inbox.jsonl             offline capture queue
  SKILL.md                generated corpus contract; never hand-edited
```

All writes are atomic (temp file plus `os.replace`). A crash mid-batch leaves
completed records on disk and never a half-written file. Edges are a
full-rewrite idempotent union, so the next successful run heals partial runs.

## Limits

- Abstracts come only from `abstract_inverted_index`, are null on roughly 40
  to 55 percent of works, and keep their trailing junk verbatim. The corpus is
  for identity, graph, and retrieval, not full text.
- `referenced_works` is lossy relative to printed reference lists; the graph
  is biased toward DOI-matchable citations.
- OpenAlex metadata is CC0. Reconstructed abstracts are for local corpus use.
- Without an API key, budgeted calls (batches, title searches, inbox triage
  with search entries) draw on a small keyless daily budget and the script
  warns first. Singleton DOI and W-id lookups are free.

## Testing

```bash
python test_lit_fetch.py        # offline checks; the network is faked
python lit_fetch.py --check     # live smoke test of endpoint forms
```

Set `OPENALEX_API_KEY` for the full daily budget. Get a key from OpenAlex.
