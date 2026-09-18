# Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE.
# SPDX-License-Identifier: MIT
"""lit_fetch.py: capture OpenAlex works into a .lit corpus.

Single file, Python 3.9+ standard library only. Part of jgs-lit-memory.
See README.md and skills/lit-capture/SKILL.md.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path

OA_PREFIX = "https://openalex.org/"
DOI_PREFIX = "https://doi.org/"


# ---------------------------------------------------------------------------
# pure corpus logic: identity and normalization (no network)
# ---------------------------------------------------------------------------

def bare_wid(value):
    """Strip the https://openalex.org/ prefix; return e.g. W2741809809."""
    return str(value).strip().removeprefix(OA_PREFIX)


def bare_doi(value):
    """Lowercase and strip any https://doi.org/ prefix; None stays None."""
    if not value:
        return None
    d = str(value).strip().lower()
    if d.startswith(DOI_PREFIX):
        d = d[len(DOI_PREFIX):]
    return d or None


def fold(title):
    """Lowercase, turn punctuation into spaces, collapse whitespace."""
    if not title:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"[^0-9a-z\s]", " ", str(title).lower())).strip()


def reconstruct_abstract(inv_idx):
    """Rebuild abstract text from an abstract_inverted_index.

    None or empty stays None. Trailing junk in the index is kept verbatim;
    v1 never strips it (spec: joined text kept verbatim).
    """
    if not inv_idx:
        return None
    positions = {}
    for word, idxs in inv_idx.items():
        for i in idxs:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def normalize_work(payload, seed, source, captured_at=None):
    """Map a raw OpenAlex work object to the corpus record schema.

    The record id is the bare canonical W-id and always matches the file name
    the caller writes. captured_at defaults to now, ISO 8601 UTC.
    """
    if captured_at is None:
        captured_at = now_iso()
    return {
        "id": bare_wid(payload["id"]),
        "doi": bare_doi(payload.get("doi")),
        "display_name": payload.get("display_name"),
        "publication_date": payload.get("publication_date"),
        "publication_year": payload.get("publication_year"),
        "cited_by_count": payload.get("cited_by_count"),
        "authors": [a["author"]["display_name"]
                    for a in payload.get("authorships") or []
                    if a.get("author", {}).get("display_name")],
        "topics": [t["display_name"] for t in payload.get("topics") or []
                   if t.get("display_name")],
        "oa_url": (payload.get("open_access") or {}).get("oa_url"),
        "venue": ((payload.get("primary_location") or {}).get("source") or {})
                 .get("display_name"),
        "referenced_works": [bare_wid(w)
                             for w in payload.get("referenced_works") or []],
        "seed": seed,
        "captured_at": captured_at,
        "source": source,
        "abstract": reconstruct_abstract(payload.get("abstract_inverted_index")),
    }


def verify_title(query_title, candidates, author_surname=None, year=None):
    """Return the single verified candidate, else None.

    A candidate survives when fold(title) matches the query exactly and, when
    supplied, its authorships contain the surname (case-folded) and
    publication_year matches. Zero survivors, or two or more after the
    supplied checks, return None: near-misses and ambiguity never auto-write.
    """
    matches = [c for c in candidates
               if fold(c.get("display_name")) == fold(query_title)]
    if author_surname is not None:
        s = author_surname.lower()
        matches = [c for c in matches
                   if any(s in (a.get("author", {}).get("display_name") or "").lower()
                          for a in c.get("authorships") or [])]
    if year is not None:
        matches = [c for c in matches
                   if str(c.get("publication_year")) == str(year)]
    if len(matches) == 1:
        return matches[0]
    return None


