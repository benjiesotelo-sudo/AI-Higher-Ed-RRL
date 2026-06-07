"""Deterministic persistence + validation for MMAT appraisal (no model calls)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_disposition(conn: sqlite3.Connection, paper_id: str,
                    disposition: str, detail: str = "") -> None:
    """Upsert one paper's disposition so a row can transition (ok -> appraised)."""
    conn.execute(
        "INSERT INTO mmat_dispositions (paper_id, disposition, detail, created_at) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(paper_id) DO UPDATE SET "
        "disposition=excluded.disposition, detail=excluded.detail, created_at=excluded.created_at",
        (paper_id, disposition, detail, _now()),
    )


_IN_SCOPE = ("SELECT paper_id FROM papers WHERE included=1 AND pdf_status='downloaded' "
             "AND pdf_filename IS NOT NULL AND paper_id NOT IN (SELECT loser_id FROM paper_merges)")


def reconcile_dispositions(conn: sqlite3.Connection) -> dict:
    """LEFT-JOIN reconciliation: every in-scope paper has exactly one disposition."""
    in_scope = {r[0] for r in conn.execute(_IN_SCOPE).fetchall()}
    rows = conn.execute(
        f"SELECT d.disposition, COUNT(*) FROM mmat_dispositions d "
        f"WHERE d.paper_id IN ({_IN_SCOPE}) GROUP BY d.disposition").fetchall()
    counts = {r[0]: r[1] for r in rows}
    dispositioned = sum(counts.values())
    return {"in_scope": len(in_scope), "dispositioned": dispositioned,
            "counts": counts, "balanced": dispositioned == len(in_scope)}
