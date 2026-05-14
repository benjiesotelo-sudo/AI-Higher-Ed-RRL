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