def now_iso():
    """Current time, ISO 8601 UTC with Z suffix."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# pure corpus logic: inbox queue, citation graph, generated index
# ---------------------------------------------------------------------------

PAGE_SIZE = 100

REF_RE = re.compile(r"^(doi|arxiv|title):(.+)$", re.S)
WID_RE = re.compile(r"^W\d+$")


def chunk_ids(ids, size=PAGE_SIZE):
    """Dedupe preserving first-seen order, then split into chunks of at most
    `size`. Chunks are computed after skip/dedupe (spec)."""
    seen = set()
    unique = []
    for raw in ids:
        w = bare_wid(raw)
        if w and w not in seen:
            seen.add(w)
            unique.append(w)
    return [unique[i:i + size] for i in range(0, len(unique), size)]


def parse_ref(ref):
    """Parse one inbox ref. Returns (kind, value) or None when malformed.

    kind is "doi", "wid", "arxiv", or "title". "W<digits>" is a wid; anything
    else must carry one of the three kind prefixes.
    """
    if not ref:
        return None
    r = str(ref).strip()
    if WID_RE.match(r):
        return ("wid", r)
    m = REF_RE.match(r)
    if m:
        return (m.group(1), m.group(2).strip())
    return None


def entry_key(entry):
    """Normalize one inbox entry to its dedupe key form (spec: doi refs to
    normalized DOI, W-ids to W-id, title-form and arxiv-form to folded title)."""
    kind, value = entry["_ref"]
    if kind == "doi":
        return "doi:" + (bare_doi(value) or value)
    if kind == "wid":
        return "wid:" + value
    if kind == "arxiv" and not entry.get("title"):
        return "arxiv:" + value
    return "title:" + fold(entry.get("title") or "")


def corpus_keys(papers_dir):
    """Known-ID set for inbox dedupe: canonical W-ids, bare normalized DOIs,
    and folded display_names of existing records."""
    keys = set()
    for path in sorted(Path(papers_dir).glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        keys.add("wid:" + rec["id"])
        if rec.get("doi"):
            keys.add("doi:" + rec["doi"])
        if rec.get("display_name"):
            keys.add("title:" + fold(rec["display_name"]))
    return keys


def dedupe_inbox(entries, known_keys):
    """Return (kept, duplicates). Duplicate = key in known_keys, or key equal
    to an earlier entry in the same file."""
    kept, duplicates, seen = [], [], set()
    for entry in entries:
        k = entry_key(entry)
        if k in known_keys or k in seen:
            duplicates.append(entry)
        else:
            seen.add(k)
            kept.append(entry)
    return kept, duplicates


def union_edges(existing, new):
    """Union edge lists, deduped on (source, target), input order preserved."""
    out, seen = [], set()
    for e in list(existing) + list(new):
        key = (e["source"], e["target"])
        if key not in seen:
            seen.add(key)
            out.append({"source": e["source"], "target": e["target"]})
    return out


def resolve_alias(wid, aliases):
    """Follow alias chains to the final canonical W-id. Cycle-safe."""
    seen = set()
    while wid in aliases and wid not in seen:
        seen.add(wid)
        wid = aliases[wid]
    return wid


def remap_edges(edges, aliases):
    """Repoint every edge endpoint through the full alias table."""
    return [{"source": resolve_alias(e["source"], aliases),
             "target": resolve_alias(e["target"], aliases)}
            for e in edges]


# ---------------------------------------------------------------------------
# pure corpus logic: analysis briefs (sidecar .lit/briefs/<W-id>.json)
# ---------------------------------------------------------------------------

BRIEF_SCHEMA_VERSION = 1
BRIEF_STATUS = ("pending", "partial", "ready", "stale")   # stale reserved, v1 never writes it
BRIEF_BASIS = ("none", "abstract", "fulltext", "mixed")
CLAIM_TYPES = ("contribution", "finding", "method", "limit", "assumption", "other")
CLAIM_BASIS = ("abstract", "fulltext", "human")
CLAIM_CONFIDENCE = ("low", "med", "high")
CLAIM_REQUIRED = ("id", "text", "type", "confidence", "basis")
AGENT_TEXT_FIELDS = ("overview", "methods_tests", "limits", "why_it_matters", "notes")


def present_str(value):
    """A string field is present when non-null with stripped length > 0."""
    return isinstance(value, str) and bool(value.strip())


def present_claims(claims):
    """A claims array is present when at least one claim has present text."""
    return any(isinstance(c, dict) and present_str(c.get("text"))
               for c in claims or [])


def empty_agent_block():
    """Agent-owned fields; the agent block is fully replaced on re-enrich."""
    return {"overview": "", "claims": [], "methods_tests": "", "limits": "",
            "why_it_matters": "", "related_in_corpus": [], "open_questions": [],
            "notes": ""}


def empty_human_block():
    """Human-owned fields; merge-only. null means "not dictated by the user"."""
    return {"overview": None, "claims": [], "methods_tests": None, "limits": None,
            "why_it_matters": None, "open_questions": [], "notes": None}


def new_brief(wid, paper_captured_at=None):
    """The stub shape: pending, no stamps, empty shells. No placeholder claims."""
    return {"id": wid,
            "schema_version": BRIEF_SCHEMA_VERSION,
            "status": "pending",
            "basis": "none",
            "enriched_at": None,
            "enrichment_source": None,
            "paper_captured_at": paper_captured_at,
            "agent": empty_agent_block(),
            "human": empty_human_block()}


def paper_capture_stamp(paper):
    """The paper record's capture stamp (captured_at), or None."""
    if not isinstance(paper, dict):
        return None
    stamp = paper.get("captured_at")
    return stamp if isinstance(stamp, str) and stamp.strip() else None


