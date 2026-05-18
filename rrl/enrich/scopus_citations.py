"""Scopus: citation_count fallback when OpenAlex didn't provide one.

Resumability: papers are tracked via scopus_checked_at so a killed run
picks back up where it left off. Skips papers that already have a
citation_count from a prior enrichment pass.
"""
from __future__ import annotations
import logging
import sqlite3
import time

import requests

from rrl.config import RATE_PLANS
from rrl.http import RateLimitedSession

log = logging.getLogger(__name__)

BASE = "https://api.elsevier.com/content/abstract/doi/"
PROGRESS_INTERVAL = 100


def lookup_citations(session, doi: str, *, api_key: str, inst_token: str | None = None) -> int | None:
    """Return citation_count for a DOI, or None if not found / not parseable."""
    headers = {"X-ELS-APIKey": api_key, "Accept": "application/json"}
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token
    r = session.get(BASE + doi, headers=headers)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    payload = r.json()
    coredata = (payload.get("abstracts-retrieval-response") or {}).get("coredata") or {}
    raw = coredata.get("citedby-count")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _wrap_rate_limited(session: requests.Session) -> RateLimitedSession | requests.Session:
    rps = RATE_PLANS.get("scopus", {}).get("requests_per_second")
    if not rps:
        return session
    return RateLimitedSession(session, requests_per_second=rps)


def enrich_papers_with_scopus(
    conn: sqlite3.Connection,
    session: requests.Session,
    *,
    api_key: str | None,
    inst_token: str | None = None,
) -> dict:
    """Look up Scopus citation_count for every paper that has a DOI, no count,
    and hasn't been checked yet."""
    if not api_key:
        log.info("scopus_citations: no api_key set, skipping")
        return {"checked": 0, "updated": 0, "errored": 0, "skipped_no_key": True}

    sess = _wrap_rate_limited(session)
    rows = conn.execute(
        """SELECT paper_id, doi FROM papers
           WHERE doi IS NOT NULL
             AND citation_count IS NULL
             AND scopus_checked_at IS NULL"""
    ).fetchall()
    total = len(rows)
    log.info("scopus_citations: %d paper(s) to check", total)
    updated = errored = 0
    started = time.monotonic()
    for i, row in enumerate(rows, start=1):
        doi = row["doi"]
        pid = row["paper_id"]
        try:
            n = lookup_citations(sess, doi, api_key=api_key, inst_token=inst_token)
        except Exception as exc:
            errored += 1
            log.warning("scopus citation lookup failed for %s (%s): %s", pid, doi, exc)
            conn.execute(
                "UPDATE papers SET scopus_checked_at=datetime('now') WHERE paper_id=?",
                (pid,),
            )
        else:
            if n is not None:
                conn.execute(
                    """UPDATE papers SET citation_count=?, scopus_checked_at=datetime('now'),
                       last_updated_at=datetime('now') WHERE paper_id=?""",
                    (n, pid),
                )
                updated += 1
            else:
                conn.execute(
                    "UPDATE papers SET scopus_checked_at=datetime('now') WHERE paper_id=?",
                    (pid,),
                )
        if i % PROGRESS_INTERVAL == 0 or i == total:
            elapsed = time.monotonic() - started
            rate = i / elapsed if elapsed > 0 else 0.0
            log.info(
                "scopus_citations: %d/%d (updated=%d errored=%d) %.1f req/s",
                i, total, updated, errored, rate,
            )
    return {"checked": total, "updated": updated, "errored": errored, "skipped_no_key": False}
