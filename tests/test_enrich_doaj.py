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
