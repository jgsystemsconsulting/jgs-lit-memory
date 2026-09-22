# Copyright (c) 2026 JG Systems Consulting Ltd. Source: https://github.com/jgsystemsconsulting/jgs-lit-memory. See LICENSE.
# SPDX-License-Identifier: MIT
"""Offline checks for lit_fetch.py. Plain asserts, no test framework.

Run: python test_lit_fetch.py   (exit 0 when all checks pass)
Network calls never leave the test process: every test that reaches the
network installs a fake via lit_fetch.http_get.
"""

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import urllib.parse

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "skills" / "lit-capture"))

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


# ---------------------------------------------------------------------------
# checks: briefs (schema, derivation, IO, verbs)
# ---------------------------------------------------------------------------

def agent_shell(**over):
    """Empty agent block with optional field overrides."""
    agent = lit_fetch.empty_agent_block()
    agent.update(over)
    return agent


def claim(cid, text="claim text", **over):
    """One valid claim object with overrides."""
    c = {"id": cid, "text": text, "type": "finding", "support": None,
         "basis": "abstract", "confidence": "med", "page": None,
         "section": None, "supports": [], "contradicts": []}
    c.update(over)
    return c


def empty_human():
    """Alias so the test reads like the spec block name."""
    return lit_fetch.empty_human_block()


def write_brief_file(lit, wid, brief):
    """Atomically write one brief JSON file into lit/briefs/."""
    lit_fetch.atomic_write(lit / "briefs" / (wid + ".json"),
                           json.dumps(brief, indent=2, ensure_ascii=False) + "\n")


def write_payload(tmp, payload):
    """Write a brief payload JSON file; returns its path as str."""
    p = pathlib.Path(tmp) / "payload.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_present_rules():
    assert lit_fetch.present_str("x") and lit_fetch.present_str(" x ")
    assert not lit_fetch.present_str("")
    assert not lit_fetch.present_str(None)
    assert not lit_fetch.present_str(5)
    assert lit_fetch.present_claims([claim("c1")])
    assert not lit_fetch.present_claims([claim("c1", text="")])
    assert not lit_fetch.present_claims([])
    assert not lit_fetch.present_claims(None)


def test_new_brief_shape():
    b = lit_fetch.new_brief("W1", "2026-09-16T00:00:00Z")
    assert b["id"] == "W1" and b["schema_version"] == 1
    assert b["status"] == "pending" and b["basis"] == "none"
    assert b["enriched_at"] is None and b["enrichment_source"] is None
    assert b["paper_captured_at"] == "2026-09-16T00:00:00Z"
    assert b["agent"] == lit_fetch.empty_agent_block()
    assert b["human"] == lit_fetch.empty_human_block()
    assert lit_fetch.new_brief("W1")["paper_captured_at"] is None


def test_paper_capture_stamp():
    assert lit_fetch.paper_capture_stamp(
        {"captured_at": "2026-09-16T00:00:00Z"}) == "2026-09-16T00:00:00Z"
    assert lit_fetch.paper_capture_stamp({}) is None
    assert lit_fetch.paper_capture_stamp({"captured_at": ""}) is None
    assert lit_fetch.paper_capture_stamp({"captured_at": None}) is None
    assert lit_fetch.paper_capture_stamp(None) is None


def test_derive_basis():
    A = agent_shell
    assert lit_fetch.derive_basis(A()) == "none"
    assert lit_fetch.derive_basis(A(claims=[claim("c1", text="")])) == "none"
    assert lit_fetch.derive_basis(A(claims=[claim("c1", basis="abstract")])) == "abstract"
    assert lit_fetch.derive_basis(A(claims=[claim("c1", basis="fulltext"),
                                            claim("c2", basis="fulltext")])) == "fulltext"
    assert lit_fetch.derive_basis(A(claims=[claim("c1", basis="abstract"),
                                            claim("c2", basis="fulltext")])) == "mixed"
    assert lit_fetch.derive_basis(A(claims=[claim("c1", basis="human"),
                                            claim("c2", basis="abstract")])) == "mixed"
    assert lit_fetch.derive_basis(A(claims=[claim("c1", basis="human")])) == "mixed"


def test_derive_status():
    A = agent_shell
    ids = {"c1", "c2"}
    assert lit_fetch.derive_status(A(), ids) == "pending"
    assert lit_fetch.derive_status(A(notes="a note"), ids) == "partial"
    full = A(overview="o", methods_tests="m", limits="l", why_it_matters="w",
             claims=[claim("c1"), claim("c2")])
    assert lit_fetch.derive_status(full, ids) == "ready"
    # thin fulltext fill that fails ready: partial, basis still fulltext
    thin = A(overview="o", claims=[claim("c1", basis="fulltext")])
    assert lit_fetch.derive_status(thin, {"c1"}) == "partial"
    assert lit_fetch.derive_basis(thin) == "fulltext"


def test_ready_content_union_targets():
    full = agent_shell(overview="o", methods_tests="m", limits="l",
                       why_it_matters="w",
                       claims=[claim("c1", supports=["h1"])])
    assert lit_fetch.ready_content(full, {"c1", "h1"})
    assert not lit_fetch.ready_content(full, {"c1"})   # dangling target blocks ready
    assert not lit_fetch.ready_content(agent_shell(overview="o"), {"c1"})


def test_validate_claim_rejects():
    lit_fetch.validate_claim(claim("c1"), "agent")   # no raise
    mutations = (
        lambda c: c.pop("id"),
        lambda c: c.pop("text"),
        lambda c: c.pop("type"),
        lambda c: c.pop("confidence"),
        lambda c: c.pop("basis"),
        lambda c: c.update(type="wrong"),
        lambda c: c.update(confidence="certain"),
        lambda c: c.update(basis="vibes"),
        lambda c: c.update(id=""),
        lambda c: c.update(text=5),
        lambda c: c.update(supports="c2"),
    )
    for mutate in mutations:
        bad = claim("c1")
        mutate(bad)
        try:
            lit_fetch.validate_claim(bad, "agent")
            raise AssertionError("expected BriefValidationError")
        except lit_fetch.BriefValidationError:
            pass


def test_validate_claim_lists_union():
    a = agent_shell(claims=[claim("c1"), claim("c2", supports=["c1"])])
    h = dict(empty_human(), claims=[claim("h1", basis="human")])
    assert lit_fetch.validate_claim_lists(a, h) == {"c1", "c2", "h1"}
    dup_h = dict(h, claims=[claim("c1", basis="human")])
    try:
        lit_fetch.validate_claim_lists(agent_shell(claims=[claim("c1")]), dup_h)
        raise AssertionError("expected BriefValidationError")
    except lit_fetch.BriefValidationError as e:
        assert "duplicate" in str(e)
    dang = agent_shell(claims=[claim("c1", contradicts=["ghost"])])
    try:
        lit_fetch.validate_claim_lists(dang, h)
        raise AssertionError("expected BriefValidationError")
    except lit_fetch.BriefValidationError as e:
        assert "ghost" in str(e)


