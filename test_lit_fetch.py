"""Offline checks for lit_fetch.py. Plain asserts, no test framework.

Run: python test_lit_fetch.py   (exit 0 when all checks pass)
Network calls never leave the test process: every test that reaches the
network installs a fake via lit_fetch.http_get (see Task 3).
"""

import io
import json
import sys
import urllib.parse

import lit_fetch

lit_fetch.time.sleep = lambda seconds: None

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


# ---------------------------------------------------------------------------
# fakes: the network seam
# ---------------------------------------------------------------------------

def fake_http(handler):
    """Wrap a handler(url) -> (status, headers, body) as a fake lit_fetch.http_get."""
    calls = []

    def get(url, timeout=30):
        calls.append(url)
        return handler(url)

    get.calls = calls
    return get


def envelope(records):
    return json.dumps({"meta": {"count": len(records)}, "results": records})


def fake_urlopen(handler):
    """Patch urllib.request.urlopen UNDER the real lit_fetch.http_get, for
    tests that exercise retry/backoff/BudgetExhausted logic itself. handler(url)
    returns (status, headers, body_text) or raises. Returns the seen URLs."""
    calls = []

    class FakeResp:
        def __init__(self, status, headers, body):
            self.status = status
            self.headers = dict(headers)
            self._body = body

        def read(self):
            return self._body.encode("utf-8")

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def urlopen(req, timeout=30):
        url = req.full_url
        calls.append(url)
        result = handler(url)
        if isinstance(result, Exception):
            raise result
        return FakeResp(*result)

    lit_fetch.urllib.request.urlopen = urlopen
    return calls


# ---------------------------------------------------------------------------
# checks: network layer (all offline through the fake)
# ---------------------------------------------------------------------------

def test_url_builders():
    u = lit_fetch.work_url("doi:10.1038/nature12373", "KEY")
    assert u.startswith("https://api.openalex.org/works/doi:10.1038/nature12373?")
    assert "select=" in u and "api_key=KEY" in u
    u2 = lit_fetch.work_url("W1111111111", None)
    q2 = urllib.parse.parse_qs(urllib.parse.urlparse(u2).query)
    assert q2["select"] == [lit_fetch.SELECT_FIELDS]
    assert "api_key" not in u2 and "mailto" not in u2
    u3 = lit_fetch.ids_filter_url(["W1", "W2"], None)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u3).query)
    assert q["filter"] == ["ids.openalex:W1|W2"]
    assert q["per-page"] == ["100"]
    u4 = lit_fetch.search_url("Graphs and Edges", None)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(u4).query)
    assert q["search"] == ["Graphs and Edges"]
    assert q["per-page"] == ["5"]


def test_parse_envelope():
    assert lit_fetch.parse_envelope('{"meta": {"count": 2}, "results": [1, 2]}') == [1, 2]
    assert lit_fetch.parse_envelope('{"meta": {}}') == []


def test_retry_then_success():
    attempts = []

    def handler(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise lit_fetch.urllib.error.HTTPError(
                url, 503, "oops", {}, io.BytesIO(b""))
        return (200, {"x-ratelimit-remaining": "9999"}, "{}")

    fake_urlopen(handler)
    status, headers, body = lit_fetch.http_get("https://api.openalex.org/works/W1")
    assert status == 200
    assert len(attempts) == 2


def test_retry_after_overrides_schedule():
    slept = []

    def handler(url):
        if len(handler.calls) == 0:
            handler.calls.append(url)
            raise lit_fetch.urllib.error.HTTPError(
                url, 429, "slow down", {"Retry-After": "7"}, io.BytesIO(b""))
        return (200, {"x-ratelimit-remaining": "99"}, "{}")

    handler.calls = []
    lit_fetch.time.sleep = slept.append
    fake_urlopen(handler)
    lit_fetch.http_get("https://api.openalex.org/works/W1")
    assert slept == [7.0]
    lit_fetch.time.sleep = lambda seconds: None


def test_budget_exhausted():
    def handler(url):
        return (200, {"x-ratelimit-remaining": "0"}, "{}")

    fake_urlopen(handler)
    try:
        lit_fetch.http_get("https://api.openalex.org/works/W1")
        raise AssertionError("expected BudgetExhausted")
    except lit_fetch.BudgetExhausted:
        pass


def test_http_404_propagates():
    calls = []

    def handler(url):
        calls.append(url)
        raise lit_fetch.urllib.error.HTTPError(url, 404, "nope", {}, io.BytesIO(b""))

    fake_urlopen(handler)
    try:
        lit_fetch.http_get("https://api.openalex.org/works/W1")
        raise AssertionError("expected HTTPError")
    except lit_fetch.urllib.error.HTTPError as e:
        assert e.code == 404
    assert len(calls) == 1


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
    test_url_builders,
    test_parse_envelope,
    test_retry_then_success,
    test_retry_after_overrides_schedule,
    test_budget_exhausted,
    test_http_404_propagates,
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
