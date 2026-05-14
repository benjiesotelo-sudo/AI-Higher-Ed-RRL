"""DOAJ verification: is the paper's journal listed in DOAJ?

Resumability: papers are tracked via doaj_checked_at so a killed run
picks back up where it left off (even papers with no resolvable ISSN
are recorded as checked, so we don't keep re-trying them).
"""
from __future__ import annotations
import json
import logging
import sqlite3
import time

import requests

from rrl.config import RATE_PLANS
from rrl.http import RateLimitedSession

log = logging.getLogger(__name__)

BASE = "https://doaj.org/api/v3/search/journals/issn:"
PROGRESS_INTERVAL = 200


def lookup_issn(session, issn: str) -> bool:
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


def _wrap_rate_limited(session: requests.Session) -> RateLimitedSession | requests.Session:
    rps = RATE_PLANS.get("doaj", {}).get("requests_per_second")
    if not rps:
        return session
    return RateLimitedSession(session, requests_per_second=rps)


def enrich_papers_with_doaj(conn: sqlite3.Connection, session: requests.Session) -> dict:
    """Look up every unchecked paper's journal in DOAJ.

    - Filters on doaj_checked_at IS NULL (resumable).
    - Caches per ISSN to avoid duplicate HTTP calls.
    - Per-paper try/except; logs and continues on lookup errors.
    - Rate-limits client-side per RATE_PLANS['doaj'].
    - Logs progress every PROGRESS_INTERVAL papers.
    """
    sess = _wrap_rate_limited(session)
    cache: dict[str, bool] = {}
    n_set = n_skipped = n_errored = 0
    papers = conn.execute(
        "SELECT paper_id FROM papers WHERE doaj_checked_at IS NULL"
    ).fetchall()
    total = len(papers)
    log.info("doaj: %d paper(s) to check", total)
    started = time.monotonic()
    for i, row in enumerate(papers, start=1):
        pid = row["paper_id"]
        issn = _issn_for_paper(conn, pid)
        if not issn:
            n_skipped += 1
            conn.execute(
                "UPDATE papers SET doaj_checked_at=datetime('now') WHERE paper_id=?",
                (pid,),
            )
        else:
            try:
                if issn not in cache:
                    cache[issn] = lookup_issn(sess, issn)
            except Exception as exc:
                n_errored += 1
                log.warning("doaj lookup failed for %s (issn=%s): %s", pid, issn, exc)
                conn.execute(
                    "UPDATE papers SET doaj_checked_at=datetime('now') WHERE paper_id=?",
                    (pid,),
                )
            else:
                conn.execute(
                    """UPDATE papers SET is_in_doaj=?, doaj_checked_at=datetime('now'),
                       last_updated_at=datetime('now') WHERE paper_id=?""",
                    (1 if cache[issn] else 0, pid),
                )
                n_set += 1
        if i % PROGRESS_INTERVAL == 0 or i == total:
            elapsed = time.monotonic() - started
            rate = i / elapsed if elapsed > 0 else 0.0
            log.info(
                "doaj: %d/%d (set=%d skipped_no_issn=%d errored=%d) %.1f req/s",
                i, total, n_set, n_skipped, n_errored, rate,
            )
    return {
        "checked": total,
        "updated": n_set,
        "skipped_no_issn": n_skipped,
        "errored": n_errored,
    }
