from pathlib import Path

from rrl.db import connect, init_schema


def test_mmat_tables_created(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    names = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert {"mmat_classifications", "mmat_appraisals", "mmat_dispositions"} <= names


def test_mmat_appraisals_unique_constraint(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite")
    init_schema(conn)
    conn.execute(
        "INSERT INTO papers (paper_id, title, authors_json, year, "
        "first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')"
    )
    row = ("p1", "llm_pass_1", "qualitative", "1.1", "yes", None, None, None, None,
           "classify-v1", "test-model", "harness", "now")
    cols = ("paper_id, coder, mmat_category, criterion_id, rating, rationale, "
            "source_quote, quote_verified, adjudication_note, prompt_version, "
            "model, engine, created_at")
    ins = f"INSERT INTO mmat_appraisals ({cols}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)"
    conn.execute(ins, row)
    import sqlite3
    with __import__("pytest").raises(sqlite3.IntegrityError):
        conn.execute(ins, row)  # same (paper_id, coder, criterion_id, prompt_version)