def derive_basis(agent):
    """Top-level basis from agent.claims basis values only (human claims never
    move it). No claims with present text -> none; all-abstract -> abstract;
    all-fulltext -> fulltext; any other combination (including human-only,
    which is unexpected) -> mixed."""
    bases = [c.get("basis") for c in (agent or {}).get("claims") or []
             if isinstance(c, dict) and present_str(c.get("text"))]
    if not bases:
        return "none"
    if set(bases) == {"abstract"}:
        return "abstract"
    if set(bases) == {"fulltext"}:
        return "fulltext"
    return "mixed"


def nonempty_agent(agent):
    """Any agent-authored content at all (spec: pending vs partial gate)."""
    a = agent or {}
    return bool(present_str(a.get("overview"))
                or present_str(a.get("methods_tests"))
                or present_str(a.get("limits"))
                or present_str(a.get("why_it_matters"))
                or present_str(a.get("notes"))
                or (a.get("open_questions") or [])
                or (a.get("related_in_corpus") or [])
                or present_claims(a.get("claims")))


def ready_content(agent, union_ids):
    """Ready predicate on the agent block: overview, at least one claim with
    present text, methods_tests / limits / why_it_matters present, every such
    claim carrying allowed type / confidence / basis enums, and every
    supports / contradicts target existing in the agent+human claim-id union."""
    a = agent or {}
    if not present_str(a.get("overview")):
        return False
    claims = [c for c in a.get("claims") or []
              if isinstance(c, dict) and present_str(c.get("text"))]
    if not claims:
        return False
    for field in ("methods_tests", "limits", "why_it_matters"):
        if not present_str(a.get(field)):
            return False
    for c in claims:
        if c.get("type") not in CLAIM_TYPES:
            return False
        if c.get("confidence") not in CLAIM_CONFIDENCE:
            return False
        if c.get("basis") not in CLAIM_BASIS:
            return False
        for t in (c.get("supports") or []) + (c.get("contradicts") or []):
            if t not in union_ids:
                return False
    return True


def derive_status(agent, union_ids):
    """Closed function; stored status is ignored. pending -> ready -> partial."""
    if not nonempty_agent(agent):
        return "pending"
    if ready_content(agent, union_ids):
        return "ready"
    return "partial"


INDEX_TEMPLATE = r"""> Generated by lit_fetch.py. Do not edit; the next capture regenerates this file.

# Literature corpus (`.lit/`)

This is the project's captured literature corpus: papers pulled from research
conversations, normalized from OpenAlex metadata. Read this file first each
session; it carries the counts and the query recipes.

| metric | count |
|---|---|
| papers (full records) | __PAPERS__ |
| edges | __EDGES__ |
| boundary nodes (edge endpoints without records) | __BOUNDARY__ |
| inbox pending | __INBOX__ |

last-synced: __GENERATED__

Records live in `papers/<W-id>.json`. The citation graph lives in
`graph/edges.jsonl`, one `{"source": ..., "target": ...}` per line, where
`source` cites `target`. Boundary nodes appear only as edge endpoints; promote
one by fetching its W-id (pass it to `--ids`).

## Query recipes (Git Bash)

Grep for a title fragment across the corpus:

```bash
grep -ril "fragment" .lit/papers/
```

Extract boundary IDs (edge endpoints with no record yet):

```bash
python -c "import json,glob,pathlib;edges=[json.loads(l) for l in open('.lit/graph/edges.jsonl') if l.strip()];have={pathlib.Path(p).stem for p in glob.glob('.lit/papers/*.json')};print('\n'.join(sorted(({e['source'] for e in edges}|{e['target'] for e in edges})-have)))"
```

Count edges per paper:

```bash
python -c "import json,collections;c=collections.Counter();[c.update([json.loads(l)['source'] for l in open('.lit/graph/edges.jsonl') if l.strip()]) for _ in [0]];print(c.most_common())"
```

Find papers citing a given W-id (who cites W123):

```bash
python -c "import json;print('\n'.join(json.loads(l)['source'] for l in open('.lit/graph/edges.jsonl') if json.loads(l)['target']=='W123'))"
```

## Caveats

`referenced_works` is lossy relative to printed reference lists: OpenAlex
matches references by DOI, so the stored graph is biased toward DOI-matchable
citations. Treat the graph as biased, not authoritative.

License: OpenAlex metadata is CC0. Reconstructed abstracts are for local
corpus use; do not redistribute them.
"""


