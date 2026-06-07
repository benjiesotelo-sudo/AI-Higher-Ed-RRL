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
