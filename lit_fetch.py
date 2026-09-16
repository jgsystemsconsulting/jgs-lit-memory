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
