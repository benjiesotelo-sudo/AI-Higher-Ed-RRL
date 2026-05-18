"""Lift OA / quality flags from cached OpenAlex raw payloads. No network."""
from __future__ import annotations
import json
import sqlite3

# OpenAlex's newer type taxonomy uses 'article' for what used to be
# 'journal-article'. Include both shapes so newly-indexed papers get the
# is_peer_reviewed flag set automatically.
PEER_REVIEWED_TYPES = {"journal-article", "article", "book-chapter", "proceedings-article", "review"}

def _flags_from_payload(payload: dict) -> dict:
    oa = payload.get("open_access") or {}
    loc = (payload.get("primary_location") or {}).get("source") or {}
    best_oa = payload.get("best_oa_location") or {}
    work_type = payload.get("type")
    source_type = loc.get("type")
    is_peer_reviewed = int(work_type in PEER_REVIEWED_TYPES and source_type != "repository")
    return {
        "is_oa": int(oa.get("is_oa", False)) if oa else None,
        "oa_status": oa.get("oa_status"),
        "oa_pdf_url": best_oa.get("pdf_url"),
        "work_type": work_type,
        "publisher": loc.get("host_organization_name"),
        "citation_count": payload.get("cited_by_count"),
        "is_peer_reviewed": is_peer_reviewed,
    }

def enrich_from_openalex_payloads(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """SELECT p.paper_id, rr.raw_payload FROM papers p
           JOIN paper_sources ps ON ps.paper_id = p.paper_id
           JOIN raw_records rr ON rr.raw_id = ps.raw_id
           WHERE rr.adapter = 'openalex'"""
    ).fetchall()
    updated = 0
    for row in rows:
        try:
            payload = json.loads(row["raw_payload"])
        except Exception:
            continue
        f = _flags_from_payload(payload)
        conn.execute(
            """UPDATE papers SET
                 is_oa=COALESCE(is_oa, ?),
                 oa_status=COALESCE(oa_status, ?),
                 oa_pdf_url=COALESCE(oa_pdf_url, ?),
                 work_type=COALESCE(work_type, ?),
                 publisher=COALESCE(publisher, ?),
                 citation_count=COALESCE(citation_count, ?),
                 is_peer_reviewed=COALESCE(is_peer_reviewed, ?),
                 last_updated_at=datetime('now')
               WHERE paper_id=?""",
            (f["is_oa"], f["oa_status"], f["oa_pdf_url"], f["work_type"], f["publisher"],
             f["citation_count"], f["is_peer_reviewed"], row["paper_id"]),
        )
        updated += 1
    return {"updated": updated}
