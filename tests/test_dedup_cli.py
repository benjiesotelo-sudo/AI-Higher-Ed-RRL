import json
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema

def _seed_two_papers(db_path: Path):
    conn = connect(db_path); init_schema(conn)
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','2026-05-14T00:00:00Z','ok')")
    for ext, doi, title in [("W1","10.1/a","Generative AI in colleges 2023 Smith"),
                            ("W2","10.1/b","Generative AI in colleges 2023 (preprint) Smith")]:
        conn.execute(
            """INSERT INTO raw_records (run_id, adapter, external_id, doi, title, title_norm,
               authors_json, first_author, year, venue, abstract, language, raw_payload, fetched_at)
               VALUES ('r','openalex',?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ext, doi, title, title.lower(),
             json.dumps([{"family":"Smith","given":"J","orcid":None}]),
             "smith", 2023, "J", "abs", "en", "{}", "2026-05-14T00:00:00Z"),
        )

def test_dedup_command_creates_papers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed_two_papers(tmp_path / "data/rrl.sqlite")
    r = CliRunner().invoke(main, ["dedup"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2

def test_dedup_review_writes_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed_two_papers(tmp_path / "data/rrl.sqlite")
    CliRunner().invoke(main, ["dedup"])
    r = CliRunner().invoke(main, ["dedup", "--review"])
    assert r.exit_code == 0, r.output
    review = tmp_path / "data/dedup_review.csv"
    assert review.exists()
    rows = review.read_text().strip().splitlines()
    assert len(rows) >= 2

def test_dedup_merge_records_paper_merges(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed_two_papers(tmp_path / "data/rrl.sqlite")
    CliRunner().invoke(main, ["dedup"])
    conn = connect(tmp_path / "data/rrl.sqlite")
    ids = [r[0] for r in conn.execute("SELECT paper_id FROM papers").fetchall()]
    loser, winner = ids[0], ids[1]
    r = CliRunner().invoke(main, ["dedup", "--merge", loser, winner])
    assert r.exit_code == 0, r.output
    n = conn.execute("SELECT COUNT(*) FROM paper_merges WHERE loser_id=? AND winner_id=?", (loser, winner)).fetchone()[0]
    assert n == 1
    rem = conn.execute("SELECT COUNT(*) FROM paper_sources WHERE paper_id=?", (loser,)).fetchone()[0]
    assert rem == 0
