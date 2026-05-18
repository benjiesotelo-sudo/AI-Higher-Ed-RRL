import json
import sqlite3

from rrl.db import init_schema
from rrl.enrich.eric_flags import _flags_from_payload, enrich_from_eric_payloads, ERIC_FULLTEXT_URL


def test_ed_prefix_sets_oa_and_url():
    f = _flags_from_payload("ED600585", {"peerreviewed": "F"})
    assert f["is_oa"] == 1
    assert f["oa_pdf_url"] == ERIC_FULLTEXT_URL.format("ED600585")
    assert f["is_peer_reviewed"] is None


def test_ej_prefix_does_not_set_oa_url():
    f = _flags_from_payload("EJ123456", {"peerreviewed": "T"})
    assert f["is_oa"] is None
    assert f["oa_pdf_url"] is None
    assert f["is_peer_reviewed"] == 1


def test_peerreviewed_t_sets_flag_regardless_of_prefix():
    assert _flags_from_payload("ED1", {"peerreviewed": "T"})["is_peer_reviewed"] == 1
    assert _flags_from_payload("EJ1", {"peerreviewed": "T"})["is_peer_reviewed"] == 1
    assert _flags_from_payload("EJ1", {"peerreviewed": "F"})["is_peer_reviewed"] is None
    assert _flags_from_payload("EJ1", {})["is_peer_reviewed"] is None


def _seed(conn):
    init_schema(conn)
    now = "2026-05-18T00:00:00+00:00"
    conn.execute(
        "INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES (?,?,?,?,?,?)",
        ("r1", "eric", "h", "{}", now, "ok"),
    )
    for raw_id, ext, pr, prefix in [
        (101, "ED111", "T", "ED"),  # ED + peer-reviewed
        (102, "EJ222", "T", "EJ"),  # EJ + peer-reviewed
        (103, "ED333", "F", "ED"),  # ED + not peer-reviewed
        (104, "EJ444", "F", "EJ"),  # EJ + not peer-reviewed (full miss)
    ]:
        conn.execute(
            """INSERT INTO raw_records (raw_id, run_id, adapter, external_id, title,
               title_norm, authors_json, raw_payload, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (raw_id, "r1", "eric", ext, f"Title {ext}", f"title {ext}", "[]",
             json.dumps({"peerreviewed": pr}), now),
        )
        pid = f"p{raw_id}"
        conn.execute(
            """INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at)
               VALUES (?,?,?,?,?,?)""",
            (pid, f"Title {ext}", "[]", 2024, now, now),
        )
        conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES (?,?)", (pid, raw_id))


def test_enrich_updates_in_database():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed(conn)

    counts = enrich_from_eric_payloads(conn)
    assert counts["updated"] == 3   # EJ444 has nothing to set
    assert counts["is_oa_set"] == 2  # ED111, ED333
    assert counts["is_peer_reviewed_set"] == 2  # ED111, EJ222

    rows = {r["paper_id"]: dict(r) for r in conn.execute("SELECT * FROM papers").fetchall()}
    assert rows["p101"]["is_oa"] == 1 and rows["p101"]["is_peer_reviewed"] == 1
    assert rows["p101"]["oa_pdf_url"] == ERIC_FULLTEXT_URL.format("ED111")
    assert rows["p102"]["is_oa"] is None and rows["p102"]["is_peer_reviewed"] == 1
    assert rows["p103"]["is_oa"] == 1 and rows["p103"]["is_peer_reviewed"] is None
    assert rows["p104"]["is_oa"] is None and rows["p104"]["is_peer_reviewed"] is None


def test_enrich_does_not_overwrite_existing_values():
    """OpenAlex enrichment runs first; its values should win."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _seed(conn)
    # Simulate OpenAlex enrichment having set is_peer_reviewed=0 for p101.
    conn.execute("UPDATE papers SET is_peer_reviewed=0 WHERE paper_id='p101'")
    enrich_from_eric_payloads(conn)
    r = conn.execute("SELECT is_peer_reviewed FROM papers WHERE paper_id='p101'").fetchone()
    assert r["is_peer_reviewed"] == 0  # ERIC didn't override
