"""Write data/dedup_review.csv: pairs of likely-duplicate papers for manual judgment."""
from __future__ import annotations
import csv
import json
import sqlite3
from itertools import combinations
from pathlib import Path

from rapidfuzz.fuzz import token_sort_ratio

THRESHOLD = 85.0

def write_review_csv(conn: sqlite3.Connection, out_path: Path) -> int:
    rows = conn.execute(
        """SELECT paper_id, title, year, authors_json FROM papers
           WHERE paper_id NOT IN (SELECT loser_id FROM paper_merges)"""
    ).fetchall()
    blocks: dict[tuple, list[sqlite3.Row]] = {}
    for r in rows:
        authors = json.loads(r["authors_json"]) or [{}]
        first = (authors[0] or {}).get("family", "") or ""
        key = (first[:1].lower(), r["year"])
        blocks.setdefault(key, []).append(r)
    pairs: list[tuple[float, str, str, str, str]] = []
    for block in blocks.values():
        for a, b in combinations(block, 2):
            score = token_sort_ratio(a["title"], b["title"])
            if score >= THRESHOLD:
                pairs.append((score, a["paper_id"], a["title"], b["paper_id"], b["title"]))
    pairs.sort(reverse=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["similarity", "paper_id_a", "title_a", "paper_id_b", "title_b"])
        for row in pairs:
            w.writerow(row)
    return len(pairs)
