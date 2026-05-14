import json
import responses
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema

def _seed(db_path: Path):
    conn = connect(db_path); init_schema(conn)
    payload = {
        "type": "journal-article",
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "primary_location": {"source": {"host_organization_name": "Springer", "type": "journal", "issn_l": "1111-2222"}},
        "best_oa_location": {"pdf_url": "https://x/y.pdf"},
        "cited_by_count": 3,
    }
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (json.dumps(payload), "now"))
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES ('p1', 1)")

@responses.activate
def test_enrich_runs_all_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed(tmp_path / "data/rrl.sqlite")
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1111-2222",
                  json={"results": [{"id": "abc"}]}, status=200)
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/aaa",
                  json={"best_oa_location": {"url_for_pdf": "https://better.pdf"}}, status=200)
    r = CliRunner().invoke(main, ["enrich"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    row = conn.execute("SELECT is_in_doaj, oa_pdf_url, work_type, is_peer_reviewed FROM papers WHERE paper_id='p1'").fetchone()
    assert row["is_in_doaj"] == 1
    # Unpaywall overrides OpenAlex.
    assert row["oa_pdf_url"] == "https://better.pdf"
    assert row["work_type"] == "journal-article"
    assert row["is_peer_reviewed"] == 1
