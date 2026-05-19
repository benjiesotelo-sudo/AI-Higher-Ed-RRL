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
    assert row["pdf_status"] == "not_retrievable"

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


@responses.activate
def test_download_pdfs_uses_sciencedirect_fallback_for_elsevier_doi(tmp_path):
    """When OA URL fails and DOI is Elsevier-prefixed, fall through to ScienceDirect."""
    from rrl.db import connect, init_schema
    from rrl.http import build_session
    from rrl.output.pdf import download_pdfs
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, year, oa_pdf_url, included, "
        "authors_json, first_seen_at, last_updated_at) "
        "VALUES ('p1','10.1016/j.test.2024.100001','T',2024,"
        "'https://dead.example/oa.pdf',1,'[]','now','now')"
    )
    # OA URL fails
    responses.add(responses.GET, "https://dead.example/oa.pdf", status=404)
    # ScienceDirect succeeds
    pdf_bytes = b"%PDF-1.4\n" + b"x" * (11 * 1024)
    responses.add(
        responses.GET,
        "https://api.elsevier.com/content/article/doi/10.1016/j.test.2024.100001",
        body=pdf_bytes,
        headers={"Content-Type": "application/pdf"},
        status=200,
    )
    summary = download_pdfs(
        conn, build_session("t@e.com"),
        pdf_root=tmp_path / "pdfs",
        core_api_key=None,
        elsevier_api_key="fake-key",
    )
    assert summary["downloaded"] == 1
    # Verify the X-ELS-APIKey header was sent on the ScienceDirect call
    sd_call = [c for c in responses.calls if "api.elsevier.com" in c.request.url][0]
    assert sd_call.request.headers.get("X-ELS-APIKey") == "fake-key"
    assert sd_call.request.headers.get("Accept") == "application/pdf"


@responses.activate
def test_download_pdfs_skips_sciencedirect_for_non_elsevier_doi(tmp_path):
    """A non-10.1016/ DOI must not trigger a ScienceDirect call."""
    from rrl.db import connect, init_schema
    from rrl.http import build_session
    from rrl.output.pdf import download_pdfs
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, year, oa_pdf_url, included, "
        "authors_json, first_seen_at, last_updated_at) "
        "VALUES ('p1','10.1111/hequ.12345','T',2024,"
        "'https://dead.example/oa.pdf',1,'[]','now','now')"
    )
    responses.add(responses.GET, "https://dead.example/oa.pdf", status=404)
    summary = download_pdfs(
        conn, build_session("t@e.com"),
        pdf_root=tmp_path / "pdfs",
        core_api_key=None,
        elsevier_api_key="fake-key",
    )
    assert summary["downloaded"] == 0
    assert summary["failed"] == 1
    # Only the OA URL was tried — no ScienceDirect request
    sd_calls = [c for c in responses.calls if "api.elsevier.com" in c.request.url]
    assert sd_calls == []


@responses.activate
def test_download_does_not_call_core_when_oa_succeeds(tmp_path, fixtures_dir):
    """CORE is a fallback, not a parallel source. With a working oa_pdf_url,
    no CORE request should fire — that's where the old code was wasting
    CORE budget and tripping the 10/min limit."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, doi, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','10.1/aaa','T','[]',2024,1,'https://x/y.pdf',1,'now','now')""")
    pdf_bytes = (fixtures_dir / "sample.pdf").read_bytes()
    responses.add(responses.GET, "https://x/y.pdf", body=pdf_bytes, status=200,
                  content_type="application/pdf")
    download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs",
                  core_api_key="KEY")
    core_calls = [c for c in responses.calls if "api.core.ac.uk" in c.request.url]
    assert core_calls == []


@responses.activate
def test_download_uses_core_only_when_oa_fails(tmp_path, fixtures_dir):
    """When the OA URL is dead, CORE should be tried as a fallback."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, doi, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','10.1/aaa','ChatGPT','[]',2024,1,'https://dead.example/x.pdf',1,'now','now')""")
    responses.add(responses.GET, "https://dead.example/x.pdf", status=404)
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  json={"results": [{"downloadUrl": "https://core.ac.uk/c.pdf"}]}, status=200)
    pdf_bytes = (fixtures_dir / "sample.pdf").read_bytes()
    responses.add(responses.GET, "https://core.ac.uk/c.pdf", body=pdf_bytes,
                  status=200, content_type="application/pdf")
    summary = download_pdfs(conn, build_session("t@e.com"),
                            pdf_root=tmp_path / "pdfs", core_api_key="KEY")
    assert summary["downloaded"] == 1
    core_calls = [c for c in responses.calls if "api.core.ac.uk" in c.request.url]
    assert len(core_calls) >= 1


@responses.activate
def test_download_handles_core_429_gracefully(tmp_path):
    """CORE returning 429 must NOT crash export — paper is marked
    not_retrievable and the run continues."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, doi, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','10.1/aaa','ChatGPT','[]',2024,1,'https://dead.example/x.pdf',1,'now','now')""")
    responses.add(responses.GET, "https://dead.example/x.pdf", status=404)
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  status=429)  # rate-limited
    summary = download_pdfs(conn, build_session("t@e.com"),
                            pdf_root=tmp_path / "pdfs", core_api_key="KEY")
    assert summary["failed"] == 1
    status = conn.execute("SELECT pdf_status FROM papers WHERE paper_id='p1'").fetchone()["pdf_status"]
    assert status == "not_retrievable"


@responses.activate
def test_download_respects_core_budget_cap(tmp_path):
    """With core_budget=0, no CORE call is made even when oa fails."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, doi, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','10.1/aaa','T','[]',2024,1,'https://dead.example/x.pdf',1,'now','now')""")
    responses.add(responses.GET, "https://dead.example/x.pdf", status=404)
    download_pdfs(conn, build_session("t@e.com"),
                  pdf_root=tmp_path / "pdfs", core_api_key="KEY",
                  core_budget=0)
    core_calls = [c for c in responses.calls if "api.core.ac.uk" in c.request.url]
    assert core_calls == []


@responses.activate
def test_download_pdfs_marks_not_retrievable_when_all_sources_fail(tmp_path):
    """All sources fail → pdf_status becomes 'not_retrievable' (not 'oa_link_dead')."""
    from rrl.db import connect, init_schema
    from rrl.http import build_session
    from rrl.output.pdf import download_pdfs
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, year, oa_pdf_url, included, "
        "authors_json, first_seen_at, last_updated_at) "
        "VALUES ('p1','10.1016/j.test.2024.999','T',2024,"
        "'https://dead.example/oa.pdf',1,'[]','now','now')"
    )
    responses.add(responses.GET, "https://dead.example/oa.pdf", status=404)
    responses.add(
        responses.GET,
        "https://api.elsevier.com/content/article/doi/10.1016/j.test.2024.999",
        status=403,
    )
    download_pdfs(
        conn, build_session("t@e.com"),
        pdf_root=tmp_path / "pdfs",
        core_api_key=None,
        elsevier_api_key="fake-key",
    )
    status = conn.execute("SELECT pdf_status FROM papers WHERE paper_id='p1'").fetchone()["pdf_status"]
    assert status == "not_retrievable"
