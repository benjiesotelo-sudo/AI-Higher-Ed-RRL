"""Unpaywall: find the authoritative OA PDF URL for a DOI.
Per spec, Unpaywall OVERRIDES OpenAlex's oa_pdf_url."""
from __future__ import annotations
import sqlite3

import requests

BASE = "https://api.unpaywall.org/v2/"

def lookup_doi(session: requests.Session, doi: str, email: str) -> tuple[str | None, str | None]:
    r = session.get(BASE + doi, params={"email": email})
    if r.status_code == 404:
        return None, "not_found"
    r.raise_for_status()
    payload = r.json()
    loc = payload.get("best_oa_location") or {}
    return loc.get("url_for_pdf"), payload.get("oa_status")

def enrich_papers_with_unpaywall(conn: sqlite3.Connection, session: requests.Session, email: str) -> dict:
    """Look up every paper with a DOI and overwrite oa_pdf_url when Unpaywall has one.
    Unpaywall is authoritative over OpenAlex per spec."""
    rows = conn.execute(
        "SELECT paper_id, doi FROM papers WHERE doi IS NOT NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        pdf, status = lookup_doi(session, row["doi"], email)
        if pdf:
            conn.execute(
                """UPDATE papers SET oa_pdf_url=?, oa_status=COALESCE(?, oa_status),
                   last_updated_at=datetime('now') WHERE paper_id=?""",
                (pdf, status, row["paper_id"]),
            )
            updated += 1
    return {"updated": updated, "checked": len(rows)}
