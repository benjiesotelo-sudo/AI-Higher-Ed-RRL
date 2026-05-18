from pathlib import Path
import responses
from rrl.db import connect, init_schema
from rrl.http import build_session
from rrl.output.pdf import validate_pdf_bytes, download_pdfs, _try_url

def test_validate_rejects_non_pdf_magic():
    assert validate_pdf_bytes(b"<html>error</html>") is False

def test_validate_rejects_tiny_file():
    assert validate_pdf_bytes(b"%PDF-1.4\nshort") is False

def test_validate_accepts_real_pdf(fixtures_dir):
    data = (fixtures_dir / "sample.pdf").read_bytes()
    assert validate_pdf_bytes(data) is True

@responses.activate
def test_download_pdfs_writes_file_and_records_attempt(tmp_path, fixtures_dir):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,1,'https://x/y.pdf',1,'now','now')""")
    data = (fixtures_dir / "sample.pdf").read_bytes()
    responses.add(responses.GET, "https://x/y.pdf", body=data, status=200,
                  content_type="application/pdf")
    summary = download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs", core_api_key=None)
    assert summary["downloaded"] == 1
    row = conn.execute("SELECT pdf_status, pdf_filename FROM papers WHERE paper_id='p1'").fetchone()
    assert row["pdf_status"] == "downloaded"
    assert (tmp_path / "pdfs" / row["pdf_filename"]).exists()
    att = conn.execute("SELECT outcome FROM pdf_attempts").fetchone()[0]
    assert att == "ok"

@responses.activate
def test_download_marks_oa_link_dead_after_failed_attempts(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,1,'https://x/y.pdf',1,'now','now')""")
    responses.add(responses.GET, "https://x/y.pdf", body=b"<html>nope</html>", status=200)
    download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs", core_api_key=None)
    row = conn.execute("SELECT pdf_status FROM papers WHERE paper_id='p1'").fetchone()
    assert row["pdf_status"] == "oa_link_dead"

@responses.activate
def test_download_skips_already_downloaded(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year,
        is_oa, oa_pdf_url, included, pdf_status, pdf_filename,
        first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,1,'u',1,'downloaded','2023/p1.pdf','now','now')""")
    summary = download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs", core_api_key=None)
    assert summary["downloaded"] == 0
    assert len(responses.calls) == 0


@responses.activate
def test_try_url_sends_custom_headers(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, "
                 "first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    pdf_bytes = b"%PDF-1.4\n" + b"x" * (11 * 1024)
    responses.add(responses.GET, "https://example.org/x.pdf",
                  body=pdf_bytes,
                  headers={"Content-Type": "application/pdf"},
                  status=200)
    dest = tmp_path / "x.pdf"
    ok = _try_url(build_session("t@e.com"), "https://example.org/x.pdf",
                  "test_source", "p1", conn, dest,
                  headers={"X-Test-Header": "hello"})
    assert ok is True
    assert responses.calls[0].request.headers.get("X-Test-Header") == "hello"


@responses.activate
def test_try_url_works_without_headers(tmp_path):
    """Backward compat: existing callers that don't pass headers still work."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, "
                 "first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    pdf_bytes = b"%PDF-1.4\n" + b"x" * (11 * 1024)
    responses.add(responses.GET, "https://example.org/y.pdf",
                  body=pdf_bytes,
                  headers={"Content-Type": "application/pdf"},
                  status=200)
    dest = tmp_path / "y.pdf"
    ok = _try_url(build_session("t@e.com"), "https://example.org/y.pdf",
                  "test_source", "p1", conn, dest)
    assert ok is True
