# Paper briefs design

Date: 2026-09-18  
Status: approved for planning  
Repo: jgs-lit-memory

## Problem

`.lit/papers/<W-id>.json` holds bibliographic metadata (OpenAlex-shaped: id, doi, title, authors, abstract, topics, refs, capture stamps). Citation structure lives in `.lit/graph/edges.jsonl`. Agents can answer "do we have this paper?" and "what cites what?" They cannot answer "what does this paper claim?", "how was it tested?", or "why does it matter here?" without re-reading the abstract or the web every time.

Optional `.lit/findings/*.md` notes are freeform human diary, not a structured query surface.

## Goal

On first successful load of a paper into the corpus, default to a **full analysis brief** the agent can use for rationale. Briefs are first-class JSON, offline-safe via stubs, and layered so human notes are never auto-wiped.

## Non-goals (v1)

- LLM API calls inside Python
- PDF download, OCR, or fulltext pipeline in-repo
- Cross-paper claim-to-claim graphs on first load
- Auto-generated `findings/*.md` from briefs
- Embeddings / vector search
- Orphan briefs with no matching paper
- Automatic `stale` detection beyond what write/restub already allow

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| When | Default enrich on first load (not opt-in later-only) |
| Depth | Full brief (overview, claims, methods/tests, limits, why it matters, related-in-corpus, open questions, enrichment metadata) |
| Offline | Stub brief with `status: pending` at paper write; fill when agent drains queue |
| Storage | Sidecar `.lit/briefs/<W-id>.json` (bib stays fetch-owned) |
| Claims | Argument-graph fields (`supports` / `contradicts`); **in-paper only** on first load |
| Text basis | Abstract by default; fulltext when already available (local or readable OA); every claim records `basis` |
| Ownership | `agent` block replaceable on re-enrich; `human` block merge-only unless explicit `--human` |
| Trigger | Successful paper write ensures stub; separate `--enrich-pending` queue drain |
| Writer | Chat agent authors brief JSON; script stubs, lists, validates, atomic-writes |

## Layout

```
.lit/
  papers/<W-id>.json     # bib; lit_fetch owns
  briefs/<W-id>.json     # analysis sidecar; agent owns agent block
  graph/edges.jsonl      # citation edges (unchanged)
  findings/*.md          # optional human diary (unchanged; not required)
```

Brief `id` equals paper id and filename stem. v1 rejects writes when the paper file is missing.

## Lifecycle

1. Capture/fetch writes or updates `papers/<id>.json` as today.
2. On successful paper write, `ensure_brief_stub(id)`: if brief missing, create pending skeleton; if present, leave untouched.
3. Operator or skill runs `--enrich-pending` and drains the queue (recommended cap: a few ids per turn; remainder stay queued).
4. Agent reads paper JSON (and fulltext when available), drafts the brief, submits via `--brief-write`.
5. Script validates, atomically writes, preserves `human` unless `--human`, sets `enriched_at` / `enrichment_source`, derives `status`.
6. Re-enrich replaces `agent` only. Basis upgrade (abstract to fulltext) is an allowed reason to refresh the agent block.
7. `--brief-restub --id` resets the agent shell to pending and keeps `human`.

Offline inbox rows stay thin until fetch materializes the paper and stub.

## Schema (`schema_version: 1`)

```json
{
  "id": "W....",
  "schema_version": 1,
  "status": "pending|partial|ready|stale",
  "basis": "none|abstract|fulltext|mixed",
  "enriched_at": null,
  "enrichment_source": null,
  "paper_captured_at": null,

  "agent": {
    "overview": "",
    "claims": [
      {
        "id": "c1",
        "text": "",
        "type": "contribution|finding|method|limit|assumption|other",
        "support": "",
        "basis": "abstract|fulltext|human",
        "confidence": "low|med|high",
        "page": null,
        "section": null,
        "supports": ["c2"],
        "contradicts": []
      }
    ],
    "methods_tests": "",
    "limits": "",
    "why_it_matters": "",
    "related_in_corpus": [],
    "open_questions": [],
    "notes": ""
  },

  "human": {
    "overview": null,
    "claims": [],
    "methods_tests": null,
    "limits": null,
    "why_it_matters": null,
    "open_questions": [],
    "notes": null
  }
}
```

### Status rules

- **pending:** stub or empty agent shell; `basis: none` until first real fill attempt.
- **partial:** agent filled what abstract (or thin source) allows; overview and at least one claim should exist when leaving pending; methods/tests may be thin; `basis` is `abstract` or `mixed`.
- **ready:** non-empty overview; at least one claim with `text`; `methods_tests`, `limits`, and `why_it_matters` present (short is fine); every claim has `type`, `confidence`, and `basis`; `supports` / `contradicts` only reference claim ids in this brief.
- **stale:** reserved; not auto-set in v1 write path.

### Claim rules

