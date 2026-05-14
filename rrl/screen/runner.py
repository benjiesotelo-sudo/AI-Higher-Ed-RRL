"""Apply screening decisions to every paper. Pure SQL + regex; no network."""
from __future__ import annotations
import sqlite3
from collections import Counter

from rrl.screen.rules import evaluate_paper

PAPER_COLS = ("paper_id", "title", "abstract", "venue", "year", "language",
              "is_oa", "oa_pdf_url", "is_peer_reviewed", "is_in_doaj",
              "work_type", "publisher")

def run_screen(conn: sqlite3.Connection, *, dry_run: bool = False) -> dict:
    rows = conn.execute(f"SELECT {','.join(PAPER_COLS)} FROM papers").fetchall()
    counts: Counter = Counter()
    for r in rows:
        decision = evaluate_paper({c: r[c] for c in PAPER_COLS})
        if decision.get("included"):
            counts["included"] += 1
            counts[decision.get("quality_tier")] += 1
        else:
            counts["excluded"] += 1
            counts[decision.get("exclusion_reason")] += 1
        if dry_run:
            continue
        conn.execute(
            """UPDATE papers SET included=?, exclusion_reason=?, quality_tier=?,
               era_tag=?, topic_match_score=?, last_updated_at=datetime('now')
               WHERE paper_id=?""",
            (decision.get("included"), decision.get("exclusion_reason"),
             decision.get("quality_tier"), decision.get("era_tag"),
             decision.get("topic_match_score"), r["paper_id"]),
        )
    return dict(counts)
