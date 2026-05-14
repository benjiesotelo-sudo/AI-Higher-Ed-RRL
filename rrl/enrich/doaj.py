"""DOAJ verification: is the paper's journal listed in DOAJ?"""
from __future__ import annotations
import json
import sqlite3

import requests

BASE = "https://doaj.org/api/v3/search/journals/issn:"

def lookup_issn(session: requests.Session, issn: str) -> bool:
    r = session.get(BASE + issn)
    if r.status_code == 404:
        return False
    r.raise_for_status()
    return bool(r.json().get("results"))

def _issn_for_paper(conn: sqlite3.Connection, paper_id: str) -> str | None:
    rows = conn.execute(
        """SELECT rr.raw_payload FROM raw_records rr
           JOIN paper_sources ps ON ps.raw_id = rr.raw_id
           WHERE ps.paper_id = ? AND rr.adapter = 'openalex'""",
        (paper_id,),
    ).fetchall()
    for r in rows:
        try:
            payload = json.loads(r["raw_payload"])
        except Exception:
            continue
        src = (payload.get("primary_location") or {}).get("source") or {}
        issn = src.get("issn_l") or (src.get("issn") or [None])[0]
        if issn:
            return issn
    return None

def enrich_papers_with_doaj(conn: sqlite3.Connection, session: requests.Session) -> dict:
    cache: dict[str, bool] = {}
    n_set = n_skipped = 0
    papers = conn.execute("SELECT paper_id FROM papers WHERE is_in_doaj IS NULL").fetchall()
    for row in papers:
        pid = row["paper_id"]
        issn = _issn_for_paper(conn, pid)
        if not issn:
            n_skipped += 1
            continue
        if issn not in cache:
            cache[issn] = lookup_issn(session, issn)
        conn.execute("UPDATE papers SET is_in_doaj=?, last_updated_at=datetime('now') WHERE paper_id=?",
                     (1 if cache[issn] else 0, pid))
        n_set += 1
    return {"updated": n_set, "skipped_no_issn": n_skipped}
