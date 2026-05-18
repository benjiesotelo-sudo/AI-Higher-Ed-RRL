import responses
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.scopus_citations import enrich_papers_with_scopus, lookup_citations
from rrl.http import build_session


@responses.activate
def test_lookup_citations_returns_count():
    responses.add(
        responses.GET, "https://api.elsevier.com/content/abstract/doi/10.1/aaa",
        json={"abstracts-retrieval-response": {"coredata": {"citedby-count": "42"}}},
        status=200,
    )
    n = lookup_citations(build_session("t@e.com"), "10.1/aaa", api_key="fake-key")
    assert n == 42


@responses.activate
def test_lookup_citations_returns_none_on_404():
    responses.add(
        responses.GET, "https://api.elsevier.com/content/abstract/doi/10.1/bbb",
        status=404,
    )
    n = lookup_citations(build_session("t@e.com"), "10.1/bbb", api_key="fake-key")
    assert n is None


@responses.activate
def test_lookup_citations_sends_apikey_header():
    responses.add(
        responses.GET, "https://api.elsevier.com/content/abstract/doi/10.1/aaa",
        json={"abstracts-retrieval-response": {"coredata": {"citedby-count": "5"}}},
        status=200,
    )
    lookup_citations(build_session("t@e.com"), "10.1/aaa", api_key="my-key")
    assert responses.calls[0].request.headers.get("X-ELS-APIKey") == "my-key"


@responses.activate
def test_enrich_updates_null_citation_counts(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, authors_json, year, citation_count, "
        "first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,NULL,'now','now')"
    )
    responses.add(
        responses.GET, "https://api.elsevier.com/content/abstract/doi/10.1/aaa",
        json={"abstracts-retrieval-response": {"coredata": {"citedby-count": "7"}}},
        status=200,
    )
    summary = enrich_papers_with_scopus(conn, build_session("t@e.com"), api_key="fake-key")
    row = conn.execute(
        "SELECT citation_count, scopus_checked_at FROM papers WHERE paper_id='p1'"
    ).fetchone()
    assert row["citation_count"] == 7
    assert row["scopus_checked_at"] is not None
    assert summary["updated"] == 1


@responses.activate
def test_enrich_skips_papers_with_existing_citation_count(tmp_path: Path):
    """If OpenAlex already filled citation_count, Scopus is skipped (saves quota)."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, authors_json, year, citation_count, "
        "first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,15,'now','now')"
    )
    enrich_papers_with_scopus(conn, build_session("t@e.com"), api_key="fake-key")
    assert len(responses.calls) == 0


@responses.activate
def test_enrich_skips_papers_without_doi(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, title, authors_json, year, "
        "first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')"
    )
    enrich_papers_with_scopus(conn, build_session("t@e.com"), api_key="fake-key")
    assert len(responses.calls) == 0


@responses.activate
def test_enrich_is_resumable(tmp_path: Path):
    """Papers with scopus_checked_at set are skipped on re-run."""
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, authors_json, year, citation_count, "
        "scopus_checked_at, first_seen_at, last_updated_at) "
        "VALUES ('p1','10.1/aaa','T','[]',2023,NULL,'2026-05-14','now','now')"
    )
    enrich_papers_with_scopus(conn, build_session("t@e.com"), api_key="fake-key")
    assert len(responses.calls) == 0


def test_enrich_no_op_without_api_key(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, authors_json, year, "
        "first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,'now','now')"
    )
    summary = enrich_papers_with_scopus(conn, build_session("t@e.com"), api_key=None)
    assert summary == {"checked": 0, "updated": 0, "errored": 0, "skipped_no_key": True}


@responses.activate
def test_enrich_continues_on_individual_failure(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, authors_json, year, "
        "first_seen_at, last_updated_at) VALUES ('p1','10.1/bad','T','[]',2023,'now','now')"
    )
    conn.execute(
        "INSERT INTO papers (paper_id, doi, title, authors_json, year, "
        "first_seen_at, last_updated_at) VALUES ('p2','10.1/ok','T','[]',2023,'now','now')"
    )
    responses.add(
        responses.GET, "https://api.elsevier.com/content/abstract/doi/10.1/bad",
        json={"error": "boom"}, status=500,
    )
    responses.add(
        responses.GET, "https://api.elsevier.com/content/abstract/doi/10.1/ok",
        json={"abstracts-retrieval-response": {"coredata": {"citedby-count": "3"}}},
        status=200,
    )
    summary = enrich_papers_with_scopus(conn, build_session("t@e.com"), api_key="fake-key")
    assert summary["checked"] == 2
    assert summary["updated"] == 1
    assert summary["errored"] == 1
