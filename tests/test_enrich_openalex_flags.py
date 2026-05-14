import json
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.openalex_flags import enrich_from_openalex_payloads

def _seed(conn, paper_id, payload):
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (json.dumps(payload), "now"))
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES (?, 'T', '[]', 2023, 'now', 'now')", (paper_id,))
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES (?, 1)", (paper_id,))

def test_enrich_lifts_flags(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    payload = {
        "type": "journal-article",
        "cited_by_count": 12,
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "best_oa_location": {"pdf_url": "https://x/y.pdf"},
        "primary_location": {"source": {"host_organization_name": "Springer", "type": "journal"}},
    }
    _seed(conn, "p1", payload)
    enrich_from_openalex_payloads(conn)
    row = conn.execute("SELECT is_oa, oa_status, oa_pdf_url, work_type, publisher, citation_count, is_peer_reviewed FROM papers WHERE paper_id='p1'").fetchone()
    assert row["is_oa"] == 1
    assert row["oa_status"] == "gold"
    assert row["oa_pdf_url"] == "https://x/y.pdf"
    assert row["work_type"] == "journal-article"
    assert row["publisher"] == "Springer"
    assert row["citation_count"] == 12
    assert row["is_peer_reviewed"] == 1

def test_enrich_skips_repository_as_peer_reviewed(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    payload = {
        "type": "posted-content",
        "primary_location": {"source": {"type": "repository", "host_organization_name": "arXiv"}},
    }
    _seed(conn, "p2", payload)
    enrich_from_openalex_payloads(conn)
    row = conn.execute("SELECT is_peer_reviewed FROM papers WHERE paper_id='p2'").fetchone()
    assert row["is_peer_reviewed"] == 0
