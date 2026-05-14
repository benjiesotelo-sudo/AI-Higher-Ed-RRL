from pathlib import Path
from rrl.db import connect, init_schema, SCHEMA_VERSION


def test_init_schema_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "rrl.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {r[0] for r in cur.fetchall()}
    assert tables >= {
        "search_runs", "raw_records", "papers", "paper_sources",
        "pdf_attempts", "paper_merges", "schema_version",
    }
    v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert v == SCHEMA_VERSION


def test_init_schema_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "rrl.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    init_schema(conn)  # second call must not error
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    assert count == 1


def test_wal_mode_enabled(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
