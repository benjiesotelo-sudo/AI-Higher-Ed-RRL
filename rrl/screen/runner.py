"""Apply screening decisions to every paper. Pure SQL + regex; no network."""
from __future__ import annotations
import sqlite3
from collections import Counter

from langdetect import detect, DetectorFactory, LangDetectException
DetectorFactory.seed = 0

from rrl.screen.rules import evaluate_paper

PAPER_COLS = ("paper_id", "title", "abstract", "venue", "year", "language",
              "is_oa", "oa_pdf_url", "is_peer_reviewed", "is_in_doaj",
              "work_type", "publisher", "citation_count")

def run_screen(conn: sqlite3.Connection, *, dry_run: bool = False) -> dict:
    rows = conn.execute(f"SELECT {','.join(PAPER_COLS)} FROM papers").fetchall()
    counts: Counter = Counter()
    for r in rows:
        paper = {c: r[c] for c in PAPER_COLS}
        if not paper.get("language") and paper.get("abstract"):
            try:
                detected = detect(paper["abstract"])
            except LangDetectException:
                detected = None
            if detected is not None:
                paper["language"] = detected
                if not dry_run:
                    conn.execute(
                        "UPDATE papers SET language=? WHERE paper_id=?",
                        (detected, paper["paper_id"]),
                    )
        decision = evaluate_paper(paper)
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
