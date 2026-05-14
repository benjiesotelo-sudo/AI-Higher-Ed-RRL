from click.testing import CliRunner
from pathlib import Path
from rrl.cli import main
from rrl.db import connect, init_schema

def test_status_reports_zero_counts_on_empty_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    connect(tmp_path / "data/rrl.sqlite").executescript("")
    init_schema(connect(tmp_path / "data/rrl.sqlite"))
    r = CliRunner().invoke(main, ["status"])
    assert r.exit_code == 0
    assert "raw_records" in r.output
    assert "papers" in r.output

def test_status_paper_shows_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    r = CliRunner().invoke(main, ["status", "--paper", "p1"])
    assert r.exit_code == 0
    assert "p1" in r.output

def test_all_runs_each_stage_in_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    called: list[str] = []

    def fake_harvest(db, only=None): called.append("harvest"); return {}
    def fake_dedup(conn): called.append("dedup"); return {"raw_records": 0, "papers_created": 0}
    def fake_enrich_oa(conn): called.append("openalex_flags"); return {}
    def fake_enrich_doaj(conn, sess): called.append("doaj"); return {}
    def fake_enrich_unp(conn, sess, email): called.append("unpaywall"); return {}
    def fake_screen(conn, dry_run=False): called.append("screen"); return {}
    def fake_export(**kw): called.append("export"); return {"counts": {}}

    monkeypatch.setattr("rrl.harvest.harvest", fake_harvest)
    monkeypatch.setattr("rrl.dedup.grouping.run_dedup", fake_dedup)
    monkeypatch.setattr("rrl.enrich.openalex_flags.enrich_from_openalex_payloads", fake_enrich_oa)
    monkeypatch.setattr("rrl.enrich.doaj.enrich_papers_with_doaj", fake_enrich_doaj)
    monkeypatch.setattr("rrl.enrich.unpaywall.enrich_papers_with_unpaywall", fake_enrich_unp)
    monkeypatch.setattr("rrl.screen.runner.run_screen", fake_screen)
    monkeypatch.setattr("rrl.output.runner.run_export", fake_export)

    r = CliRunner().invoke(main, ["all", "--skip", ""])
    assert r.exit_code == 0, r.output
    assert called == ["harvest", "dedup", "openalex_flags", "doaj", "unpaywall", "screen", "export"]

def test_all_respects_skip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    called: list[str] = []
    monkeypatch.setattr("rrl.harvest.harvest", lambda db, only=None: called.append("harvest") or {})
    monkeypatch.setattr("rrl.dedup.grouping.run_dedup", lambda c: called.append("dedup") or {"raw_records": 0, "papers_created": 0})
    monkeypatch.setattr("rrl.enrich.openalex_flags.enrich_from_openalex_payloads", lambda c: called.append("openalex_flags") or {})
    monkeypatch.setattr("rrl.enrich.doaj.enrich_papers_with_doaj", lambda c, s: called.append("doaj") or {})
    monkeypatch.setattr("rrl.enrich.unpaywall.enrich_papers_with_unpaywall", lambda c, s, e: called.append("unpaywall") or {})
    monkeypatch.setattr("rrl.screen.runner.run_screen", lambda c, dry_run=False: called.append("screen") or {})
    monkeypatch.setattr("rrl.output.runner.run_export", lambda **k: called.append("export") or {"counts": {}})

    r = CliRunner().invoke(main, ["all", "--skip", "harvest,export"])
    assert r.exit_code == 0, r.output
    assert "harvest" not in called and "export" not in called
    assert "dedup" in called and "screen" in called