- Claim ids unique within the brief.
- `supports` / `contradicts` targets must exist in the same brief or validation fails.
- No invented page numbers. Unknown `page` / `section` stay null.
- Abstract-only fills should prefer `confidence` of `low` or `med`.
- First load does not create cross-paper claim links. Schema does not need global claim ids in v1.

### `related_in_corpus`

Array of `{ "id": "W...", "note": "..." }` pointing at other **papers** (not claim ids). Best-effort from local papers and citation edges. Empty array is valid.

### Merge view (query time)

Agents prefer `human.X` when non-null / non-empty, else `agent.X`. No merged file on disk in v1.

### Stub shape

`id`, `schema_version: 1`, `status: pending`, `basis: none`, null timestamps/source, empty agent shell, empty human defaults. No placeholder fake claims.

## CLI surface (`skills/lit-capture/lit_fetch.py`)

One entrypoint. Fetch verbs stay bib-focused and gain stub ensure.

| Verb | Role |
|------|------|
| Existing fetch/inbox/status/check | Unchanged bib behavior; successful paper write calls `ensure_brief_stub` |
| `--enrich-pending` | List `pending` and `partial` briefs (labeled); read-only; empty list is success |
| `--brief-status [id]` | Counts by status and basis; optional single-id detail |
| `--brief-check [id]` | Validate one brief or all; non-zero on invalid |
| `--brief-write --id W… --file path.json` | Validate; atomic write; replace `agent` from payload; keep existing `human` unless `--human`; set stamps; derive status |
| `--brief-restub --id W…` | Clear agent shell to pending; keep `human` |

### Write merge detail

1. Load existing brief if any (else start from stub defaults).
2. Take `agent` from payload.
3. Keep existing `human` unless `--human` is set, in which case payload `human` replaces.
4. Reject if paper missing.
5. Reject duplicate claim ids, dangling support/contradict edges, `ready` without required fields.
6. Atomic replace (temp file then rename), same pattern as papers.
7. On validation failure, leave the previous brief file untouched.

### Stub failure

If paper write succeeds and stub create fails, surface `brief_stub_failed` (warn or non-zero per implementation plan). Do not silent-succeed without a stub when enrich-on-first-load is the default. Operator recovery: fix path permissions and restub/ensure.

### Id remap

OpenAlex alias / 301 merges must move or alias briefs with papers and edges. Brief identity follows paper identity; no separate brief alias scheme in v1 beyond whatever papers already use.

## Skill procedure

Extend `skills/lit-capture/SKILL.md` and `docs/skill-usage.md`.

After successful online capture (and whenever the agent starts lit work):

1. Run `--enrich-pending`.
2. If none, stop.
3. For each selected id (small per-turn cap, e.g. 3):
   - Read `.lit/papers/<id>.json`.
   - Use fulltext when clearly available; otherwise abstract. Set brief and claim `basis` honestly.
   - Draft full brief per schema (in-paper claim graph only).
   - Write through `--brief-write`, not an unvalidated hand overwrite.
4. `--brief-check` on written ids; fix failures before finishing the turn.
5. `git add` briefs with papers/edges as today.

Honesty constraints for the agent author:

- Do not invent pages, tests, or results absent from the source basis.
- Do not mint cross-paper claim ids on first load.
- Do not clear `human.*` unless the user dictated human notes this turn (then `--human`).

Query recipe: before searching the web for literature already in scope, read briefs (human-over-agent merge in the agent's head), then papers, then edges.

`findings/*.md` remains optional human diary. v1 skill does not require a findings file per brief.

## Errors and edge cases

- Dangling `supports` / `contradicts` → reject write.
- Duplicate claim ids → reject write.
- Corrupt brief JSON → check fails; pending list flags or skips as `invalid`.
- Existing `ready` brief + later bib refresh → stub ensure is no-op; agent block unchanged until explicit re-enrich or restub.
- Concurrent writers → last atomic replace wins; no lock file in v1.

## Tests (acceptance)

- First paper write creates exactly one stub; second paper write does not clobber an existing brief.
- `--enrich-pending` returns pending and partial, labeled; empty corpus exits 0.
- `--brief-write` without `--human` preserves pre-existing human fields when payload omits or alters human.
- Validation rejects dangling support targets, duplicate claim ids, and `ready` without required content.
- Status derivation: empty shell stays pending; thin abstract fill can be partial; full content can be ready.
- Failed validation does not leave a partial temp file as the brief path.
- Brief write without a paper file fails.

## Rollout

1. Schema helpers + stub ensure hooked into paper write.
2. CLI verbs + tests.
3. Skill and usage doc updates (pending drain as default follow-on).
4. Optional later: findings render, cross-paper claim pass, fulltext helper, `stale` policy.

## Open points for the implementation plan (not design forks)

- Exact JSON list vs line format for `--enrich-pending` output.
- Whether stub failure fails the whole fetch exit code or warns with a distinct code path.
- Per-turn pending cap as skill guidance vs hard CLI limit (design assumes skill guidance).
- Mirror path under `.agents` / user skill copies when this repo ships skill mirrors.
