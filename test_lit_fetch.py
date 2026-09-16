"""Offline checks for lit_fetch.py. Plain asserts, no test framework.

Run: python test_lit_fetch.py   (exit 0 when all checks pass)
Network calls never leave the test process: every test that reaches the
network installs a fake via lit_fetch.http_get (see Task 3).
"""

import json
import sys

import lit_fetch

# ---------------------------------------------------------------------------
# frozen fixtures
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD = {
    "id": "https://openalex.org/W1111111111",
    "doi": "https://doi.org/10.1234/Sample.2021",
    "display_name": "A Sample Study of Graphs and Edges",
    "publication_date": "2021-06-01",
    "publication_year": 2021,
    "cited_by_count": 12,
    "authorships": [
        {"author": {"display_name": "Jane Doe"}},
        {"author": {"display_name": "Ravi Patel"}},
    ],
    "topics": [{"display_name": "Graph theory"}, {"display_name": "Data systems"}],
    "open_access": {"oa_url": "https://example.org/pdf"},
    "primary_location": {"source": {"display_name": "Journal of Samples"}},
    "referenced_works": [
        "https://openalex.org/W2222222222",
        "https://openalex.org/W3333333333",
    ],
    "abstract_inverted_index": {"Sample": [0], "study": [1], "of": [2],
                                "graphs": [3], "and": [4], "edges": [5],
                                "Copyright": [6], "2021": [7]},
}

CANDIDATES = [
    {"id": "https://openalex.org/W1111111111",
     "display_name": "A Sample Study of Graphs and Edges",
     "publication_year": 2021,
     "authorships": [{"author": {"display_name": "Jane Doe"}}]},
    {"id": "https://openalex.org/W4444444444",
     "display_name": "a sample study of graphs and edges",
     "publication_year": 2019,
     "authorships": [{"author": {"display_name": "Bob Roe"}}]},
    {"id": "https://openalex.org/W5555555555",
     "display_name": "A Sample Study of Graphs and Nodes",
     "publication_year": 2021,
     "authorships": [{"author": {"display_name": "Jane Doe"}}]},
]


def make_payload(wid, refs=()):
    """A minimal valid OpenAlex work payload for a synthetic W-id."""
    return {
        "id": "https://openalex.org/" + wid,
        "doi": None,
        "display_name": "Paper " + wid,
        "publication_date": None,
        "publication_year": 2020,
        "cited_by_count": 0,
        "authorships": [],
        "topics": [],
        "open_access": {},
        "primary_location": None,
        "referenced_works": ["https://openalex.org/" + r for r in refs],
        "abstract_inverted_index": None,
    }


# ---------------------------------------------------------------------------
# checks: pure identity core
# ---------------------------------------------------------------------------

def test_fold():
    assert lit_fetch.fold("Hello,  World!") == "hello world"
    assert lit_fetch.fold("  State-of-the-Art Methods ") == "state of the art methods"
    assert lit_fetch.fold(None) == ""
    assert lit_fetch.fold("") == ""


def test_bare_ids():
    assert lit_fetch.bare_wid("https://openalex.org/W2741809807") == "W2741809807"
    assert lit_fetch.bare_wid(" W1111111111 ") == "W1111111111"
    assert lit_fetch.bare_doi("https://doi.org/10.1038/Nature12373") == "10.1038/nature12373"
    assert lit_fetch.bare_doi("10.1234/X") == "10.1234/x"
    assert lit_fetch.bare_doi(None) is None
    assert lit_fetch.bare_doi("") is None


def test_reconstruct_abstract():
    assert lit_fetch.reconstruct_abstract(
        {"A": [0], "b": [1], "graph": [2, 4], "of": [3]}) == "A b graph of graph"
    assert lit_fetch.reconstruct_abstract(None) is None
    assert lit_fetch.reconstruct_abstract({}) is None
    junk = {"Real": [0], "title": [1], "Copyright": [2],
            "(c)": [3], "2020": [4], "ACM": [5]}
    assert lit_fetch.reconstruct_abstract(junk) == "Real title Copyright (c) 2020 ACM"


def test_normalize_work():
    rec = lit_fetch.normalize_work(SAMPLE_PAYLOAD, seed=True, source="capture",
                                   captured_at="2026-09-16T00:00:00Z")
    assert rec["id"] == "W1111111111"
    assert rec["doi"] == "10.1234/sample.2021"
    assert rec["display_name"] == "A Sample Study of Graphs and Edges"
    assert rec["publication_date"] == "2021-06-01"
    assert rec["publication_year"] == 2021
    assert rec["cited_by_count"] == 12
    assert rec["authors"] == ["Jane Doe", "Ravi Patel"]
    assert rec["topics"] == ["Graph theory", "Data systems"]
    assert rec["oa_url"] == "https://example.org/pdf"
    assert rec["venue"] == "Journal of Samples"
    assert rec["referenced_works"] == ["W2222222222", "W3333333333"]
    assert rec["seed"] is True
    assert rec["source"] == "capture"
    assert rec["captured_at"] == "2026-09-16T00:00:00Z"
    assert rec["abstract"] == "Sample study of graphs and edges Copyright 2021"
    bare = dict(SAMPLE_PAYLOAD, abstract_inverted_index=None,
                primary_location=None, doi=None)
    rec2 = lit_fetch.normalize_work(bare, seed=False, source="fetch",
                                    captured_at="2026-09-16T00:00:00Z")
    assert rec2["abstract"] is None
    assert rec2["venue"] is None
    assert rec2["doi"] is None
    assert rec2["seed"] is False and rec2["source"] == "fetch"


