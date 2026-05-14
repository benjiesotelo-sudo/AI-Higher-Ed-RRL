"""Unpaywall: find the authoritative OA PDF URL for a DOI.
Per spec, Unpaywall OVERRIDES OpenAlex's oa_pdf_url.

Resumability: papers are tracked via unpaywall_checked_at so a killed run
picks back up where it left off.
"""
from __future__ import annotations
import logging
import sqlite3
import time

import requests

from rrl.config import RATE_PLANS
from rrl.http import RateLimitedSession

log = logging.getLogger(__name__)

BASE = "https://api.unpaywall.org/v2/"
PROGRESS_INTERVAL = 200


def lookup_doi(session, doi: str, email: str) -> tuple[str | None, str | None]:
    """Returns (pdf_url, oa_status). Returns (None, 'not_found') on 404.
    Raises requests.HTTPError on other non-2xx after retries are exhausted."""
    r = session.get(BASE + doi, params={"email": email})
    if r.status_code == 404:
        return None, "not_found"
    r.raise_for_status()
    payload = r.json()
    loc = payload.get("best_oa_location") or {}
    return loc.get("url_for_pdf"), payload.get("oa_status")


def _wrap_rate_limited(session: requests.Session) -> RateLimitedSession | requests.Session:
    rps = RATE_PLANS.get("unpaywall", {}).get("requests_per_second")
    if not rps:
        return session
    return RateLimitedSession(session, requests_per_second=rps)


def enrich_papers_with_unpaywall(conn: sqlite3.Connection, session: requests.Session, email: str) -> dict:
    """Look up every unchecked paper with a DOI and overwrite oa_pdf_url
    when Unpaywall has one. Unpaywall is authoritative over OpenAlex per spec.

    - Skips papers whose unpaywall_checked_at is already set (resumability).
    - Catches errors per-DOI; logs and continues.
    - Rate-limits client-side per RATE_PLANS['unpaywall'].
    - Logs progress every PROGRESS_INTERVAL papers.
    """
    sess = _wrap_rate_limited(session)
    rows = conn.execute(
        """SELECT paper_id, doi FROM papers
           WHERE doi IS NOT NULL AND unpaywall_checked_at IS NULL"""
    ).fetchall()
    total = len(rows)
    log.info("unpaywall: %d paper(s) to check", total)
    updated = errored = not_found = no_pdf = 0
    started = time.monotonic()
    for i, row in enumerate(rows, start=1):
        doi = row["doi"]
        pid = row["paper_id"]
        try:
            pdf, status = lookup_doi(sess, doi, email)
        except Exception as exc:
            errored += 1
            log.warning("unpaywall lookup failed for %s (%s): %s", pid, doi, exc)
            conn.execute(
                "UPDATE papers SET unpaywall_checked_at=datetime('now') WHERE paper_id=?",
                (pid,),
            )
        else:
            if pdf:
                conn.execute(
                    """UPDATE papers SET oa_pdf_url=?, oa_status=COALESCE(?, oa_status),
                       unpaywall_checked_at=datetime('now'),
                       last_updated_at=datetime('now') WHERE paper_id=?""",
                    (pdf, status, pid),
                )
                updated += 1
            else:
                conn.execute(
                    """UPDATE papers SET unpaywall_checked_at=datetime('now'),
                       last_updated_at=datetime('now') WHERE paper_id=?""",
                    (pid,),
                )
                if status == "not_found":
                    not_found += 1
                else:
                    no_pdf += 1
        if i % PROGRESS_INTERVAL == 0 or i == total:
            elapsed = time.monotonic() - started
            rate = i / elapsed if elapsed > 0 else 0.0
            log.info(
                "unpaywall: %d/%d (updated=%d errored=%d not_found=%d no_pdf=%d) %.1f req/s",
                i, total, updated, errored, not_found, no_pdf, rate,
            )
    return {
        "checked": total,
        "updated": updated,
        "errored": errored,
        "not_found": not_found,
        "no_pdf": no_pdf,
    }
