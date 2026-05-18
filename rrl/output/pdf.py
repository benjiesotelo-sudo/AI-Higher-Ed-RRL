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

def download_pdfs(conn: sqlite3.Connection, session: requests.Session, *,
                  pdf_root: Path, core_api_key: str | None,
                  elsevier_api_key: str | None = None,
                  retry_failed: bool = False) -> dict:
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
    for i, r in enumerate(rows, start=1):
        pid, doi, title, year, oa_url = r["paper_id"], r["doi"], r["title"], r["year"], r["oa_pdf_url"]
        dest = pdf_root / str(year) / f"{pid}.pdf"
        # Each attempt is a 3-tuple: (source, url, headers_dict_or_None)
        attempts: list[tuple[str, str, dict | None]] = []
        if oa_url:
            attempts.append(("oa", oa_url, None))
        if doi and core_api_key:
            core_url = find_pdf_by_doi(session, doi, api_key=core_api_key)
            if core_url:
                attempts.append(("core_doi", core_url, None))
        if title and core_api_key:
            core_url = find_pdf_by_title(session, title, api_key=core_api_key)
            if core_url:
                attempts.append(("core_title", core_url, None))
        if doi and elsevier_api_key and doi.startswith("10.1016/"):
            attempts.append((
                "sciencedirect",
                f"https://api.elsevier.com/content/article/doi/{doi}",
                {"X-ELS-APIKey": elsevier_api_key, "Accept": "application/pdf"},
            ))
        ok = False
        for source, url, headers in attempts:
            if _try_url(session, url, source, pid, conn, dest, headers=headers):
                ok = True
                break
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
                "pdf: %d/%d (downloaded=%d failed=%d) %.2f papers/s",
                i, total, counts["downloaded"], counts["failed"], rate,
            )
    return counts
