"""PDF download with magic-byte validation, retries, and attempt logging."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

from rrl.search.core_api import find_pdf_by_doi, find_pdf_by_title

MIN_BYTES = 10 * 1024  # 10KB

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

def _try_url(session, url, source, paper_id, conn, dest: Path) -> bool:
    try:
        r = session.get(url, timeout=60)
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
                  retry_failed: bool = False) -> dict:
    where = "included = 1 AND pdf_status IS NULL"
    if retry_failed:
        where = "included = 1 AND (pdf_status IS NULL OR pdf_status = 'oa_link_dead')"
    rows = conn.execute(
        f"SELECT paper_id, doi, title, year, oa_pdf_url FROM papers WHERE {where}"
    ).fetchall()
    counts = {"downloaded": 0, "failed": 0}
    for r in rows:
        pid, doi, title, year, oa_url = r["paper_id"], r["doi"], r["title"], r["year"], r["oa_pdf_url"]
        dest = pdf_root / str(year) / f"{pid}.pdf"
        urls = []
        if oa_url:
            urls.append(("oa", oa_url))
        if doi and core_api_key:
            core_url = find_pdf_by_doi(session, doi, api_key=core_api_key)
            if core_url:
                urls.append(("core_doi", core_url))
        if title and core_api_key:
            core_url = find_pdf_by_title(session, title, api_key=core_api_key)
            if core_url:
                urls.append(("core_title", core_url))
        ok = False
        for source, url in urls:
            if _try_url(session, url, source, pid, conn, dest):
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
                "UPDATE papers SET pdf_status='oa_link_dead', last_updated_at=datetime('now') WHERE paper_id=?",
                (pid,),
            )
            counts["failed"] += 1
    return counts
