import responses
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.unpaywall import enrich_papers_with_unpaywall, lookup_doi
from rrl.http import build_session

@responses.activate
def test_lookup_returns_pdf_url():
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/aaa",
                  json={"best_oa_location": {"url_for_pdf": "https://x/y.pdf"}}, status=200)
    pdf, status = lookup_doi(build_session("t@e.com"), "10.1/aaa", "t@e.com")
    assert pdf == "https://x/y.pdf"

@responses.activate
def test_lookup_handles_no_oa():
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/bbb",
                  json={"best_oa_location": None}, status=200)
    pdf, status = lookup_doi(build_session("t@e.com"), "10.1/bbb", "t@e.com")
    assert pdf is None

@responses.activate
def test_enrich_writes_oa_pdf_url(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,'now','now')")
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/aaa",
                  json={"best_oa_location": {"url_for_pdf": "https://x/y.pdf"}}, status=200)
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    v = conn.execute("SELECT oa_pdf_url FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert v == "https://x/y.pdf"

@responses.activate
def test_enrich_skips_papers_without_doi(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    assert len(responses.calls) == 0
