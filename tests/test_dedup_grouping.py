import json
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.dedup.grouping import (
    compute_dedup_key, paper_id_from_key, build_canonical_paper, run_dedup,
)

def _insert_raw(conn, run_id, adapter, ext_id, doi=None, title="T", year=2023,
                first_author="smith", authors=None, abstract=None, venue=None,
                openalex_id=None):
    authors = authors or [{"family": "Smith", "given": "J", "orcid": None}]
    payload = {"id": f"https://openalex.org/{openalex_id}"} if openalex_id else {}
    conn.execute(
        """INSERT INTO raw_records (run_id, adapter, external_id, doi, title, title_norm,
           authors_json, first_author, year, venue, abstract, language, raw_payload, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, adapter, ext_id, doi, title, title.lower(),
         json.dumps(authors), first_author, year, venue, abstract, "en",
         json.dumps(payload), "2026-05-14T00:00:00Z"),
    )

def _seed(conn):
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r1','openalex','h','{}','2026-05-14T00:00:00Z','ok')")
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r2','eric','h','{}','2026-05-14T00:00:00Z','ok')")

def test_doi_key_prefers_normalized():
    k1 = compute_dedup_key({"doi": "https://doi.org/10.1/X", "openalex_id": None,
                            "title_norm": "t", "year": 2023, "first_author": "smith", "raw_id": 1})
    k2 = compute_dedup_key({"doi": "10.1/x", "openalex_id": None,
                            "title_norm": "different", "year": 2024, "first_author": "doe", "raw_id": 2})
    assert k1 == k2

def test_openalex_key_used_when_no_doi():
    k = compute_dedup_key({"doi": None, "openalex_id": "W1",
                           "title_norm": "t", "year": 2023, "first_author": "smith", "raw_id": 1})
    assert k.startswith("openalex:")

def test_signature_key_fallback():
    k1 = compute_dedup_key({"doi": None, "openalex_id": None,
                            "title_norm": "study of chatgpt", "year": 2023, "first_author": "smith", "raw_id": 1})
    k2 = compute_dedup_key({"doi": None, "openalex_id": None,
                            "title_norm": "study of chatgpt", "year": 2023, "first_author": "smith", "raw_id": 2})
    assert k1 == k2 and k1.startswith("sig:")

def test_singleton_fallback_when_no_fields():
    k = compute_dedup_key({"doi": None, "openalex_id": None,
                           "title_norm": "", "year": None, "first_author": None, "raw_id": 99})
    assert k == "singleton:raw_99"

def test_paper_id_deterministic():
    k = "doi:10.1/x"
    assert paper_id_from_key(k) == paper_id_from_key(k)
    assert len(paper_id_from_key(k)) == 16

def test_run_dedup_merges_across_adapters(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W111", doi="10.1/aaa", title="ChatGPT in university", openalex_id="W111")
    _insert_raw(conn, "r2", "eric", "EJ100001", doi="10.1/aaa", title="ChatGPT in university (preprint)")
    summary = run_dedup(conn)
    assert summary["raw_records"] == 2
    assert summary["papers_created"] == 1
    n_links = conn.execute("SELECT COUNT(*) FROM paper_sources").fetchone()[0]
    assert n_links == 2

def test_run_dedup_keeps_distinct_papers(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W1", doi="10.1/a", title="A")
    _insert_raw(conn, "r1", "openalex", "W2", doi="10.1/b", title="B")
    run_dedup(conn)
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2

def test_run_dedup_is_idempotent(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W1", doi="10.1/a", title="A")
    run_dedup(conn)
    run_dedup(conn)
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM paper_sources").fetchone()[0] == 1

# --- Phase-6 follow-up: fuzzy fingerprint + post-dedup merge pass ---

from rrl.dedup.grouping import fuzzy_fingerprint, fuzzy_merge_pass


def test_fuzzy_fingerprint_same_paper_different_subtitle():
    """Same paper with vs without subtitle should share a fingerprint."""
    a = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses across three universities",
        year=2024,
        authors_json='[{"family": "Smith", "given": "J"}]',
    )
    b = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses across three universities: a mixed-methods study",
        year=2024,
        authors_json='[{"family": "Smith", "given": "J A"}]',
    )
    assert a is not None and a == b


def test_fuzzy_fingerprint_robust_to_author_ordering():
    """Co-author order should not change the fingerprint."""
    a = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses across three universities",
        year=2024,
        authors_json='[{"family": "Smith"}, {"family": "Jones"}, {"family": "Lee"}]',
    )
    b = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses across three universities",
        year=2024,
        authors_json='[{"family": "Jones"}, {"family": "Lee"}, {"family": "Smith"}]',
    )
    assert a is not None and a == b


def test_fuzzy_fingerprint_different_papers_differ():
    a = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses",
        year=2024,
        authors_json='[{"family": "Smith"}]',
    )
    b = fuzzy_fingerprint(
        title="Faculty perceptions of generative AI tools in research",
        year=2024,
        authors_json='[{"family": "Smith"}]',
    )
    assert a != b


def test_fuzzy_fingerprint_year_must_match():
    a = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses across three universities",
        year=2024,
        authors_json='[{"family": "Smith"}]',
    )
    b = fuzzy_fingerprint(
        title="ChatGPT in undergraduate writing courses across three universities",
        year=2025,
        authors_json='[{"family": "Smith"}]',
    )
    assert a != b


def test_fuzzy_fingerprint_short_title_returns_none():
    """Very short titles are unreliable for fingerprinting."""
    assert fuzzy_fingerprint(title="AI study", year=2024,
                             authors_json='[{"family": "Smith"}]') is None


def test_fuzzy_fingerprint_missing_fields_returns_none():
    base = dict(
        title="ChatGPT in undergraduate writing courses across three universities",
        year=2024,
        authors_json='[{"family": "Smith"}]',
    )
    assert fuzzy_fingerprint(**{**base, "year": None}) is None
    assert fuzzy_fingerprint(**{**base, "authors_json": "[]"}) is None
    assert fuzzy_fingerprint(**{**base, "title": ""}) is None


def test_fuzzy_merge_pass_merges_doi_less_dupe_into_doi_paper(tmp_path: Path):
    """ERIC entry without DOI should merge into the OpenAlex entry with DOI
    when they share a fuzzy fingerprint."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    title = "ChatGPT in undergraduate writing courses across three universities"
    _insert_raw(conn, "r1", "openalex", "W111", doi="10.1/aaa", title=title,
                first_author="smith",
                authors=[{"family": "Smith", "given": "J"}], year=2024,
                openalex_id="W111")
    _insert_raw(conn, "r2", "eric", "E222", doi=None,
                title=title + ": a mixed-methods study",
                first_author="smithja",
                authors=[{"family": "Smith", "given": "J A"}], year=2024)
    run_dedup(conn)
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2

    fuzzy_merge_pass(conn, pdf_root=tmp_path / "pdfs")

    # The DOI-bearing paper survives; both raw_records link to it.
    survivors = conn.execute(
        "SELECT DISTINCT paper_id FROM paper_sources"
    ).fetchall()
    assert len(survivors) == 1
    winner = survivors[0][0]
    assert conn.execute(
        "SELECT doi FROM papers WHERE paper_id=?", (winner,)
    ).fetchone()[0] == "10.1/aaa"
    assert conn.execute(
        "SELECT COUNT(*) FROM paper_sources WHERE paper_id=?", (winner,)
    ).fetchone()[0] == 2


def test_fuzzy_merge_pass_does_not_merge_different_papers(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W1", doi=None,
                title="ChatGPT in undergraduate writing courses across institutions",
                first_author="smith",
                authors=[{"family": "Smith"}], year=2024)
    _insert_raw(conn, "r2", "eric", "E1", doi=None,
                title="Faculty perceptions of generative AI in research universities",
                first_author="smith",
                authors=[{"family": "Smith"}], year=2024)
    run_dedup(conn)
    fuzzy_merge_pass(conn, pdf_root=tmp_path / "pdfs")
    survivors = conn.execute(
        "SELECT DISTINCT paper_id FROM paper_sources"
    ).fetchall()
    assert len(survivors) == 2


def test_canonical_prefers_longest_title_and_openalex_source():
    raws = [
        {"adapter": "eric", "title": "Short title", "authors_json": '[{"family":"Smith"}]', "doi": None,
         "year": 2023, "venue": "X", "abstract": None, "language": "en", "first_author": "smith",
         "raw_id": 1, "raw_payload": "{}"},
        {"adapter": "openalex", "title": "Longer title from OpenAlex", "authors_json": '[{"family":"Smith"}]',
         "doi": "10.1/x", "year": 2023, "venue": "Y", "abstract": "Long abstract", "language": "en",
         "first_author": "smith", "raw_id": 2, "raw_payload": "{}"},
    ]
    canon = build_canonical_paper(raws)
    assert canon["title"] == "Longer title from OpenAlex"
    assert canon["venue"] == "Y"
    assert canon["abstract"] == "Long abstract"
    assert canon["doi"] == "10.1/x"
