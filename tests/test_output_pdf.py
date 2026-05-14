from pathlib import Path
import responses
from rrl.db import connect, init_schema
from rrl.http import build_session
from rrl.output.pdf import validate_pdf_bytes, download_pdfs

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
