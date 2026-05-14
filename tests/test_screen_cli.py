from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema

def _insert(conn, pid, **kw):
    cols = {"paper_id": pid, "title": "T", "authors_json": "[]", "year": 2023,
            "language": "en", "is_oa": 1, "oa_pdf_url": "u",
            "first_seen_at": "now", "last_updated_at": "now"}
    cols.update(kw)
    keys = ",".join(cols.keys())
    qs = ",".join(["?"] * len(cols))
    conn.execute(f"INSERT INTO papers ({keys}) VALUES ({qs})", tuple(cols.values()))

def test_screen_assigns_included_and_tier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    _insert(conn, "p_good", title="ChatGPT in higher education",
            is_peer_reviewed=1, work_type="journal-article", publisher="J", abstract="Survey of faculty.")
    _insert(conn, "p_offtopic", title="Tomato cultivation", abstract="No relevance")
    _insert(conn, "p_old", year=2019, title="ChatGPT in higher education", abstract="")
    r = CliRunner().invoke(main, ["screen"])
    assert r.exit_code == 0, r.output
    rows = {row[0]: row for row in conn.execute("SELECT paper_id, included, exclusion_reason, quality_tier, era_tag FROM papers").fetchall()}
    assert rows["p_good"][1] == 1
    assert rows["p_good"][3] == "high_confidence"
    assert rows["p_good"][4] == "post_chatgpt"
    assert rows["p_offtopic"][1] == 0
    assert rows["p_offtopic"][2] == "off_topic"
    assert rows["p_old"][2] == "wrong_date"

def test_screen_fills_in_language_via_langdetect(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    _insert(conn, "p1", language=None, title="ChatGPT in higher education",
            abstract="This study examines faculty adoption of ChatGPT in university classrooms.",
            is_peer_reviewed=1, work_type="journal-article", publisher="J")
    r = CliRunner().invoke(main, ["screen"])
    assert r.exit_code == 0
    row = conn.execute("SELECT included, language FROM papers WHERE paper_id='p1'").fetchone()
    assert row["language"] == "en"  # filled in by langdetect
    assert row["included"] == 1

def test_screen_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    _insert(conn, "p1", title="ChatGPT in university")
    r = CliRunner().invoke(main, ["screen", "--dry-run"])
    assert r.exit_code == 0
    inc = conn.execute("SELECT included FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert inc is None
