import responses
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.doaj import lookup_issn, enrich_papers_with_doaj
from rrl.http import build_session

@responses.activate
def test_lookup_issn_listed():
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1234-5678",
                  json={"results": [{"id": "abc"}]}, status=200)
    assert lookup_issn(build_session("t@e.com"), "1234-5678") is True

@responses.activate
def test_lookup_issn_not_listed():
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:9999-9999",
                  json={"results": []}, status=200)
    assert lookup_issn(build_session("t@e.com"), "9999-9999") is False

@responses.activate
def test_enrich_skips_papers_without_issn(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    enrich_papers_with_doaj(conn, build_session("t@e.com"))
    v = conn.execute("SELECT is_in_doaj FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert v is None
    # No ISSN, but the paper is still marked checked so we won't retry it forever.
    checked = conn.execute("SELECT doaj_checked_at FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert checked is not None

@responses.activate
def test_enrich_skips_already_checked_papers(tmp_path: Path):
    """Resumability: papers with doaj_checked_at set are skipped on rerun."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, doaj_checked_at, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'2026-05-14','now','now')")
    enrich_papers_with_doaj(conn, build_session("t@e.com"))
    assert len(responses.calls) == 0

@responses.activate
def test_enrich_continues_when_lookup_errors(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    bad = '{"primary_location":{"source":{"issn_l":"0000-0001"}}}'
    good = '{"primary_location":{"source":{"issn_l":"1111-2222"}}}'
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (bad, "now"))
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W2','T',?,?)", (good, "now"))
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p2','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES ('p1', 1)")
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES ('p2', 2)")
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:0000-0001",
                  json={"error": "boom"}, status=500)
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1111-2222",
                  json={"results": [{"id": "abc"}]}, status=200)
    summary = enrich_papers_with_doaj(conn, build_session("t@e.com"))
    assert summary["errored"] == 1
    assert summary["updated"] == 1
    # Both papers marked checked so they won't be re-tried.
    assert conn.execute(
        "SELECT COUNT(*) FROM papers WHERE doaj_checked_at IS NOT NULL"
    ).fetchone()[0] == 2

@responses.activate
def test_enrich_sets_flag_when_issn_present(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    payload = '{"primary_location":{"source":{"issn_l":"1111-2222"}}}'
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (payload, "now"))
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES ('p1', 1)")
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1111-2222",
                  json={"results": [{"id": "abc"}]}, status=200)
    enrich_papers_with_doaj(conn, build_session("t@e.com"))
    v = conn.execute("SELECT is_in_doaj FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert v == 1
