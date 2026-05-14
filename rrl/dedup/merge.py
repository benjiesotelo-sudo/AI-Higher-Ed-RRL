"""Manual merge: write paper_merges row and migrate paper_sources / pdf metadata."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def merge_papers(conn: sqlite3.Connection, loser_id: str, winner_id: str, pdf_root: Path) -> None:
    for pid in (loser_id, winner_id):
        if conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (pid,)).fetchone() is None:
            raise ValueError(f"unknown paper_id {pid}")
    if loser_id == winner_id:
        raise ValueError("loser and winner must differ")

    conn.execute(
        "INSERT OR REPLACE INTO paper_merges (loser_id, winner_id, merged_at, merged_by) VALUES (?,?,?,?)",
        (loser_id, winner_id, _now(), "manual"),
    )
    conn.execute(
        """INSERT OR IGNORE INTO paper_sources (paper_id, raw_id)
           SELECT ?, raw_id FROM paper_sources WHERE paper_id=?""",
        (winner_id, loser_id),
    )
    conn.execute("DELETE FROM paper_sources WHERE paper_id=?", (loser_id,))

    loser_pdf = conn.execute("SELECT pdf_filename FROM papers WHERE paper_id=?", (loser_id,)).fetchone()["pdf_filename"]
    winner_pdf = conn.execute("SELECT pdf_filename FROM papers WHERE paper_id=?", (winner_id,)).fetchone()["pdf_filename"]
    if loser_pdf and not winner_pdf:
        src = pdf_root / loser_pdf
        if src.exists():
            new_name = src.with_name(f"{winner_id}.pdf")
            src.rename(new_name)
            rel = str(new_name.relative_to(pdf_root))
            conn.execute("UPDATE papers SET pdf_filename=?, pdf_status='downloaded' WHERE paper_id=?", (rel, winner_id))
        conn.execute("UPDATE papers SET pdf_status='merged_to_winner', pdf_filename=NULL WHERE paper_id=?", (loser_id,))

    for col in ("is_in_doaj", "is_peer_reviewed", "is_oa", "oa_status", "oa_pdf_url",
                "citation_count", "publisher", "work_type"):
        conn.execute(
            f"UPDATE papers SET {col}=(SELECT {col} FROM papers WHERE paper_id=?) "
            f"WHERE paper_id=? AND {col} IS NULL",
            (loser_id, winner_id),
        )
