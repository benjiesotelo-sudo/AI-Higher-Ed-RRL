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
    row = conn.execute("SELECT oa_pdf_url, is_oa FROM papers WHERE paper_id='p1'").fetchone()
    assert row["oa_pdf_url"] == "https://x/y.pdf"
    # Unpaywall returning a PDF URL implies the paper is OA — set is_oa=1
    # so the screen filter doesn't reject these papers as not_oa.
    assert row["is_oa"] == 1

@responses.activate
def test_enrich_skips_papers_without_doi(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    assert len(responses.calls) == 0

@responses.activate
def test_enrich_skips_already_checked_papers(tmp_path: Path):
    """Resumability: papers with unpaywall_checked_at set are skipped on rerun."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, "
                 "unpaywall_checked_at, first_seen_at, last_updated_at) "
                 "VALUES ('p1','10.1/already','T','[]',2023,'2026-05-14','now','now')")
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    assert len(responses.calls) == 0

@responses.activate
def test_enrich_continues_when_individual_doi_errors(tmp_path: Path):
    """A failing lookup on one DOI should not abort the whole run."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','10.1/bad','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p2','10.1/ok','T','[]',2023,'now','now')")
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/bad",
                  json={"error": "boom"}, status=500)
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/ok",
                  json={"best_oa_location": {"url_for_pdf": "https://x/y.pdf"}}, status=200)
    summary = enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    assert summary["checked"] == 2
    assert summary["updated"] == 1
    assert summary["errored"] == 1
    # Both papers are marked checked, so a rerun won't re-hit them.
    checked_count = conn.execute(
        "SELECT COUNT(*) FROM papers WHERE unpaywall_checked_at IS NOT NULL"
    ).fetchone()[0]
    assert checked_count == 2

@responses.activate
def test_enrich_marks_checked_even_when_no_pdf(tmp_path: Path):
    """A DOI lookup with no PDF should still mark the paper as checked."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','10.1/nopdf','T','[]',2023,'now','now')")
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/nopdf",
                  json={"best_oa_location": None, "oa_status": "closed"}, status=200)
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    row = conn.execute(
        "SELECT oa_pdf_url, unpaywall_checked_at FROM papers WHERE paper_id='p1'"
    ).fetchone()
    assert row["oa_pdf_url"] is None
    assert row["unpaywall_checked_at"] is not None