def test_validate_brief_stub_and_ready():
    stub = lit_fetch.new_brief("W1")
    assert lit_fetch.validate_brief(stub) == []
    full = lit_fetch.new_brief("W1")
    full["agent"] = agent_shell(overview="o", methods_tests="m", limits="l",
                                why_it_matters="w",
                                claims=[claim("c1"), claim("c2")])
    full["status"] = "ready"
    full["basis"] = "abstract"
    full["enriched_at"] = "2026-09-18T00:00:00Z"
    full["enrichment_source"] = "agent"
    assert lit_fetch.validate_brief(full) == []
    bad = lit_fetch.new_brief("W1")
    bad["status"] = "ready"          # a stub derives pending; stored value lies
    assert any("status" in p for p in lit_fetch.validate_brief(bad))
    bad2 = lit_fetch.new_brief("W1")
    bad2["enrichment_source"] = "human"   # reserved value, never assigned in v1
    assert any("enrichment_source" in p for p in lit_fetch.validate_brief(bad2))
    bad3 = lit_fetch.new_brief("W1")
    bad3["agent"]["related_in_corpus"] = [{"id": "c1", "note": "claim id, not a paper"}]
    assert any("related_in_corpus" in p for p in lit_fetch.validate_brief(bad3))


def test_ensure_brief_stub_and_no_clobber():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        rec = lit_fetch.normalize_work(SAMPLE_PAYLOAD, seed=True, source="capture",
                                       captured_at="2026-09-16T00:00:00Z")
        lit_fetch.write_record(rec, lit)
        assert lit_fetch.ensure_brief_stub(lit, "W1111111111") is True
        brief = lit_fetch.load_brief(lit, "W1111111111")
        assert brief["status"] == "pending" and brief["basis"] == "none"
        assert brief["enriched_at"] is None and brief["enrichment_source"] is None
        assert brief["paper_captured_at"] == "2026-09-16T00:00:00Z"
        assert lit_fetch.validate_brief(brief) == []
        # second ensure is a no-op and never clobbers
        assert lit_fetch.ensure_brief_stub(lit, "W1111111111") is False
        assert lit_fetch.load_brief(lit, "W1111111111") == brief


def test_ensure_brief_stub_without_stamp():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        (lit / "papers" / "W1.json").write_text(
            json.dumps({"id": "W1"}), encoding="utf-8")   # no captured_at
        assert lit_fetch.ensure_brief_stub(lit, "W1") is True
        assert lit_fetch.load_brief(lit, "W1")["paper_captured_at"] is None


def test_first_write_makes_exactly_one_stub_and_refetch_keeps_brief():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        with contextlib.redirect_stdout(io.StringIO()):
            run = lit_fetch.Run()
            lit_fetch.write_one(SAMPLE_PAYLOAD, lit, run, True, "capture")
        assert run.written == 1 and run.failed == 0
        briefs = list((lit / "briefs").glob("*.json"))
        assert len(briefs) == 1 and briefs[0].stem == "W1111111111"
        # the agent enriches the stub, then the paper is re-fetched (skip path)
        brief = lit_fetch.load_brief(lit, "W1111111111")
        brief["agent"] = agent_shell(overview="enriched")
        write_brief_file(lit, "W1111111111", brief)
        with contextlib.redirect_stdout(io.StringIO()):
            run2 = lit_fetch.Run()
            lit_fetch.write_one(SAMPLE_PAYLOAD, lit, run2, True, "capture")
        assert run2.skipped == 1 and run2.written == 0
        assert lit_fetch.load_brief(lit, "W1111111111")["agent"]["overview"] == "enriched"


def test_stub_failure_surfaces():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"

        def boom(lit_dir, wid):
            raise OSError("briefs path unwritable")

        prev = lit_fetch.ensure_brief_stub
        lit_fetch.ensure_brief_stub = boom
        err = io.StringIO()
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                with contextlib.redirect_stderr(err):
                    run = lit_fetch.Run()
                    lit_fetch.write_one(SAMPLE_PAYLOAD, lit, run, True, "capture")
        finally:
            lit_fetch.ensure_brief_stub = prev
        assert run.written == 1            # paper write stands
        assert run.failed == 1             # stub failure is a counted failure
        assert run.failures[0][0] == "brief-stub:W1111111111"
        assert "brief_stub_failed" in err.getvalue()


def test_remap_brief_moves_and_merges():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        # case 1: only the old brief exists -> moves to the new id
        old = lit_fetch.new_brief("W9999999999")
        old["agent"] = agent_shell(overview="old notes")
        write_brief_file(lit, "W9999999999", old)
        lit_fetch.remap_brief(lit, "W9999999999", "W1111111111")
        assert not (lit / "briefs" / "W9999999999.json").exists()
        moved = lit_fetch.load_brief(lit, "W1111111111")
        assert moved["id"] == "W1111111111"
        assert moved["agent"]["overview"] == "old notes"
        # case 2: both exist -> newer mtime agent wins; empty human slots fill from loser
        winner = lit_fetch.new_brief("W1111111111")
        winner["agent"] = agent_shell(overview="newer agent")
        winner["human"]["notes"] = "winner notes"  # conflict keeps winner's notes
        write_brief_file(lit, "W1111111111", winner)
        loser = lit_fetch.new_brief("W9999999999")
        loser["human"]["overview"] = "human note to keep"
        loser["human"]["notes"] = "conflicting human note"
        write_brief_file(lit, "W9999999999", loser)
        # make loser older so winner's mtime is newer
        os.utime(lit / "briefs" / "W9999999999.json", (1000000000, 1000000000))
        lit_fetch.remap_brief(lit, "W9999999999", "W1111111111")
        assert not (lit / "briefs" / "W9999999999.json").exists()
        merged = lit_fetch.load_brief(lit, "W1111111111")
        assert merged["agent"]["overview"] == "newer agent"   # newer mtime wins
        assert merged["human"]["overview"] == "human note to keep"  # filled from loser
        assert merged["human"]["notes"] == "winner notes"     # conflict keeps winner


def test_remap_brief_noop_when_old_missing():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        lit_fetch.remap_brief(lit, "W8888888888", "W1111111111")   # no raise
        assert lit_fetch.load_brief(lit, "W1111111111") is None


