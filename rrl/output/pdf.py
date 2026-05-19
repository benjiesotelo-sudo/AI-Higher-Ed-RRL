"""PDF download with magic-byte validation, retries, and attempt logging."""
from __future__ import annotations
import logging
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from rrl.search.core_api import find_pdf_by_doi, find_pdf_by_title

log = logging.getLogger(__name__)

MIN_BYTES = 10 * 1024  # 10KB
PROGRESS_INTERVAL = 25

# CORE free-tier guards. The free tier is 10 req/min ≈ 14,400/day; we pace at
# 6.5s between calls and bound the per-run total so that a single bad batch
# can't burn the day's budget. Tunable via the download_pdfs() signature.
CORE_MIN_INTERVAL_SEC = 6.5
CORE_DEFAULT_BUDGET = 14_400

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def validate_pdf_bytes(data: bytes) -> bool:
    if not data.startswith(b"%PDF-"):
        return False
    if len(data) < MIN_BYTES:
        return False
    return True

def _log_attempt(conn, paper_id, source, url, status, content_type, n_bytes, outcome, err=None):
    conn.execute(
        """INSERT INTO pdf_attempts (paper_id, source, url, http_status, content_type,
           bytes_received, outcome, error_message, attempted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (paper_id, source, url, status, content_type, n_bytes, outcome, err, _now()),
    )

def _try_url(session, url, source, paper_id, conn, dest: Path,
             headers: dict | None = None) -> bool:
    try:
        r = session.get(url, timeout=60, headers=headers or {})
    except requests.exceptions.Timeout as e:
        _log_attempt(conn, paper_id, source, url, None, None, 0, "timeout", str(e))
        return False
    except Exception as e:
        _log_attempt(conn, paper_id, source, url, None, None, 0, "http_error", str(e))
        return False
    data = r.content
    if r.status_code != 200:
        _log_attempt(conn, paper_id, source, url, r.status_code, r.headers.get("Content-Type"), len(data), "http_error")
        return False
    if not validate_pdf_bytes(data):
        _log_attempt(conn, paper_id, source, url, r.status_code, r.headers.get("Content-Type"), len(data), "not_pdf")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    _log_attempt(conn, paper_id, source, url, r.status_code, r.headers.get("Content-Type"), len(data), "ok")
    return True

class _CoreBudget:
    """Tracks CORE call count + minimum spacing to stay under the rate limit."""

    def __init__(self, budget: int, min_interval: float):
        self.remaining = max(0, int(budget))
        self.min_interval = float(min_interval)
        self._last_call: float = 0.0

    def can_call(self) -> bool:
        return self.remaining > 0

    def before_call(self) -> None:
        # Sleep just enough to keep us at <= 1 call per min_interval seconds.
        if self.min_interval > 0:
            wait = self.min_interval - (time.monotonic() - self._last_call)
            if wait > 0:
                time.sleep(wait)

    def record(self) -> None:
        self.remaining -= 1
        self._last_call = time.monotonic()


def _try_core_lookup(session, *, lookup_fn, arg: str, api_key: str,
                     budget: _CoreBudget) -> str | None:
    """Wrapper that enforces budget + throttle around a CORE call."""
    if not budget.can_call():
        return None
    budget.before_call()
    try:
        url = lookup_fn(session, arg, api_key=api_key)
    finally:
        budget.record()
    return url


def _retrieval_cascade(session, *, paper, dest: Path, conn,
                       core_api_key: str | None, elsevier_api_key: str | None,
                       core_budget: _CoreBudget) -> bool:
    """Try sources in priority order, stopping at the first success.

    Order: oa_pdf_url → CORE-by-DOI → CORE-by-title → ScienceDirect (Elsevier
    DOIs only). CORE is intentionally LAZY — it's only invoked after the OA
    URL has failed, so a successful oa download burns zero CORE budget.
    """
    pid, doi, title = paper["paper_id"], paper["doi"], paper["title"]
    oa_url = paper["oa_pdf_url"]

    if oa_url and _try_url(session, oa_url, "oa", pid, conn, dest):
        return True
    if doi and core_api_key:
        core_url = _try_core_lookup(
            session, lookup_fn=find_pdf_by_doi, arg=doi,
            api_key=core_api_key, budget=core_budget,
        )
        if core_url and _try_url(session, core_url, "core_doi", pid, conn, dest):
            return True
    if title and core_api_key:
        core_url = _try_core_lookup(
            session, lookup_fn=find_pdf_by_title, arg=title,
            api_key=core_api_key, budget=core_budget,
        )
        if core_url and _try_url(session, core_url, "core_title", pid, conn, dest):
            return True
    if doi and elsevier_api_key and doi.startswith("10.1016/"):
        sd_url = f"https://api.elsevier.com/content/article/doi/{doi}"
        sd_headers = {"X-ELS-APIKey": elsevier_api_key, "Accept": "application/pdf"}
        if _try_url(session, sd_url, "sciencedirect", pid, conn, dest, headers=sd_headers):
            return True
    return False


def download_pdfs(conn: sqlite3.Connection, session: requests.Session, *,
                  pdf_root: Path, core_api_key: str | None,
                  elsevier_api_key: str | None = None,
                  retry_failed: bool = False,
                  core_budget: int = CORE_DEFAULT_BUDGET) -> dict:
    where = "included = 1 AND pdf_status IS NULL"
    if retry_failed:
        where = "included = 1 AND (pdf_status IS NULL OR pdf_status IN ('oa_link_dead', 'not_retrievable'))"
    rows = conn.execute(
        f"SELECT paper_id, doi, title, year, oa_pdf_url FROM papers WHERE {where}"
    ).fetchall()
    total = len(rows)
    log.info("pdf: %d paper(s) to download", total)
    started = time.monotonic()
    counts = {"downloaded": 0, "failed": 0}
    budget = _CoreBudget(core_budget, CORE_MIN_INTERVAL_SEC)
    for i, r in enumerate(rows, start=1):
        pid, year = r["paper_id"], r["year"]
        dest = pdf_root / str(year) / f"{pid}.pdf"
        ok = _retrieval_cascade(
            session, paper=r, dest=dest, conn=conn,
            core_api_key=core_api_key, elsevier_api_key=elsevier_api_key,
            core_budget=budget,
        )
        if ok:
            rel = str(dest.relative_to(pdf_root))
            conn.execute(
                "UPDATE papers SET pdf_filename=?, pdf_status='downloaded', last_updated_at=datetime('now') WHERE paper_id=?",
                (rel, pid),
            )
            counts["downloaded"] += 1
        else:
            conn.execute(
                "UPDATE papers SET pdf_status='not_retrievable', last_updated_at=datetime('now') WHERE paper_id=?",
                (pid,),
            )
            counts["failed"] += 1
        if i % PROGRESS_INTERVAL == 0 or i == total:
            elapsed = time.monotonic() - started
            rate = i / elapsed if elapsed > 0 else 0.0
            log.info(
                "pdf: %d/%d (downloaded=%d failed=%d core_remaining=%d) %.2f papers/s",
                i, total, counts["downloaded"], counts["failed"],
                budget.remaining, rate,
            )
    counts["core_remaining"] = budget.remaining
    return counts
