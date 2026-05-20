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

_MATRIX_FILTER = (
    "included = 1 AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"
)


def _counts(conn: sqlite3.Connection) -> dict:
    """Build the counts dict consumed by the manifest and the README appendix.

    All user-facing tier / era / PDF-status counts use the matrix-set filter
    (`included=1 AND NOT a fuzzy-merge loser`) so the numbers line up exactly
    with what's actually written to `output/rrl_matrix.xlsx`. The cumulative
    paper-table totals are also exposed (as `*_cumulative`) for audit, but
    they're not what gets reported to readers.
    """
    def n(sql: str, *a) -> int:
        return conn.execute(sql, a).fetchone()[0]

    raw = n("SELECT COUNT(*) FROM raw_records")
    after_dedup = n("SELECT COUNT(*) FROM papers")
    fuzzy_merges = n("SELECT COUNT(*) FROM paper_merges")
    matrix_total = n(f"SELECT COUNT(*) FROM papers WHERE {_MATRIX_FILTER}")

    # Dynamic exclusion-reason distribution: every reason currently in the
    # papers table, not a hardcoded list. Sorted desc by count to put the
    # biggest filters first.
    exclusion_rows = conn.execute(
        "SELECT exclusion_reason, COUNT(*) FROM papers "
        "WHERE included = 0 AND exclusion_reason IS NOT NULL "
        "GROUP BY exclusion_reason ORDER BY 2 DESC"
    ).fetchall()
    exclusions = {row[0]: row[1] for row in exclusion_rows}

    per_adapter_raw = dict(conn.execute(
        "SELECT adapter, COALESCE(SUM(records_new), 0) FROM search_runs GROUP BY adapter"
    ).fetchall())

    # PDF-attempt breakdown: which retrieval source delivered (or failed) each try.
    pdf_attempts_rows = conn.execute(
        "SELECT source, COUNT(*) AS attempts, "
        "       SUM(CASE WHEN outcome='ok' THEN 1 ELSE 0 END) AS downloads "
        "FROM pdf_attempts GROUP BY source ORDER BY downloads DESC"
    ).fetchall()
    per_source_attempts = [
        {"source": r[0], "attempts": r[1], "downloads": r[2] or 0}
        for r in pdf_attempts_rows
    ]

    return {
        "raw_records": raw,
        "papers_after_dedup": after_dedup,
        "fuzzy_merges": fuzzy_merges,
        # The legacy key name is kept for backwards-compat with the manifest
        # schema. Semantically this is now the matrix-set count, which is
        # what reviewers care about and what the xlsx actually contains.
        "papers_after_screen_included": matrix_total,
        "papers_in_matrix": matrix_total,
        # Cumulative count across the whole papers table, including merged-
        # loser rows that don't appear in the matrix. Exposed for audit; not
        # surfaced in the README narrative.
        "papers_after_screen_included_cumulative":
            n("SELECT COUNT(*) FROM papers WHERE included = 1"),
        "pdfs_downloaded": n(
            f"SELECT COUNT(*) FROM papers WHERE pdf_status='downloaded' AND {_MATRIX_FILTER}"
        ),
        "pdfs_not_retrievable": n(
            f"SELECT COUNT(*) FROM papers WHERE pdf_status='not_retrievable' AND {_MATRIX_FILTER}"
        ),
        "pdfs_downloaded_cumulative":
            n("SELECT COUNT(*) FROM papers WHERE pdf_status='downloaded'"),
        "pdfs_not_retrievable_cumulative":
            n("SELECT COUNT(*) FROM papers WHERE pdf_status='not_retrievable'"),
        "high_confidence": n(
            f"SELECT COUNT(*) FROM papers WHERE quality_tier='high_confidence' AND {_MATRIX_FILTER}"
        ),
        "review_needed": n(
            f"SELECT COUNT(*) FROM papers WHERE quality_tier='review_needed' AND {_MATRIX_FILTER}"
        ),
        "post_chatgpt": n(
            f"SELECT COUNT(*) FROM papers WHERE era_tag='post_chatgpt' AND {_MATRIX_FILTER}"
        ),
        "pre_chatgpt": n(
            f"SELECT COUNT(*) FROM papers WHERE era_tag='pre_chatgpt' AND {_MATRIX_FILTER}"
        ),
        "exclusion_reasons": exclusions,
        "per_adapter": per_adapter_raw,
        "per_source_pdf_attempts": per_source_attempts,
    }

