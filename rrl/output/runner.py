"""End-to-end export: PDFs → xlsx → manifest → README appendix."""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path

import requests

from rrl.output.pdf import download_pdfs
from rrl.output.matrix import write_matrix
from rrl.output.readme import update_appendix
from rrl.output.manifest import build_manifest, write_manifest

def _counts(conn: sqlite3.Connection) -> dict:
    def n(sql: str, *a) -> int:
        return conn.execute(sql, a).fetchone()[0]
    result = {
        "raw_records": n("SELECT COUNT(*) FROM raw_records"),
        "papers_after_dedup": n("SELECT COUNT(*) FROM papers"),
        "papers_after_screen_included": n("SELECT COUNT(*) FROM papers WHERE included = 1"),
        "papers_in_matrix": n(
            """SELECT COUNT(*) FROM papers
               WHERE included = 1 AND pdf_status = 'downloaded'
               AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"""
        ),
        "pdfs_downloaded_cumulative": n("SELECT COUNT(*) FROM papers WHERE pdf_status='downloaded'"),
        "pdfs_failed_cumulative": n("SELECT COUNT(*) FROM papers WHERE pdf_status='oa_link_dead'"),
        "high_confidence": n("SELECT COUNT(*) FROM papers WHERE quality_tier='high_confidence' AND pdf_status='downloaded' AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"),
        "review_needed": n("SELECT COUNT(*) FROM papers WHERE quality_tier='review_needed' AND pdf_status='downloaded' AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"),
        "excluded_off_topic": n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='off_topic'"),
        "excluded_not_oa":    n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='not_oa'"),
        "excluded_non_english": n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='non_english'"),
        "excluded_k12_only":  n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='k12_only'"),
        "excluded_wrong_date": n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='wrong_date'"),
        "post_chatgpt": n("SELECT COUNT(*) FROM papers WHERE era_tag='post_chatgpt' AND included=1"),
        "pre_chatgpt":  n("SELECT COUNT(*) FROM papers WHERE era_tag='pre_chatgpt'  AND included=1"),
    }
    per_adapter = dict(conn.execute(
        "SELECT adapter, COALESCE(SUM(records_new), 0) FROM search_runs GROUP BY adapter"
    ).fetchall())
    result["per_adapter"] = per_adapter
    return result

def _format_appendix(counts: dict, runtimes: dict, run_at: str, pdf_summary: dict | None = None) -> str:
    per_adapter = counts.get("per_adapter", {})
    # Report cumulative PDF stats from the DB (counts dict) rather than just
    # this run's attempts. Re-running export on an already-populated corpus
    # otherwise prints "0 downloaded / 0 failed", which is misleading.
    downloaded = counts.get("pdfs_downloaded_cumulative", 0)
    failed = counts.get("pdfs_failed_cumulative", 0)
    rate = 100.0 * downloaded / max(downloaded + failed, 1)
    lines = [
        "## Run statistics",
        "",
        f"_Last run: {run_at}_",
        "",
        "**Corpus summary**",
        f"- raw_records: {counts['raw_records']}",
        f"- after dedup: {counts['papers_after_dedup']}",
        f"- after screen (included): {counts['papers_after_screen_included']}",
        f"- in matrix: {counts['papers_in_matrix']}",
        "",
        "**By quality tier**",
        f"- high_confidence: {counts['high_confidence']}",
        f"- review_needed: {counts['review_needed']}",
        "",
        "**By era**",
        f"- post_chatgpt: {counts['post_chatgpt']}",
        f"- pre_chatgpt: {counts['pre_chatgpt']}",
        "",
        "**Exclusions**",
        f"- off_topic: {counts['excluded_off_topic']}",
        f"- not_oa: {counts['excluded_not_oa']}",
        f"- non_english: {counts['excluded_non_english']}",
        f"- k12_only: {counts['excluded_k12_only']}",
        f"- wrong_date: {counts['excluded_wrong_date']}",
        "",
        "**Stage runtimes (seconds)**",
        *(f"- {k}: {v:.1f}" for k, v in runtimes.items()),
        "",
        "**By source adapter** _(records contributed before dedup)_",
        *(f"- {adapter}: {n}" for adapter, n in sorted(per_adapter.items())),
        "",
        "**PDF download success**",
        f"- downloaded: {downloaded}",
        f"- failed: {failed}",
        f"- success rate: {rate:.1f}%",
    ]
    return "\n".join(lines)

def run_export(db: Path, *, session: requests.Session, pdf_root: Path, matrix_path: Path,
               manifest_path: Path, readme_path: Path, core_api_key: str | None,
               elsevier_api_key: str | None = None,
               retry_failed: bool = False) -> dict:
    from rrl.db import connect, init_schema
    conn = connect(db); init_schema(conn)

    runtimes: dict[str, float] = {}
    t0 = time.monotonic()
    pdf_summary = download_pdfs(conn, session, pdf_root=pdf_root, core_api_key=core_api_key,
                                elsevier_api_key=elsevier_api_key,
                                retry_failed=retry_failed)
    runtimes["export_pdf"] = time.monotonic() - t0

    t0 = time.monotonic()
    matrix_counts = write_matrix(conn, matrix_path)
    runtimes["export_matrix"] = time.monotonic() - t0

    counts = _counts(conn)
    manifest = build_manifest(counts=counts, runtimes=runtimes, matrix_path=matrix_path)
    write_manifest(manifest_path, manifest)

    appendix = _format_appendix(counts, runtimes, manifest["run_at_utc"], pdf_summary=pdf_summary)
    update_appendix(readme_path, appendix)
    return {"pdfs": pdf_summary, "matrix": matrix_counts, "counts": counts}
