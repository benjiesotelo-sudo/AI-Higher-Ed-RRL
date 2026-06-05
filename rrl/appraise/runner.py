"""Phase-0 extraction runner: record one MMAT disposition per in-scope paper.

In scope = included, has a downloaded PDF, and is not a fuzzy-merge loser
(the same matrix filter used everywhere else). Idempotent: papers already in
mmat_dispositions are skipped, so the stage is resumable.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rrl.appraise.pdftext import extract_text

_IN_SCOPE_SQL = """
SELECT paper_id, pdf_filename FROM papers
WHERE included = 1
  AND pdf_status = 'downloaded'
  AND pdf_filename IS NOT NULL
  AND paper_id NOT IN (SELECT loser_id FROM paper_merges)
ORDER BY paper_id
"""


def in_scope_papers(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    return [(r["paper_id"], r["pdf_filename"])
            for r in conn.execute(_IN_SCOPE_SQL).fetchall()]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_extract(conn: sqlite3.Connection, pdf_root: Path) -> dict[str, int]:
    """Extract text + record a disposition for each not-yet-done in-scope paper.
    Returns a {disposition: count} dict for papers processed in THIS run."""
    pdf_root = Path(pdf_root)
    done = {r[0] for r in conn.execute("SELECT paper_id FROM mmat_dispositions").fetchall()}
    counts: dict[str, int] = {}
    for paper_id, pdf_filename in in_scope_papers(conn):
        if paper_id in done:
            continue
        res = extract_text(pdf_root / pdf_filename)
        conn.execute(
            "INSERT INTO mmat_dispositions (paper_id, disposition, detail, created_at) "
            "VALUES (?, ?, ?, ?)",
            (paper_id, res.disposition, res.detail, _now()),
        )
        counts[res.disposition] = counts.get(res.disposition, 0) + 1
    return counts