def test_verify_title():
    q = "A Sample Study of Graphs and Edges"
    # two fold-matches, no disambiguator: ambiguous, none verifies
    assert lit_fetch.verify_title(q, CANDIDATES, None, None) is None
    # surname disambiguates to exactly one
    hit = lit_fetch.verify_title(q, CANDIDATES, "Doe", None)
    assert hit is not None and lit_fetch.bare_wid(hit["id"]) == "W1111111111"
    # year disambiguates to exactly one
    hit = lit_fetch.verify_title(q, CANDIDATES, None, "2021")
    assert hit is not None and lit_fetch.bare_wid(hit["id"]) == "W1111111111"
    # near miss never matches
    assert lit_fetch.verify_title("Study of Graphs and Nodes", CANDIDATES, None, None) is None
    # wrong surname rejects
    assert lit_fetch.verify_title(q, CANDIDATES, "Smith", None) is None
    # wrong year rejects
    assert lit_fetch.verify_title(q, CANDIDATES, None, "1999") is None


# ---------------------------------------------------------------------------
# checks: queue, graph, index template
# ---------------------------------------------------------------------------

def test_chunk_ids():
    ids = ["W3", "W1", "W2", "W1"] + ["W%d" % i for i in range(4, 250)]
    chunks = lit_fetch.chunk_ids(ids)
    assert all(len(c) <= 100 for c in chunks)
    assert [len(c) for c in chunks] == [100, 100, 49]
    flat = [w for c in chunks for w in c]
    assert len(flat) == len(set(flat))
    assert flat[:3] == ["W3", "W1", "W2"]
    assert lit_fetch.chunk_ids([]) == []


def test_parse_ref():
    assert lit_fetch.parse_ref("doi:10.1038/nature12373") == ("doi", "10.1038/nature12373")
    assert lit_fetch.parse_ref("W2741809807") == ("wid", "W2741809807")
    assert lit_fetch.parse_ref("arxiv:2401.12345") == ("arxiv", "2401.12345")
    assert lit_fetch.parse_ref("title:Some Title Here") == ("title", "Some Title Here")
    assert lit_fetch.parse_ref("nonsense") is None
    assert lit_fetch.parse_ref("") is None
    assert lit_fetch.parse_ref(None) is None


def test_entry_key_and_dedupe():
    known = {"wid:W1111111111", "doi:10.1234/sample.2021",
             "title:a sample study of graphs and edges"}
    entries = [
        {"ref": "W1111111111"},
        {"ref": "doi:HTTPS://DOI.ORG/10.1234/Sample.2021"},
        {"ref": "title:A Sample Study of Graphs and Edges",
         "title": "A Sample Study of Graphs and Edges"},
        {"ref": "doi:10.9999/new.thing"},
        {"ref": "doi:10.9999/new.thing"},
        {"ref": "title:  A  NEW Paper!", "title": "A  NEW Paper!"},
    ]
    for e in entries:
        e["_ref"] = lit_fetch.parse_ref(e["ref"])
    kept, dups = lit_fetch.dedupe_inbox(entries, known)
    assert len(dups) == 4
    assert [lit_fetch.entry_key(e) for e in kept] == [
        "doi:10.9999/new.thing", "title:a new paper"]


def test_union_edges():
    a = [{"source": "W1", "target": "W2"}, {"source": "W1", "target": "W3"}]
    b = [{"source": "W1", "target": "W2"}, {"source": "W2", "target": "W3"}]
    assert lit_fetch.union_edges(a, b) == [
        {"source": "W1", "target": "W2"},
        {"source": "W1", "target": "W3"},
        {"source": "W2", "target": "W3"},
    ]


def test_remap_edges():
    edges = [{"source": "W1", "target": "W2"}, {"source": "W9", "target": "W3"}]
    aliases = {"W2": "W5", "W5": "W7", "W9": "W1"}
    assert lit_fetch.remap_edges(edges, aliases) == [
        {"source": "W1", "target": "W7"},
        {"source": "W1", "target": "W3"},
    ]


def test_render_index():
    text = lit_fetch.render_index(3, 10, 5, 1, "2026-09-16T00:00:00Z")
    assert "| 3 |" in text and "| 10 |" in text and "| 5 |" in text and "| 1 |" in text
    assert "last-synced: 2026-09-16T00:00:00Z" in text
    assert "biased" in text and "CC0" in text
    assert "\u2014" not in lit_fetch.INDEX_TEMPLATE
    assert "\u2014" not in text
    assert "__" not in text


CHECKS = [
    test_fold,
    test_bare_ids,
    test_reconstruct_abstract,
    test_normalize_work,
    test_verify_title,
    test_chunk_ids,
    test_parse_ref,
    test_entry_key_and_dedupe,
    test_union_edges,
    test_remap_edges,
    test_render_index,
]


def main():
    failed = 0
    for check in CHECKS:
        try:
            check()
            print("PASS " + check.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL " + check.__name__ + ": "
                  + exc.__class__.__name__ + ": " + str(exc))
    if failed:
        print(str(failed) + " check(s) failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