def _pct(n: int, d: int) -> str:
    if d <= 0:
        return "n/a"
    return f"{100.0 * n / d:.1f}%"


def _format_appendix(counts: dict, runtimes: dict, run_at: str, pdf_summary: dict | None = None) -> str:
    raw = counts["raw_records"]
    after_dedup = counts["papers_after_dedup"]
    fuzzy_merges = counts.get("fuzzy_merges", 0)
    matrix_total = counts["papers_in_matrix"]
    excluded_total = sum(counts.get("exclusion_reasons", {}).values())
    downloaded = counts.get("pdfs_downloaded", counts.get("pdfs_downloaded_cumulative", 0))
    not_retrievable = counts.get("pdfs_not_retrievable", counts.get("pdfs_not_retrievable_cumulative", 0))
    pdf_total = downloaded + not_retrievable
    dedup_collapse = raw - after_dedup
    matrix_after_merge = after_dedup - fuzzy_merges

    lines = [
        "## Run statistics",
        "",
        f"_Last run: {run_at}_",
        "",
        "**Corpus pipeline** — what happened, stage by stage",
        f"- raw_records: **{raw:,}** — harvested across all configured search adapters",
        f"- after exact-key dedup: **{after_dedup:,}** — collapsed {dedup_collapse:,} duplicates "
            f"({_pct(dedup_collapse, raw)} dedup rate) via the DOI → OpenAlex ID → "
            f"title+year+author cascade",
        f"- after fuzzy-merge pass: **{matrix_after_merge:,}** — an additional **{fuzzy_merges:,}** "
            f"DOI-less duplicates collapsed by the first-6-words + year + author-surname fingerprint",
        f"- excluded by screening: **{excluded_total:,}** "
            f"({_pct(excluded_total, matrix_after_merge)} of post-dedup) — one canonical reason per paper",
        f"- in matrix (included, non-merged): **{matrix_total:,}** — the final analysis set",
        "",
        "**By quality tier** _(matrix set)_",
        f"- high_confidence: **{counts['high_confidence']:,}** "
            f"({_pct(counts['high_confidence'], matrix_total)}) — work_type article + "
            f"citations ≥ 1 or recent + abstract ≥ 400 chars + DOAJ/major publisher",
        f"- review_needed: **{counts['review_needed']:,}** "
            f"({_pct(counts['review_needed'], matrix_total)}) — surfaced for manual review",
        "",
        "**By era** _(matrix set)_",
        f"- post_chatgpt (2023–2026): **{counts['post_chatgpt']:,}**",
        f"- pre_chatgpt (2020–2022): **{counts['pre_chatgpt']:,}**",
        "",
        "**Exclusion reasons** _(first filter to fire wins)_",
    ]
    for reason, n in counts.get("exclusion_reasons", {}).items():
        lines.append(f"- {reason}: **{n:,}**")
    lines += [
        "",
        "**By source adapter** _(records contributed before dedup)_",
    ]
    for adapter, n in sorted(counts.get("per_adapter", {}).items(),
                             key=lambda kv: -kv[1]):
        lines.append(f"- {adapter}: **{n:,}**")
    lines += [
        "",
        "**PDF retrieval** _(matrix set)_",
        f"- downloaded: **{downloaded:,}** "
            f"({_pct(downloaded, pdf_total) if pdf_total else 'n/a'} success rate)",
        f"- not_retrievable: **{not_retrievable:,}** — candidate worklist for "
            f"interlibrary-loan retrieval",
        "",
        "**Per-source PDF attempts** _(which retrieval source delivered each download)_",
        "",
        "| Source | Downloads | Attempts | Hit rate |",
        "|---|---:|---:|---:|",
    ]
    for row in counts.get("per_source_pdf_attempts", []):
        src, atts, downs = row["source"], row["attempts"], row["downloads"]
        lines.append(f"| {src} | {downs:,} | {atts:,} | {_pct(downs, atts)} |")
    lines += [
        "",
        "**Stage runtimes (seconds)**",
        *(f"- {k}: {v:.1f}" for k, v in runtimes.items()),
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
