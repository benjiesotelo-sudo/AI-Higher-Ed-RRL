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

@responses.activate
def test_harvest_since_overrides_year_min(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    r = CliRunner().invoke(main, ["harvest", "--since", "2024-06-01", "--only", "openalex"])
    assert r.exit_code == 0, r.output
    from rrl.db import connect, init_schema
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    import json
    payload = conn.execute("SELECT query_payload FROM search_runs WHERE adapter='openalex'").fetchone()[0]
    spec = json.loads(payload)["spec"]
    assert spec["year_min"] == 2024


def test_build_adapter_recognizes_scopus(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "user@example.com")
    monkeypatch.setenv("ELSEVIER_API_KEY", "fake-elsevier-key")
    from rrl.config import Settings
    from rrl.harvest import _build_adapter
    settings = Settings.from_env()
    adapter = _build_adapter("scopus", settings)
    from rrl.search.scopus import ScopusAdapter
    assert isinstance(adapter, ScopusAdapter)
    assert adapter.api_key == "fake-elsevier-key"


def test_adapters_tuple_includes_scopus():
    from rrl.harvest import ADAPTERS
    assert "scopus" in ADAPTERS


def test_build_adapter_scopus_requires_key(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "user@example.com")
    monkeypatch.delenv("ELSEVIER_API_KEY", raising=False)
    from rrl.config import Settings
    from rrl.harvest import _build_adapter
    settings = Settings.from_env()
    import pytest
    with pytest.raises(ValueError, match="scopus adapter requires"):
        _build_adapter("scopus", settings)


def test_harvest_skips_scopus_when_key_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENALEX_EMAIL", "user@example.com")
    monkeypatch.delenv("ELSEVIER_API_KEY", raising=False)
    monkeypatch.delenv("SEMANTIC_SCHOLAR_API_KEY", raising=False)
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    from rrl.harvest import harvest
    # only=['scopus'] should be a no-op when key is missing — no exception, no records
    counts = harvest(tmp_path / "rrl.sqlite", only=["scopus"])
    assert counts == {} or counts.get("scopus", 0) == 0