def test_capture_merge_remaps_brief():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        stale = lit_fetch.new_brief("W9999999999")
        stale["agent"] = agent_shell(overview="pre-merge agent")
        write_brief_file(lit, "W9999999999", stale)

        def handler(url):
            assert "/works/W9999999999?" in url
            return (200, {"x-ratelimit-remaining": "9999"},
                    json.dumps(SAMPLE_PAYLOAD))   # canonical W1111111111

        with fake_http(handler):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                run = lit_fetch.Run()
                lit_fetch.capture_identifier("W9999999999", True, lit, None, run)
        assert "merge: W9999999999 -> W1111111111" in out.getvalue()
        assert run.failed == 0
        assert not (lit / "briefs" / "W9999999999.json").exists()
        brief = lit_fetch.load_brief(lit, "W1111111111")
        assert brief["agent"]["overview"] == "pre-merge agent"   # moved, not clobbered
        assert lit_fetch.load_aliases(lit) == {"W9999999999": "W1111111111"}
        # operations via the old id resolve onto the single canonical file
        payload = {"agent": agent_shell(overview="written via old id")}
        with contextlib.redirect_stdout(io.StringIO()):
            assert lit_fetch.verb_brief_write(
                lit, "W9999999999", write_payload(tmp, payload), False) == 0
        assert not (lit / "briefs" / "W9999999999.json").exists()
        assert lit_fetch.load_brief(
            lit, "W1111111111")["agent"]["overview"] == "written via old id"


def test_batch_merge_remaps_brief():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        stale = lit_fetch.new_brief("W9999999999")
        stale["human"]["notes"] = "keep me"
        write_brief_file(lit, "W9999999999", stale)

        def handler(url):
            return (200, {"x-ratelimit-remaining": "9"}, envelope([SAMPLE_PAYLOAD]))

        with fake_http(handler):
            with contextlib.redirect_stdout(io.StringIO()):
                run = lit_fetch.Run()
                lit_fetch.verb_ids("W9999999999", lit, None, False, run)
        assert run.written == 1 and run.failed == 0
        assert not (lit / "briefs" / "W9999999999.json").exists()
        assert lit_fetch.load_brief(lit, "W1111111111")["human"]["notes"] == "keep me"


