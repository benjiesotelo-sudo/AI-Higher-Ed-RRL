import json
import responses
from pathlib import Path
from click.testing import CliRunner

from rrl.cli import main
from rrl.db import connect, init_schema

def _setup_responses(fixtures_dir: Path):
    oa1 = json.loads((fixtures_dir / "openalex_page1.json").read_text())
    oa2 = json.loads((fixtures_dir / "openalex_page2.json").read_text())
    eric = json.loads((fixtures_dir / "eric_response.json").read_text())
    eric_empty = {"response": {"numFound": 2, "start": 2000, "docs": []}}
    s2 = json.loads((fixtures_dir / "s2_bulk_response.json").read_text())
    s2_empty = {"token": None, "data": []}
    responses.add(responses.GET, "https://api.openalex.org/works", json=oa1)
    responses.add(responses.GET, "https://api.openalex.org/works", json=oa2)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=eric)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=eric_empty)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=s2)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=s2_empty)

@responses.activate
def test_harvest_populates_raw_records_and_search_runs(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    r = CliRunner().invoke(main, ["harvest"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    init_schema(conn)
    n_raw = conn.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]
    n_runs = conn.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
    assert n_raw == 6
    assert n_runs == 3
    statuses = {r[0] for r in conn.execute("SELECT status FROM search_runs").fetchall()}
    assert statuses == {"ok"}

@responses.activate
def test_harvest_is_idempotent_on_unique_constraint(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    CliRunner().invoke(main, ["harvest"])
    _setup_responses(fixtures_dir)
    r = CliRunner().invoke(main, ["harvest"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    init_schema(conn)
    n_raw = conn.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]
    assert n_raw == 6

@responses.activate
def test_harvest_only_filter(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    r = CliRunner().invoke(main, ["harvest", "--only", "openalex"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    init_schema(conn)
    adapters = {r[0] for r in conn.execute("SELECT DISTINCT adapter FROM raw_records").fetchall()}
    assert adapters == {"openalex"}