def render_index(papers, edges, boundary, inbox_pending, generated_at):
    """Fill the generated .lit/SKILL.md template. Placeholder replacement, not
    str.format, so the recipe snippets can contain braces freely."""
    text = INDEX_TEMPLATE
    for key, value in [("PAPERS", papers), ("EDGES", edges),
                       ("BOUNDARY", boundary), ("INBOX", inbox_pending),
                       ("GENERATED", generated_at)]:
        text = text.replace("__" + key + "__", str(value))
    return text


# ---------------------------------------------------------------------------
# corpus write model (atomic everywhere)
# ---------------------------------------------------------------------------

def atomic_write(path, text):
    """Write text atomically: temp file in the same directory, then os.replace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ensure_corpus(lit_dir):
    """Create the corpus directory tree on first use in a fresh --dir."""
    for sub in ("papers", "graph", "findings"):
        (Path(lit_dir) / sub).mkdir(parents=True, exist_ok=True)


class Run:
    """Accumulates the end-of-run summary block."""

    def __init__(self):
        self.written = 0
        self.skipped = 0
        self.failed = 0
        self.failures = []

    def fail(self, identifier, reason):
        self.failed += 1
        self.failures.append((identifier, reason))

    def summary(self):
        lines = ["written={0} skipped={1} failed={2}".format(
            self.written, self.skipped, self.failed)]
        lines += ["failed: {0} ({1})".format(i, r) for i, r in self.failures]
        return "\n".join(lines)


def write_record(record, lit_dir):
    """Atomically write one normalized record. File name equals record id."""
    atomic_write(Path(lit_dir) / "papers" / (record["id"] + ".json"),
                 json.dumps(record, indent=2, ensure_ascii=False) + "\n")


def write_one(payload, lit_dir, run, seed, source):
    """Normalize and write one record with post-fetch skip-if-exists.

    The canonical id is only knowable after the fetch, so the skip happens
    here. An existing canonical record is never rewritten: its seed and
    captured_at stay untouched, and the run counts it as skipped.
    Returns (record, wrote)."""
    record = normalize_work(payload, seed=seed, source=source)
    path = Path(lit_dir) / "papers" / (record["id"] + ".json")
    if path.exists():
        run.skipped += 1
        return record, False
    write_record(record, lit_dir)
    run.written += 1
    return record, True


def edges_of(records):
    """Citation edges from normalized records: source cites target, bare W-ids."""
    return [{"source": r["id"], "target": t}
            for r in records for t in r["referenced_works"]]


def load_edges(lit_dir):
    p = Path(lit_dir) / "graph" / "edges.jsonl"
    if not p.exists():
        return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def load_aliases(lit_dir):
    p = Path(lit_dir) / "graph" / "aliases.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_aliases(lit_dir, aliases):
    atomic_write(Path(lit_dir) / "graph" / "aliases.json",
                 json.dumps(aliases, indent=2, sort_keys=True) + "\n")


def write_edges(lit_dir, new_edges):
    """Union new edges into edges.jsonl, healing as we go: existing and new
    endpoints are both remapped through the full alias table before the union,
    so stale endpoints collapse onto canonical ones. Full idempotent rewrite,
    atomic."""
    aliases = load_aliases(lit_dir)
    existing = remap_edges(load_edges(lit_dir), aliases)
    combined = union_edges(existing, remap_edges(new_edges, aliases))
    atomic_write(Path(lit_dir) / "graph" / "edges.jsonl",
                 "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in combined))
    return len(combined)


def boundary_nodes(lit_dir):
    """Edge endpoints that have no papers/<id>.json. No placeholder records
    are ever created for them (spec)."""
    papers_dir = Path(lit_dir) / "papers"
    have = {p.stem for p in papers_dir.glob("*.json")} if papers_dir.is_dir() else set()
    endpoints = set()
    for e in load_edges(lit_dir):
        endpoints.add(bare_wid(e["source"]))
        endpoints.add(bare_wid(e["target"]))
    return endpoints - have


def count_inbox(lit_dir):
    p = Path(lit_dir) / "inbox.jsonl"
    if not p.exists():
        return 0
    return sum(1 for line in p.read_text(encoding="utf-8").splitlines() if line.strip())


def regenerate_index(lit_dir):
    """Regenerate .lit/SKILL.md after any successful write operation."""
    ensure_corpus(lit_dir)
    papers = len(list((Path(lit_dir) / "papers").glob("*.json")))
    text = render_index(papers, len(load_edges(lit_dir)),
                        len(boundary_nodes(lit_dir)), count_inbox(lit_dir),
                        now_iso())
    atomic_write(Path(lit_dir) / "SKILL.md", text)


# ---------------------------------------------------------------------------
# OpenAlex network layer (the only code that touches the network)
# ---------------------------------------------------------------------------

BASE_URL = "https://api.openalex.org"
TIMEOUT = 30
MAX_ATTEMPTS = 5
BACKOFF_SCHEDULE = (1, 2, 4, 8, 16)
UA = "lit_fetch/1.0 (jgs-lit-memory)"
SELECT_FIELDS = ("id,doi,display_name,publication_date,publication_year,"
                 "authorships,referenced_works,cited_by_count,topics,"
                 "open_access,primary_location,abstract_inverted_index")


class BudgetExhausted(Exception):
    """X-RateLimit-Remaining read 0: abort the run, keep completed writes."""


class BackoffExhausted(Exception):
    """A call kept failing through the full backoff schedule."""


def _retry_delay(headers, attempt_index):
    """Retry-After (seconds) when the response carries one, else the schedule."""
    if headers is not None:
        try:
            ra = headers.get("Retry-After")
        except AttributeError:
            ra = None
        if ra:
            try:
                return float(ra)
            except ValueError:
                pass
    return BACKOFF_SCHEDULE[min(attempt_index, len(BACKOFF_SCHEDULE) - 1)]


def http_get(url, timeout=TIMEOUT):
    """GET a URL. Returns (status, headers, body_text).

    Retries 429 and 5xx on the backoff schedule; Retry-After overrides.
    Always returns the tuple once a 200 body is in hand, including when
    x-ratelimit-remaining is 0: budget-abort is the caller's job (verb loops
    stop before the next call). urllib follows 301 merge redirects itself;
    the record body returned is already the canonical work.
    """
    for attempt in range(MAX_ATTEMPTS):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                headers = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, headers, body
        except urllib.error.HTTPError as e:
            if not (e.code == 429 or 500 <= e.code < 600):
                raise
            headers = e.headers
        # failed attempt: sleep the schedule (Retry-After overrides), then retry
        time.sleep(_retry_delay(headers, attempt))
    raise BackoffExhausted(url)


def with_params(path, params, api_key):
    """Build an API URL. api_key appended when present; no mailto, ever."""
    if api_key:
        params = dict(params, api_key=api_key)
    return BASE_URL + path + "?" + urllib.parse.urlencode(params)


def work_url(identifier, api_key):
    """Singleton work URL: /works/doi:<doi> or /works/<W-id> (free)."""
    return with_params("/works/" + urllib.parse.quote(identifier, safe=":/"),
                       {"select": SELECT_FIELDS}, api_key)


def ids_filter_url(wids, api_key):
    """Batch list URL: pipe-OR filter, per-page=100 (budgeted)."""
    return with_params("/works",
                       {"filter": "ids.openalex:" + "|".join(wids),
                        "per-page": str(PAGE_SIZE),
                        "select": SELECT_FIELDS}, api_key)


def search_url(title, api_key):
    """Verified title search URL (budgeted)."""
    return with_params("/works", {"search": title, "per-page": "5",
                                  "select": SELECT_FIELDS}, api_key)


def parse_envelope(body):
    """results list from a list/filter/search envelope {"meta": ..., "results": [...]}."""
    return json.loads(body).get("results", [])


def warn_keyless(call_type, api_key):
    """One warning line before any budgeted call when no key is configured."""
    if not api_key:
        print("warning: {0} without OPENALEX_API_KEY; the keyless budget is "
              "$0.10/day and this call is budgeted".format(call_type),
              file=sys.stderr)


# ---------------------------------------------------------------------------
# verbs and CLI
# ---------------------------------------------------------------------------

def promote_payload(payload, lit_dir, run, seed=True, source="capture"):
    """Write one already-fetched payload: record (skip-if-exists) plus edges,
    then regenerate the index when anything changed (record written or edges
    added), so edge-only changes never leave the index stale."""
    ensure_corpus(lit_dir)
    edges_before = len(load_edges(lit_dir))
    record, wrote = write_one(payload, lit_dir, run, seed, source)
    edges_after = write_edges(lit_dir, edges_of([record]))
    if wrote or edges_after != edges_before:
        regenerate_index(lit_dir)
    return record


def capture_identifier(identifier, is_wid_form, lit_dir, api_key, run):
    """Singleton capture by DOI form or W-id. Records the 301 merge alias when
    a W-id request resolves to a different canonical id, and prints one merge
    note. DOI requests need no alias entry: they dedupe through the canonical
    id itself."""
    ensure_corpus(lit_dir)
    status, headers, body = http_get(work_url(identifier, api_key))
    payload = json.loads(body)
    canonical = bare_wid(payload["id"])
    requested = bare_wid(identifier) if is_wid_form else None
    aliases = load_aliases(lit_dir)
    if requested and requested != canonical and requested not in aliases:
        aliases[requested] = canonical
        save_aliases(lit_dir, aliases)
        print("merge: {0} -> {1}".format(requested, canonical))
    return promote_payload(payload, lit_dir, run, seed=True, source="capture")


def verb_title(title, author, year, lit_dir, api_key, run):
    """Verified title search. Returns True when the paper is present
    afterwards: written now, or already in the corpus via skip-if-exists.

    On no verified hit: writes nothing, counts one failure, and prints the top
    candidates for a human decision."""
    warn_keyless("title search", api_key)
    status, headers, body = http_get(search_url(title, api_key))
    candidates = parse_envelope(body)
    hit = verify_title(title, candidates, author, year)
    if hit is None:
        run.fail(title, "verification failed")
        print("no single verified match; top candidates:")
        for c in candidates[:5]:
            print("  {0}  {1}  {2}".format(bare_wid(c.get("id", "W?")),
                                           c.get("publication_year"),
                                           c.get("display_name")))
        return False
    promote_payload(hit, lit_dir, run, seed=True, source="capture")
    return True


def parse_ids(raw):
    """Split a pipe-separated id string, normalize, dedupe, preserve order."""
    out, seen = [], set()
    for part in str(raw).split("|"):
        w = bare_wid(part)
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out


def verb_ids(raw_ids, lit_dir, api_key, seed_flag, run):
    """Batch fetch by W-id. Skips ids already in the corpus before chunking,
    warns keyless before the budgeted call, writes seed=false source="fetch"
    records (seed_flag overrides), unions edges once per chunk, and reports
    ids absent from a response as 404 failures. When a response carries
    x-ratelimit-remaining 0, remaining chunks are aborted with one budget
    failure; completed writes stand. Index regenerates when the record set or
    the edge set changed."""
    ensure_corpus(lit_dir)
    ids = parse_ids(raw_ids)
    if not ids:
        print("error: --ids needs at least one W-id", file=sys.stderr)
        sys.exit(2)
    papers_dir = Path(lit_dir) / "papers"
    todo = [w for w in ids if not (papers_dir / (w + ".json")).exists()]
    run.skipped += len(ids) - len(todo)
    if not todo:
        return
    warn_keyless("batch --ids", api_key)
    aliases = load_aliases(lit_dir)
    edges_before = len(load_edges(lit_dir))
    chunks = chunk_ids(todo)
    for i, chunk in enumerate(chunks):
        status, headers, body = http_get(ids_filter_url(chunk, api_key))
        results = parse_envelope(body)
        by_id = {bare_wid(r["id"]): r for r in results}
        records = []
        for wid in chunk:
            payload = by_id.get(wid) or by_id.get(resolve_alias(wid, aliases))
            if payload is None and len(chunk) == 1 and len(by_id) == 1:
                # single-id filter returned exactly one different canonical:
                # treat as a 301 merge (OpenAlex collapsed the requested id)
                only = next(iter(by_id.values()))
                if bare_wid(only["id"]) != wid:
                    payload = only
            if payload is None:
                run.fail(wid, "404; requested id absent from response; "
                         "use --openalex for merged ids")
                continue
            canonical = bare_wid(payload["id"])
            if canonical != wid and wid not in aliases:
                aliases[wid] = canonical
                save_aliases(lit_dir, aliases)
                print("merge: {0} -> {1}".format(wid, canonical))
            record, wrote = write_one(payload, lit_dir, run,
                                      seed=seed_flag, source="fetch")
            records.append(record)
        write_edges(lit_dir, edges_of(records))
        if headers.get("x-ratelimit-remaining") == "0":
            remaining = sum(len(c) for c in chunks[i + 1:])
            if remaining:
                run.fail("{0} remaining id(s)".format(remaining),
                         "budget exhausted; re-run when the daily budget resets")
                print("budget exhausted; completed writes stand")
            break
    edges_after = len(load_edges(lit_dir))
    if run.written or edges_after != edges_before:
        regenerate_index(lit_dir)


def read_inbox(lit_dir):
    """Read inbox entries as dicts, skipping blank lines. Attaches the parsed
    ref as the internal "_ref" key (None when unparseable)."""
    p = Path(lit_dir) / "inbox.jsonl"
    if not p.exists():
        return []
    entries = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        entry = json.loads(line)
        entry["_ref"] = parse_ref(entry.get("ref"))
        entries.append(entry)
    return entries


def resolve_entry(entry, kind, value, lit_dir, api_key, run):
    """Promote one inbox entry. Returns True on success, False on a
    verification failure (already reported by verb_title); raises on hard
    errors (404, network, budget)."""
    if kind == "doi":
        capture_identifier("doi:" + bare_doi(value), False, lit_dir, api_key, run)
        return True
    if kind == "wid":
        capture_identifier(value, True, lit_dir, api_key, run)
        return True
    title = entry.get("title") or (value if kind == "title" else None)
    if not title:
        raise ValueError("no title available to search")
    return verb_title(title, entry.get("author"), entry.get("year"),
                      lit_dir, api_key, run)


def verb_inbox(lit_dir, api_key, run):
    """Triage the inbox: dedupe, resolve every entry, then rewrite the inbox
    exactly once, atomically, keeping only entries that remain. Failures stay
    queued with their reason in "last_error". A BudgetExhausted abort
    re-raises before the rewrite, leaving the original queue file intact, and
    re-runs are idempotent through skip-if-exists."""
    entries = read_inbox(lit_dir)
    parseable = [e for e in entries if e["_ref"]]
    malformed = [e for e in entries if not e["_ref"]]
    for e in malformed:
        e.pop("_ref", None)
        run.fail(e.get("ref", "?"), "unparseable ref")
        e["last_error"] = "unparseable ref"
    papers_dir = Path(lit_dir) / "papers"
    known = corpus_keys(papers_dir) if papers_dir.is_dir() else set()
    kept, duplicates = dedupe_inbox(parseable, known)
    run.skipped += len(duplicates)
    if any(e["_ref"][0] in ("title", "arxiv") for e in kept):
        warn_keyless("inbox title/arxiv search", api_key)
    remaining = list(malformed)
    for entry in kept:
        kind, value = entry.pop("_ref")
        try:
            ok = resolve_entry(entry, kind, value, lit_dir, api_key, run)
            if not ok:
                entry["last_error"] = "verification failed"
                remaining.append(entry)
        except BudgetExhausted:
            raise
        except Exception as exc:
            reason = str(exc) or exc.__class__.__name__
            entry["last_error"] = reason
            run.fail(entry.get("ref", "?"), reason)
            remaining.append(entry)
    atomic_write(Path(lit_dir) / "inbox.jsonl",
                 "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in remaining))
    if run.written:
        regenerate_index(lit_dir)


def verb_status(lit_dir):
    """Corpus summary to stdout. Read-only; never regenerates the index.
    last-synced reads the generated index's timestamp line and prints
    "never" when no generated index exists yet."""
    papers_dir = Path(lit_dir) / "papers"
    papers = len(list(papers_dir.glob("*.json"))) if papers_dir.is_dir() else 0
    edges = len(load_edges(lit_dir))
    boundary = len(boundary_nodes(lit_dir))
    pending = count_inbox(lit_dir)
    last = "never"
    index_path = Path(lit_dir) / "SKILL.md"
    if index_path.exists():
        m = re.search(r"^last-synced: (.+)$",
                      index_path.read_text(encoding="utf-8"), re.M)
        if m:
            last = m.group(1).strip()
    print("papers={0} edges={1} boundary={2} inbox_pending={3}".format(
        papers, edges, boundary, pending))
    print("last-synced: {0}".format(last))
    return 0


CHECK_DOI = "10.1038/nature12373"   # live-probed 2026-09-16 (plan Research section)
CHECK_ID = "W2741809807"            # live-probed 2026-09-16 (plan Research section)


def verb_check(api_key):
    """Live smoke test of the four load-bearing endpoint forms. Exit 1 when
    any form fails. Run on first use and whenever OpenAlex behaves oddly."""
    ok = True
    doi_result = {}

    def probe(name, fn):
        nonlocal ok
        try:
            fn()
            print("OK   " + name)
        except Exception as exc:
            ok = False
            print("FAIL {0}: {1}".format(name, exc))

    def probe_doi():
        payload = json.loads(http_get(work_url("doi:" + CHECK_DOI, api_key))[2])
        doi_result["wid"] = bare_wid(payload["id"])

    def probe_wid():
        payload = json.loads(http_get(work_url(CHECK_ID, api_key))[2])
        assert bare_wid(payload["id"]) == CHECK_ID

    def probe_batch():
        url = ids_filter_url([CHECK_ID, doi_result.get("wid", CHECK_ID)], api_key)
        results = parse_envelope(http_get(url)[2])
        assert isinstance(results, list)

    def probe_search():
        results = parse_envelope(http_get(
            search_url("crystal structure prediction", api_key))[2])
        assert isinstance(results, list)

    probe("doi singleton   /works/doi:" + CHECK_DOI, probe_doi)
    probe("W-id singleton  /works/" + CHECK_ID, probe_wid)
    probe("two-ID batch filter", probe_batch)
    probe("title search", probe_search)
    return 0 if ok else 1


VERB_FLAGS = ("doi", "openalex", "arxiv", "title", "ids", "inbox", "status", "check")


def build_parser():
    p = argparse.ArgumentParser(
        prog="lit_fetch.py",
        description="Capture OpenAlex works into a .lit corpus.")
    p.add_argument("--doi", help="capture by DOI (singleton, free)")
    p.add_argument("--openalex", help="capture by OpenAlex W-id (singleton, free)")
    p.add_argument("--arxiv", help="arXiv id; requires --title (no arXiv lookup exists)")
    p.add_argument("--title", help="verified title search; also the modifier of --arxiv")
    p.add_argument("--author", help="surname disambiguator for --title/--arxiv")
    p.add_argument("--year", help="year disambiguator for --title/--arxiv")
    p.add_argument("--ids", help='pipe-separated W-ids, e.g. "W123|W456"')
    p.add_argument("--inbox", action="store_true", help="triage .lit/inbox.jsonl")
    p.add_argument("--status", action="store_true", help="print corpus summary")
    p.add_argument("--check", action="store_true", help="live smoke test of endpoint forms")
    p.add_argument("--dir", default=".lit", help="corpus root (default .lit)")
    p.add_argument("--api-key", default=os.environ.get("OPENALEX_API_KEY"),
                   help="OpenAlex API key (default env OPENALEX_API_KEY)")
    p.add_argument("--seed", action="store_true",
                   help="mark --ids records seed=true (batch override only)")
    return p


def pick_verb(args):
    if args.arxiv and not args.title:
        print("error: --arxiv requires --title (OpenAlex has no arXiv ID "
              "lookup); supply the exact title, or capture the DOI with --doi",
              file=sys.stderr)
        sys.exit(2)
    names = [n for n in VERB_FLAGS if getattr(args, n)]
    if args.arxiv and "title" in names:
        names.remove("title")   # --title is the required modifier of --arxiv
    if len(names) != 1:
        print("error: give exactly one of --doi/--openalex/--arxiv/--title/"
              "--ids/--inbox/--status/--check", file=sys.stderr)
        sys.exit(2)
    return names[0]


def validate_verb(args, verb):
    if verb == "doi":
        d = bare_doi(args.doi)
        if not d or not d.startswith("10."):
            print("error: --doi expects a DOI like 10.1038/nature12373",
                  file=sys.stderr)
            sys.exit(2)
    if verb == "openalex":
        if not WID_RE.match(args.openalex.strip()):
            print("error: --openalex expects a W-id like W2741809807",
                  file=sys.stderr)
            sys.exit(2)


def main(argv=None):
    args = build_parser().parse_args(argv)
    verb = pick_verb(args)
    validate_verb(args, verb)
    lit_dir = Path(args.dir)
    api_key = args.api_key or None
    run = Run()
    try:
        if verb == "doi":
            try:
                capture_identifier("doi:" + bare_doi(args.doi), False,
                                   lit_dir, api_key, run)
            except BudgetExhausted:
                raise
            except Exception as exc:
                run.fail(args.doi, str(exc) or exc.__class__.__name__)
        elif verb == "openalex":
            try:
                capture_identifier(bare_wid(args.openalex), True,
                                   lit_dir, api_key, run)
            except BudgetExhausted:
                raise
            except Exception as exc:
                run.fail(args.openalex, str(exc) or exc.__class__.__name__)
        elif verb == "arxiv":
            print("note: resolving by verified title search (arXiv id "
                  + args.arxiv + " is not an OpenAlex lookup key)")
            try:
                verb_title(args.title, args.author, args.year,
                           lit_dir, api_key, run)
            except BudgetExhausted:
                raise
            except Exception as exc:
                run.fail(args.arxiv, str(exc) or exc.__class__.__name__)
        elif verb == "title":
            try:
                verb_title(args.title, args.author, args.year,
                           lit_dir, api_key, run)
            except BudgetExhausted:
                raise
            except Exception as exc:
                run.fail(args.title, str(exc) or exc.__class__.__name__)
        elif verb == "ids":
            verb_ids(args.ids, lit_dir, api_key, args.seed, run)
        elif verb == "inbox":
            verb_inbox(lit_dir, api_key, run)
        elif verb == "status":
            return verb_status(lit_dir)
        elif verb == "check":
            return verb_check(api_key)
    except BudgetExhausted:
        print(run.summary())
        print("budget exhausted; completed writes stand")
        return 1
    except Exception as exc:
        print(run.summary())
        print("error: " + (str(exc) or exc.__class__.__name__))
        return 1
    print(run.summary())
    return 0 if run.failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