def test_enrich_pending_listing():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_enrich_pending(lit) == 0
        assert out.getvalue() == ""          # empty corpus: nothing, exit 0
        lit_fetch.ensure_corpus(lit)
        write_brief_file(lit, "W1", lit_fetch.new_brief("W1"))
        partial = lit_fetch.new_brief("W2")
        partial["status"] = "partial"
        partial["agent"] = agent_shell(overview="o")
        write_brief_file(lit, "W2", partial)
        ready = lit_fetch.new_brief("W3")
        ready["status"] = "ready"
        write_brief_file(lit, "W3", ready)
        (lit / "briefs" / "W4.json").write_text("{corrupt", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_enrich_pending(lit) == 0
        rows = [json.loads(line) for line in out.getvalue().splitlines()]
        assert [(r["id"], r["status"]) for r in rows] == [
            ("W1", "pending"), ("W2", "partial"), ("W4", "invalid")]


def test_brief_status_counts_and_detail():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        write_brief_file(lit, "W1", lit_fetch.new_brief("W1"))
        partial = lit_fetch.new_brief("W2")
        partial["status"] = "partial"
        write_brief_file(lit, "W2", partial)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_brief_status(lit, "all") == 0
        text = out.getvalue()
        assert "briefs=2" in text
        assert "status pending=1" in text and "status partial=1" in text
        assert "status ready=0" in text and "status stale=0" in text
        # both fixture briefs keep basis none until a write derives a new basis
        assert "basis none=2" in text
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_brief_status(lit, "W1") == 0
        assert '"id": "W1"' in out.getvalue()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert lit_fetch.verb_brief_status(lit, "W404") == 1


def test_brief_check_ok_and_invalid():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        write_brief_file(lit, "W1", lit_fetch.new_brief("W1"))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_brief_check(lit, "all") == 0
        assert "OK W1" in out.getvalue()
        bad = lit_fetch.new_brief("W2")
        bad["status"] = "banana"
        write_brief_file(lit, "W2", bad)
        (lit / "briefs" / "W3.json").write_text("not json", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_brief_check(lit, "all") == 1
        assert "FAIL W2" in out.getvalue() and "FAIL W3" in out.getvalue()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_brief_check(lit, "W1") == 0
        assert "OK W1" in out.getvalue()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert lit_fetch.verb_brief_check(lit, "W404") == 1


def test_brief_cli_verbs_main():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        assert lit_fetch.main(["--enrich-pending", "--dir", str(lit)]) == 0
        try:
            lit_fetch.main(["--status", "--enrich-pending", "--dir", str(lit)])
            raise AssertionError("expected usage error")
        except SystemExit as e:
            assert e.code == 2


def test_brief_write_happy_and_derived_fields():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        rec = lit_fetch.normalize_work(SAMPLE_PAYLOAD, seed=True, source="capture",
                                       captured_at="2026-09-16T00:00:00Z")
        lit_fetch.write_record(rec, lit)
        payload = {"agent": agent_shell(
            overview="o", methods_tests="m", limits="l", why_it_matters="w",
            claims=[claim("c1"), claim("c2", supports=["c1"])])}
        payload["status"] = "ready"       # ignored: script derives
        payload["basis"] = "fulltext"     # ignored: script derives
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = lit_fetch.verb_brief_write(lit, "W1111111111",
                                            write_payload(tmp, payload), False)
        assert rc == 0
        brief = lit_fetch.load_brief(lit, "W1111111111")
        assert brief["status"] == "ready" and brief["basis"] == "abstract"
        assert brief["enrichment_source"] == "agent"
        assert brief["enriched_at"] and brief["enriched_at"].endswith("Z")
        assert brief["paper_captured_at"] == "2026-09-16T00:00:00Z"
        assert brief["id"] == "W1111111111" and brief["schema_version"] == 1
        assert lit_fetch.validate_brief(brief) == []


def test_brief_write_preserves_human():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        (lit / "papers" / "W1.json").write_text(
            json.dumps({"id": "W1", "captured_at": "2026-09-16T00:00:00Z"}),
            encoding="utf-8")
        seeded = lit_fetch.new_brief("W1")
        seeded["human"]["notes"] = "human note"
        seeded["human"]["claims"] = [claim("h1", basis="human")]
        write_brief_file(lit, "W1", seeded)
        # payload omits human entirely: preserved
        payload = {"agent": agent_shell(overview="o")}
        assert lit_fetch.verb_brief_write(
            lit, "W1", write_payload(tmp, payload), False) == 0
        brief = lit_fetch.load_brief(lit, "W1")
        assert brief["human"]["notes"] == "human note"
        assert brief["human"]["claims"][0]["id"] == "h1"
        assert brief["enrichment_source"] == "agent"
        # payload alters human without --human: still preserved
        payload["human"] = {"notes": "clobber attempt"}
        assert lit_fetch.verb_brief_write(
            lit, "W1", write_payload(tmp, payload), False) == 0
        assert lit_fetch.load_brief(lit, "W1")["human"]["notes"] == "human note"
        # --human replaces
        assert lit_fetch.verb_brief_write(
            lit, "W1", write_payload(tmp, payload), True) == 0
        brief = lit_fetch.load_brief(lit, "W1")
        assert brief["human"]["notes"] == "clobber attempt"
        assert brief["human"]["claims"] == []
        assert brief["enrichment_source"] == "mixed"
        # --human without a payload human object rejects
        del payload["human"]
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert lit_fetch.verb_brief_write(
                lit, "W1", write_payload(tmp, payload), True) == 1


def test_brief_write_rejections_leave_file_untouched():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        (lit / "papers" / "W1.json").write_text(
            json.dumps({"id": "W1", "captured_at": "2026-09-16T00:00:00Z"}),
            encoding="utf-8")
        write_brief_file(lit, "W1", lit_fetch.new_brief("W1"))
        before = (lit / "briefs" / "W1.json").read_text(encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            # payload without agent
            assert lit_fetch.verb_brief_write(
                lit, "W1", write_payload(tmp, {"human": {"notes": "x"}}), False) == 1
            # agent not an object
            assert lit_fetch.verb_brief_write(
                lit, "W1", write_payload(tmp, {"agent": "prose"}), False) == 1
            # dangling support target
            assert lit_fetch.verb_brief_write(
                lit, "W1",
                write_payload(tmp, {"agent": agent_shell(
                    claims=[claim("c1", supports=["ghost"])])}), False) == 1
            # duplicate claim id across the union
            dup = {"agent": agent_shell(claims=[claim("c1")]),
                   "human": dict(lit_fetch.empty_human_block(),
                                 claims=[claim("c1", basis="human")])}
            assert lit_fetch.verb_brief_write(
                lit, "W1", write_payload(tmp, dup), True) == 1
            # no resolvable paper record
            assert lit_fetch.verb_brief_write(
                lit, "W404",
                write_payload(tmp, {"agent": agent_shell()}), False) == 1
        assert "ghost" in err.getvalue()
        assert (lit / "briefs" / "W1.json").read_text(encoding="utf-8") == before
        assert not list((lit / "briefs").glob("*.tmp"))


def test_brief_write_status_levels():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        (lit / "papers" / "W1.json").write_text(
            json.dumps({"id": "W1", "captured_at": None}), encoding="utf-8")
        # empty shell -> pending even when the payload claims ready
        assert lit_fetch.verb_brief_write(
            lit, "W1",
            write_payload(tmp, {"agent": agent_shell(), "status": "ready"}),
            False) == 0
        brief = lit_fetch.load_brief(lit, "W1")
        assert brief["status"] == "pending" and brief["basis"] == "none"
        assert brief["paper_captured_at"] is None
        assert brief["enriched_at"] is not None   # a write always stamps
        # thin fulltext fill -> partial, basis fulltext
        thin = {"agent": agent_shell(overview="o",
                                     claims=[claim("c1", basis="fulltext")])}
        assert lit_fetch.verb_brief_write(
            lit, "W1", write_payload(tmp, thin), False) == 0
        brief = lit_fetch.load_brief(lit, "W1")
        assert brief["status"] == "partial" and brief["basis"] == "fulltext"
        # full fill -> ready
        full = {"agent": agent_shell(overview="o", methods_tests="m", limits="l",
                                     why_it_matters="w",
                                     claims=[claim("c1"),
                                             claim("c2", supports=["c1"])])}
        assert lit_fetch.verb_brief_write(
            lit, "W1", write_payload(tmp, full), False) == 0
        brief = lit_fetch.load_brief(lit, "W1")
        assert brief["status"] == "ready" and brief["basis"] == "abstract"


def test_brief_restub_keeps_human_and_stamp():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        seeded = lit_fetch.new_brief("W1", "2026-09-16T00:00:00Z")
        seeded["status"] = "ready"
        seeded["basis"] = "abstract"
        seeded["enriched_at"] = "2026-09-18T00:00:00Z"
        seeded["enrichment_source"] = "agent"
        seeded["agent"] = agent_shell(overview="o")
        seeded["human"]["notes"] = "human note"
        write_brief_file(lit, "W1", seeded)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_brief_restub(lit, "W1") == 0
        brief = lit_fetch.load_brief(lit, "W1")
        assert brief["status"] == "pending" and brief["basis"] == "none"
        assert brief["enriched_at"] is None and brief["enrichment_source"] is None
        assert brief["agent"] == lit_fetch.empty_agent_block()
        assert brief["human"]["notes"] == "human note"
        assert brief["paper_captured_at"] == "2026-09-16T00:00:00Z"
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert lit_fetch.verb_brief_restub(lit, "W2") == 1   # no brief


def test_brief_write_cli_flags():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        (lit / "papers" / "W1.json").write_text(
            json.dumps({"id": "W1", "captured_at": None}), encoding="utf-8")
        payload = write_payload(tmp, {"agent": agent_shell(overview="o")})
        with contextlib.redirect_stdout(io.StringIO()):
            assert lit_fetch.main(["--brief-write", "--id", "W1",
                                   "--file", payload, "--dir", str(lit)]) == 0
        assert lit_fetch.load_brief(lit, "W1")["status"] == "partial"
        with contextlib.redirect_stdout(io.StringIO()):
            assert lit_fetch.main(["--brief-restub", "--id", "W1",
                                   "--dir", str(lit)]) == 0
        assert lit_fetch.load_brief(lit, "W1")["status"] == "pending"
        try:   # usage error: --brief-write without --file
            lit_fetch.main(["--brief-write", "--id", "W1", "--dir", str(lit)])
            raise AssertionError("expected exit 2")
        except SystemExit as e:
            assert e.code == 2


def test_render_index():
    text = lit_fetch.render_index(3, 10, 5, 1, "2026-09-16T00:00:00Z")
    assert "| 3 |" in text and "| 10 |" in text and "| 5 |" in text and "| 1 |" in text
    assert "last-synced: 2026-09-16T00:00:00Z" in text
    assert "biased" in text and "CC0" in text
    assert "\u2014" not in lit_fetch.INDEX_TEMPLATE
    assert "\u2014" not in text
    assert "__" not in text


# ---------------------------------------------------------------------------
# checks: write model (offline, temp dirs)
# ---------------------------------------------------------------------------

def test_atomic_write_and_corpus_init():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        assert (lit / "papers").is_dir()
        assert (lit / "graph").is_dir()
        assert (lit / "findings").is_dir()
        assert (lit / "briefs").is_dir()
        lit_fetch.atomic_write(lit / "graph" / "edges.jsonl", "x\n")
        assert (lit / "graph" / "edges.jsonl").read_text(encoding="utf-8") == "x\n"
        assert not list(lit.rglob("*.tmp"))


def test_edges_and_aliases_roundtrip():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        lit_fetch.write_edges(lit, [{"source": "W1", "target": "W2"}])
        lit_fetch.write_edges(lit, [{"source": "W1", "target": "W2"},
                                    {"source": "W2", "target": "W3"}])
        assert lit_fetch.load_edges(lit) == [
            {"source": "W1", "target": "W2"},
            {"source": "W2", "target": "W3"},
        ]
        # alias healing on write: existing AND new endpoints remap, union dedupes
        lit_fetch.save_aliases(lit, {"W3": "W5", "W9": "W1"})
        lit_fetch.write_edges(lit, [{"source": "W5", "target": "W1"},
                                    {"source": "W9", "target": "W2"}])  # W9 -> W1
        assert lit_fetch.load_edges(lit) == [
            {"source": "W1", "target": "W2"},   # existing + new (W9,W2) remapped
            {"source": "W2", "target": "W5"},   # existing W3 remapped
            {"source": "W5", "target": "W1"},
        ]


def test_index_and_status_counts():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        rec = lit_fetch.normalize_work(SAMPLE_PAYLOAD, seed=True, source="capture",
                                       captured_at="2026-09-16T00:00:00Z")
        lit_fetch.write_record(rec, lit)
        lit_fetch.write_edges(lit, lit_fetch.edges_of([rec]))
        lit_fetch.regenerate_index(lit)
        index = (lit / "SKILL.md").read_text(encoding="utf-8")
        assert "| 1 |" in index
        assert "boundary" in index.lower()
        assert "last-synced: " in index
        assert lit_fetch.boundary_nodes(lit) == {"W2222222222", "W3333333333"}
        assert lit_fetch.count_inbox(lit) == 0
        (lit / "inbox.jsonl").write_text('{"ref": "W1"}\n{"ref": "W2"}\n',
                                         encoding="utf-8")
        assert lit_fetch.count_inbox(lit) == 2


def test_run_summary():
    run = lit_fetch.Run()
    run.fail("W1", "404")
    assert run.summary() == "written=0 skipped=0 failed=1\nfailed: W1 (404)"


# ---------------------------------------------------------------------------
# fakes: the network seam (order-safe: always restore after the with-body)
# ---------------------------------------------------------------------------

def envelope(records):
    return json.dumps({"meta": {"count": len(records)}, "results": records})


REAL_HTTP_GET = lit_fetch.http_get
REAL_URLOPEN = lit_fetch.urllib.request.urlopen


@contextlib.contextmanager
def fake_http(handler):
    """Wrap a handler(url) -> (status, headers, body) as lit_fetch.http_get.
    Restores the previous http_get on exit so checks stay order-safe."""
    calls = []

    def get(url, timeout=30):
        calls.append(url)
        return handler(url)

    get.calls = calls
    prev = lit_fetch.http_get
    lit_fetch.http_get = get
    try:
        yield get
    finally:
        lit_fetch.http_get = prev


@contextlib.contextmanager
def fake_urlopen(handler):
    """Patch urllib.request.urlopen UNDER the real lit_fetch.http_get, for
    tests that exercise retry/backoff logic itself. handler(url) returns
    (status, headers, body_text) or raises. Restores http_get and urlopen
    on exit. Yields the seen-URLs list."""
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

    prev_http = lit_fetch.http_get
    prev_urlopen = lit_fetch.urllib.request.urlopen
    lit_fetch.http_get = REAL_HTTP_GET
    lit_fetch.urllib.request.urlopen = urlopen
    try:
        yield calls
    finally:
        lit_fetch.http_get = prev_http
        lit_fetch.urllib.request.urlopen = prev_urlopen


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

    with fake_urlopen(handler):
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
    try:
        with fake_urlopen(handler):
            lit_fetch.http_get("https://api.openalex.org/works/W1")
        assert slept == [7.0]
    finally:
        lit_fetch.time.sleep = lambda seconds: None


def test_budget_exhausted():
    """http_get never raises on remaining=0: returns the 200 tuple so the
    caller can finish the current chunk and stop before the next call."""
    def handler(url):
        return (200, {"x-ratelimit-remaining": "0"}, '{"ok": true}')

    with fake_urlopen(handler):
        status, headers, body = lit_fetch.http_get("https://api.openalex.org/works/W1")
    assert status == 200
    assert headers.get("x-ratelimit-remaining") == "0"
    assert body == '{"ok": true}'


def test_http_404_propagates():
    calls = []

    def handler(url):
        calls.append(url)
        raise lit_fetch.urllib.error.HTTPError(url, 404, "nope", {}, io.BytesIO(b""))

    with fake_urlopen(handler):
        try:
            lit_fetch.http_get("https://api.openalex.org/works/W1")
            raise AssertionError("expected HTTPError")
        except lit_fetch.urllib.error.HTTPError as e:
            assert e.code == 404
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# checks: singleton verbs (offline through the fake)
# ---------------------------------------------------------------------------

def test_singleton_capture_and_alias():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"

        def handler(url):
            assert "/works/W9999999999?" in url
            return (200, {"x-ratelimit-remaining": "9999"},
                    json.dumps(SAMPLE_PAYLOAD))   # canonical id W1111111111

        with fake_http(handler):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                run = lit_fetch.Run()
                lit_fetch.capture_identifier("W9999999999", True, lit, None, run)
            assert run.written == 1 and run.skipped == 0 and run.failed == 0
            assert "merge: W9999999999 -> W1111111111" in out.getvalue()
            assert (lit / "papers" / "W1111111111.json").exists()
            assert lit_fetch.load_aliases(lit) == {"W9999999999": "W1111111111"}
            assert lit_fetch.load_edges(lit)[0]["source"] == "W1111111111"
            assert "last-synced: " in (lit / "SKILL.md").read_text(encoding="utf-8")
            # re-run: skip-if-exists, no rewrite, still counted
            run2 = lit_fetch.Run()
            with contextlib.redirect_stdout(io.StringIO()):
                lit_fetch.capture_identifier("W9999999999", True, lit, None, run2)
            assert run2.skipped == 1 and run2.written == 0 and run2.failed == 0


def test_title_verb_verification_gate():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"

        def handler(url):
            assert "search=" in url and "per-page=5" in url
            return (200, {"x-ratelimit-remaining": "9999"}, envelope(CANDIDATES))

        with fake_http(handler):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                run = lit_fetch.Run()
                wrote = lit_fetch.verb_title("A Sample Study of Graphs and Edges",
                                             None, None, lit, None, run)
            assert wrote is False
            assert run.written == 0 and run.failed == 1
            assert "top candidates" in out.getvalue()
            assert not (lit / "papers" / "W1111111111.json").exists()
            # surname disambiguates: writes one record
            run2 = lit_fetch.Run()
            with contextlib.redirect_stdout(io.StringIO()):
                wrote = lit_fetch.verb_title("A Sample Study of Graphs and Edges",
                                             "Doe", None, lit, None, run2)
            assert wrote is True and run2.written == 1
            assert (lit / "papers" / "W1111111111.json").exists()


# ---------------------------------------------------------------------------
# checks: batch and inbox verbs (offline through the fake)
# ---------------------------------------------------------------------------

def test_batch_two_chunks_and_keyless_warning():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        ids = ["W%d" % (9000000000 + i) for i in range(1, 151)]
        calls = []

        def handler(url):
            calls.append(url)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            wids = q["filter"][0].split(":")[1].split("|")
            return (200, {"x-ratelimit-remaining": "9999"},
                    envelope([make_payload(w) for w in wids]))

        err = io.StringIO()
        with fake_http(handler):
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                run = lit_fetch.Run()
                lit_fetch.verb_ids("|".join(ids), lit, None, False, run)
        assert len(calls) == 2                       # 100 + 50
        assert run.written == 150 and run.skipped == 0 and run.failed == 0
        assert "keyless" in err.getvalue()           # warning before the budgeted call
        assert len(list((lit / "papers").glob("*.json"))) == 150
        assert "last-synced: " in (lit / "SKILL.md").read_text(encoding="utf-8")


def test_batch_skips_and_reports_absent():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        lit_fetch.write_record(
            lit_fetch.normalize_work(make_payload("W9000000001"), seed=True,
                                     source="capture",
                                     captured_at="2026-09-16T00:00:00Z"), lit)

        def handler(url):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            wids = q["filter"][0].split(":")[1].split("|")
            return (200, {"x-ratelimit-remaining": "9"},
                    envelope([make_payload(w) for w in wids if w != "W9000000002"]))

        with fake_http(handler):
            with contextlib.redirect_stdout(io.StringIO()):
                run = lit_fetch.Run()
                lit_fetch.verb_ids("W9000000001|W9000000002|W9000000003",
                                   lit, None, False, run)
        assert run.skipped == 1            # W9000000001 already in corpus, never fetched
        assert run.written == 1            # W9000000003
        assert run.failed == 1             # W9000000002 absent from response
        assert "404" in run.failures[0][1]
        assert "use --openalex" in run.failures[0][1]


def test_batch_single_id_merge():
    """R3b: single-id chunk whose response has exactly one different canonical
    is treated as a 301 merge (alias + write under the canonical id)."""
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"

        def handler(url):
            # filter asked for W9999999999; OpenAlex returns the merged canonical
            return (200, {"x-ratelimit-remaining": "9"},
                    envelope([SAMPLE_PAYLOAD]))   # id W1111111111

        out = io.StringIO()
        with fake_http(handler):
            with contextlib.redirect_stdout(out):
                run = lit_fetch.Run()
                lit_fetch.verb_ids("W9999999999", lit, None, False, run)
        assert run.written == 1 and run.failed == 0
        assert "merge: W9999999999 -> W1111111111" in out.getvalue()
        assert lit_fetch.load_aliases(lit) == {"W9999999999": "W1111111111"}
        assert (lit / "papers" / "W1111111111.json").exists()
        assert not (lit / "papers" / "W9999999999.json").exists()
        assert "last-synced: " in (lit / "SKILL.md").read_text(encoding="utf-8")


def test_budget_abort_keeps_completed_writes():
    """Chunk 1 processes (100 written); remaining 0 seen; chunk 2 never called;
    run gains one budget failure; all files valid JSON; index regenerated."""
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        ids = ["W%d" % (9100000000 + i) for i in range(1, 151)]
        calls = []

        def handler(url):
            calls.append(url)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
            wids = q["filter"][0].split(":")[1].split("|")
            # first (and only) chunk returns remaining 0 after a full body
            return (200, {"x-ratelimit-remaining": "0"},
                    envelope([make_payload(w) for w in wids]))

        out = io.StringIO()
        with fake_http(handler):
            with contextlib.redirect_stdout(out):
                run = lit_fetch.Run()
                lit_fetch.verb_ids("|".join(ids), lit, None, False, run)
        assert len(calls) == 1                 # chunk 2 never called
        assert run.written == 100
        assert run.failed == 1
        assert run.failures[0][0] == "50 remaining id(s)"
        assert "budget exhausted" in run.failures[0][1]
        assert "budget exhausted; completed writes stand" in out.getvalue()
        assert len(list((lit / "papers").glob("*.json"))) == 100
        for p in (lit / "papers").glob("*.json"):
            json.loads(p.read_text(encoding="utf-8"))
        assert "last-synced: " in (lit / "SKILL.md").read_text(encoding="utf-8")


def test_inbox_triage_flow():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        lines = [
            {"ref": "W1111111111", "title": "", "note": "seed paper",
             "added_at": "2026-09-16T10:00:00Z"},
            {"ref": "doi:10.1234/Sample.2021", "note": "dup of seed by doi",
             "added_at": "2026-09-16T10:01:00Z"},
            {"ref": "not a ref", "note": "malformed",
             "added_at": "2026-09-16T10:02:00Z"},
            {"ref": "title:A Brand New Paper", "title": "A Brand New Paper",
             "author": "Newman", "year": "2024", "note": "to resolve",
             "added_at": "2026-09-16T10:03:00Z"},
        ]
        (lit / "inbox.jsonl").write_text(
            "".join(json.dumps(e) + "\n" for e in lines), encoding="utf-8")

        def handler(url):
            if "search=" in url:
                cand = make_payload("W4444444444")
                cand["display_name"] = "A Brand New Paper"
                cand["publication_year"] = 2024
                cand["authorships"] = [{"author": {"display_name": "Al Newman"}}]
                return (200, {"x-ratelimit-remaining": "9999"}, envelope([cand]))
            return (200, {"x-ratelimit-remaining": "9999"},
                    json.dumps(SAMPLE_PAYLOAD))

        with fake_http(handler):
            with contextlib.redirect_stdout(io.StringIO()):
                run = lit_fetch.Run()
                lit_fetch.verb_inbox(lit, None, run)
            assert run.written == 2         # wid singleton + verified title search
            assert run.skipped == 1         # doi entry resolves to the existing canonical
            assert run.failed == 1          # unparseable ref stays queued
            remaining = [json.loads(l)
                         for l in (lit / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
                         if l.strip()]
            assert len(remaining) == 1 and remaining[0]["ref"] == "not a ref"
            assert "last_error" in remaining[0]
            assert (lit / "papers" / "W1111111111.json").exists()
            assert (lit / "papers" / "W4444444444.json").exists()
            # re-run: nothing left to promote, malformed entry still queued
            with contextlib.redirect_stdout(io.StringIO()):
                run2 = lit_fetch.Run()
                lit_fetch.verb_inbox(lit, None, run2)
            assert run2.written == 0 and run2.failed == 1
            # a later duplicate of a promoted paper dedupes against the corpus
            extra = {"ref": "title:A Sample Study of Graphs and Edges",
                     "title": "A Sample Study of Graphs and Edges",
                     "note": "dup by title", "added_at": "2026-09-16T11:00:00Z"}
            with (lit / "inbox.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps(extra) + "\n")
            with contextlib.redirect_stdout(io.StringIO()):
                run3 = lit_fetch.Run()
                lit_fetch.verb_inbox(lit, None, run3)
            assert run3.skipped == 1 and run3.written == 0 and run3.failed == 1
            lines_left = [l for l in (lit / "inbox.jsonl").read_text(encoding="utf-8").splitlines()
                          if l.strip()]
            assert len(lines_left) == 1     # only the malformed entry remains


# ---------------------------------------------------------------------------
# checks: status and check verbs
# ---------------------------------------------------------------------------

def test_status_never_before_index():
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        rec = lit_fetch.normalize_work(SAMPLE_PAYLOAD, seed=True, source="capture",
                                       captured_at="2026-09-16T00:00:00Z")
        lit_fetch.write_record(rec, lit)
        lit_fetch.write_edges(lit, lit_fetch.edges_of([rec]))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            assert lit_fetch.verb_status(lit) == 0
        text = out.getvalue()
        assert "papers=1 edges=2 boundary=2 inbox_pending=0" in text
        assert "last-synced: never" in text
        # after a regeneration the real timestamp shows up
        lit_fetch.regenerate_index(lit)
        out2 = io.StringIO()
        with contextlib.redirect_stdout(out2):
            lit_fetch.verb_status(lit)
        assert "last-synced: never" not in out2.getvalue()
        assert "last-synced: 20" in out2.getvalue()   # a real ISO timestamp


def test_check_forms_fake():
    def handler(url):
        if "search=" in url:
            return (200, {"x-ratelimit-remaining": "9"}, envelope([]))
        if "ids.openalex" in url:
            return (200, {"x-ratelimit-remaining": "9"},
                    envelope([make_payload("W2741809807")]))
        if "/works/W2741809807?" in url:
            return (200, {"x-ratelimit-remaining": "9"},
                    json.dumps(make_payload("W2741809807")))
        return (200, {"x-ratelimit-remaining": "9"}, json.dumps(SAMPLE_PAYLOAD))

    out = io.StringIO()
    with fake_http(handler):
        with contextlib.redirect_stdout(out):
            rc = lit_fetch.verb_check(None)
    assert rc == 0
    assert out.getvalue().count("OK") == 4
    assert "FAIL" not in out.getvalue()


# ---------------------------------------------------------------------------
# checks: error path (api_key redaction and the budget stop; offline)
# ---------------------------------------------------------------------------

def test_backoff_exhausted_redacts_key():
    """T1. The class owns the redaction: args, str, and repr are all safe,
    and the real retry loop raises the redacted form after MAX_ATTEMPTS."""
    exc = lit_fetch.BackoffExhausted(
        "https://api.openalex.org/works?search=x&api_key=SECRET123&select=id")
    for text in (str(exc), repr(exc), exc.args[0]):
        assert "SECRET123" not in text
    assert "api_key=REDACTED" in str(exc)
    assert "search=x" in str(exc)
    assert "backoff exhausted after 5 attempts" in str(exc)
    keyless = "https://api.openalex.org/works?search=x&select=id"
    assert str(lit_fetch.BackoffExhausted(keyless)) == (
        "backoff exhausted after 5 attempts: " + keyless)

    def handler(url):
        raise lit_fetch.urllib.error.HTTPError(
            url, 503, "Service Unavailable", {}, io.BytesIO(b""))

    with fake_urlopen(handler) as calls:
        try:
            lit_fetch.http_get(lit_fetch.work_url("W1111111111", "SECRET123"))
            raise AssertionError("expected BackoffExhausted")
        except lit_fetch.BackoffExhausted as exc:
            assert "SECRET123" not in str(exc)
            assert "api_key=REDACTED" in str(exc)
    assert len(calls) == lit_fetch.MAX_ATTEMPTS
    assert all("api_key=SECRET123" in u for u in calls)   # wire format unchanged


def test_inbox_keyed_backoff_writes_no_key():
    """T2. A keyed inbox run that exhausts backoff on one entry queues it with
    a redacted, descriptive last_error; the same class escaping to the main
    outer catch prints a redacted error line and exits 1."""
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        entry = {"ref": "title:A Brand New Paper", "title": "A Brand New Paper",
                 "note": "to resolve", "added_at": "2026-09-22T10:00:00Z"}
        (lit / "inbox.jsonl").write_text(json.dumps(entry) + "\n", encoding="utf-8")

        def handler(url):
            raise lit_fetch.BackoffExhausted(url)   # url carries api_key=SECRET123

        out = io.StringIO()
        with fake_http(handler):
            with contextlib.redirect_stdout(out):
                run = lit_fetch.Run()
                lit_fetch.verb_inbox(lit, "SECRET123", run)
        assert run.failed == 1 and run.written == 0
        text = (lit / "inbox.jsonl").read_text(encoding="utf-8")
        assert "SECRET123" not in text
        assert "api_key=REDACTED" in text and "backoff exhausted" in text
        remaining = [json.loads(l) for l in text.splitlines() if l.strip()]
        assert len(remaining) == 1 and remaining[0]["ref"] == "title:A Brand New Paper"
        assert remaining[0]["last_error"].startswith("backoff exhausted after 5 attempts: ")
        assert "SECRET123" not in run.summary()
        assert "SECRET123" not in out.getvalue()
        # the same class escaping verb_ids to the main outer catch (:1480)
        out2 = io.StringIO()
        with fake_http(handler):
            with contextlib.redirect_stdout(out2):
                rc = lit_fetch.main(["--ids", "W9000000001", "--dir", str(lit),
                                     "--api-key", "SECRET123"])
        assert rc == 1
        assert "error: backoff exhausted after 5 attempts: " in out2.getvalue()
        assert "api_key=REDACTED" in out2.getvalue()
        assert "SECRET123" not in out2.getvalue()


def _title_search_handler(headers):
    """fake_http handler for verified title search: parses search= from the
    URL, answers with the one make_payload whose name matches, and attaches
    the given headers to every response."""
    def handler(url):
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        wid = q["search"][0].split()[-1]          # "Paper W7000000001" -> W-id
        return (200, dict(headers), envelope([make_payload(wid)]))
    return handler


def test_missing_remaining_header_does_not_stop():
    """T4. (a) No header: verb_title returns True and verb_inbox drains two
    entries. (b) Decision 4: a free singleton ignores remaining 0. (c)
    Decision 3: singleton --title on remaining 0 writes the record, exits 1
    with the budget line, and a re-run skips it as already present."""
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        # (a) headers {} never trips the stop
        with fake_http(_title_search_handler({})):
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                run = lit_fetch.Run()
                wrote = lit_fetch.verb_title("Paper W7000000010", None, None,
                                             lit, None, run)
        assert wrote is True and run.written == 1
        entries = [
            {"ref": "title:Paper W7000000011", "title": "Paper W7000000011",
             "note": "a", "added_at": "2026-09-22T10:00:00Z"},
            {"ref": "title:Paper W7000000012", "title": "Paper W7000000012",
             "note": "b", "added_at": "2026-09-22T10:01:00Z"},
        ]
        inbox = lit / "inbox.jsonl"
        inbox.write_text("".join(json.dumps(e) + "\n" for e in entries),
                         encoding="utf-8")
        with fake_http(_title_search_handler({})) as fake:
            with contextlib.redirect_stdout(io.StringIO()), \
                    contextlib.redirect_stderr(io.StringIO()):
                run2 = lit_fetch.Run()
                lit_fetch.verb_inbox(lit, None, run2)
        assert len(fake.calls) == 2 and run2.written == 2 and run2.failed == 0
        assert inbox.read_text(encoding="utf-8") == ""

        # (b) decision 4: capture_identifier ignores remaining 0 (free call)
        def singleton(url):
            assert "/works/W9999999999?" in url
            return (200, {"x-ratelimit-remaining": "0"},
                    json.dumps(make_payload("W9999999999")))

        with fake_http(singleton):
            with contextlib.redirect_stdout(io.StringIO()):
                run3 = lit_fetch.Run()
                lit_fetch.capture_identifier("W9999999999", True, lit, None, run3)
        assert run3.written == 1
        assert (lit / "papers" / "W9999999999.json").exists()

        # (c) decision 3: singleton --title writes, then exits 1 with the budget line
        out = io.StringIO()
        with fake_http(_title_search_handler({"x-ratelimit-remaining": "0"})):
            with contextlib.redirect_stdout(out):
                rc = lit_fetch.main(["--title", "Paper W8888888888", "--dir", str(lit),
                                     "--api-key", "SECRET123"])
        assert rc == 1
        assert "budget exhausted; completed writes stand" in out.getvalue()
        assert (lit / "papers" / "W8888888888.json").exists()
        out2 = io.StringIO()
        with fake_http(_title_search_handler({"x-ratelimit-remaining": "9999"})):
            with contextlib.redirect_stdout(out2):
                rc2 = lit_fetch.main(["--title", "Paper W8888888888", "--dir", str(lit),
                                      "--api-key", "SECRET123"])
        assert rc2 == 0
        assert "written=0 skipped=1 failed=0" in out2.getvalue()


def test_inbox_budget_abort_freezes_queue():
    """T3. Remaining 0 on the first handled title search: no second call,
    the promoted record and a current index stand, the queue file is
    byte-identical, exit 1 with the budget line. A re-run with budget dedupes
    the first entry, resolves the second, and empties the queue."""
    with tempfile.TemporaryDirectory() as tmp:
        lit = pathlib.Path(tmp) / ".lit"
        lit_fetch.ensure_corpus(lit)
        entries = [
            {"ref": "title:Paper W7000000001", "title": "Paper W7000000001",
             "note": "first", "added_at": "2026-09-22T10:00:00Z"},
            {"ref": "title:Paper W7000000002", "title": "Paper W7000000002",
             "note": "second", "added_at": "2026-09-22T10:01:00Z"},
        ]
        inbox = lit / "inbox.jsonl"
        inbox.write_text("".join(json.dumps(e) + "\n" for e in entries),
                         encoding="utf-8")
        before = inbox.read_bytes()

        out = io.StringIO()
        with fake_http(_title_search_handler({"x-ratelimit-remaining": "0"})) as fake:
            with contextlib.redirect_stdout(out), \
                    contextlib.redirect_stderr(io.StringIO()):
                rc = lit_fetch.main(["--inbox", "--dir", str(lit)])
        assert rc == 1
        assert "budget exhausted; completed writes stand" in out.getvalue()
        assert len(fake.calls) == 1                     # second entry never called
        assert (lit / "papers" / "W7000000001.json").exists()
        assert not (lit / "papers" / "W7000000002.json").exists()
        assert inbox.read_bytes() == before             # queue frozen, byte for byte
        index = (lit / "SKILL.md").read_text(encoding="utf-8")
        assert "| papers (full records) | 1 |" in index  # regenerated inside promote_payload

        # re-run with budget: first entry dedupes against the corpus, second resolves
        out2 = io.StringIO()
        with fake_http(_title_search_handler({"x-ratelimit-remaining": "9999"})) as fake2:
            with contextlib.redirect_stdout(out2), \
                    contextlib.redirect_stderr(io.StringIO()):
                rc2 = lit_fetch.main(["--inbox", "--dir", str(lit)])
        assert rc2 == 0
        assert len(fake2.calls) == 1
        assert "written=1 skipped=1 failed=0" in out2.getvalue()
        assert (lit / "papers" / "W7000000002.json").exists()
        assert inbox.read_text(encoding="utf-8") == ""


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
    test_atomic_write_and_corpus_init,
    test_edges_and_aliases_roundtrip,
    test_index_and_status_counts,
    test_run_summary,
    test_singleton_capture_and_alias,
    test_title_verb_verification_gate,
    test_url_builders,
    test_parse_envelope,
    test_retry_then_success,
    test_retry_after_overrides_schedule,
    test_budget_exhausted,
    test_http_404_propagates,
    test_batch_two_chunks_and_keyless_warning,
    test_batch_skips_and_reports_absent,
    test_batch_single_id_merge,
    test_budget_abort_keeps_completed_writes,
    test_inbox_triage_flow,
    test_status_never_before_index,
    test_check_forms_fake,
    test_backoff_exhausted_redacts_key,
    test_inbox_keyed_backoff_writes_no_key,
    test_missing_remaining_header_does_not_stop,
    test_inbox_budget_abort_freezes_queue,
    test_present_rules,
    test_new_brief_shape,
    test_paper_capture_stamp,
    test_derive_basis,
    test_derive_status,
    test_ready_content_union_targets,
    test_validate_claim_rejects,
    test_validate_claim_lists_union,
    test_validate_brief_stub_and_ready,
    test_ensure_brief_stub_and_no_clobber,
    test_ensure_brief_stub_without_stamp,
    test_first_write_makes_exactly_one_stub_and_refetch_keeps_brief,
    test_stub_failure_surfaces,
    test_remap_brief_moves_and_merges,
    test_remap_brief_noop_when_old_missing,
    test_capture_merge_remaps_brief,
    test_batch_merge_remaps_brief,
    test_enrich_pending_listing,
    test_brief_status_counts_and_detail,
    test_brief_check_ok_and_invalid,
    test_brief_cli_verbs_main,
    test_brief_write_happy_and_derived_fields,
    test_brief_write_preserves_human,
    test_brief_write_rejections_leave_file_untouched,
    test_brief_write_status_levels,
    test_brief_restub_keeps_human_and_stamp,
    test_brief_write_cli_flags,
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
