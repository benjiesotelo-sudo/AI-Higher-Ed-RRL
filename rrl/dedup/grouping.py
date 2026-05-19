"""Dedup cascade: DOI > OpenAlex ID > signature key > singleton."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from rrl.search.base import normalize_doi, normalize_title, normalize_author_name

SOURCE_PRIORITY = {"openalex": 0, "crossref": 1, "eric": 2, "s2": 3}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def compute_dedup_key(row: dict) -> str:
    doi = normalize_doi(row.get("doi"))
    if doi:
        return f"doi:{doi}"
    oa = row.get("openalex_id")
    if oa:
        return f"openalex:{oa}"
    title = row.get("title_norm") or ""
    year = row.get("year")
    fa = row.get("first_author")
    if title and year and fa:
        return f"sig:{title}|{year}|{fa}"
    return f"singleton:raw_{row['raw_id']}"

def paper_id_from_key(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def _openalex_id_from_payload(payload_json: str) -> str | None:
    try:
        payload = json.loads(payload_json)
    except Exception:
        return None
    pid = payload.get("id")
    if isinstance(pid, str) and "openalex.org/" in pid:
        return pid.rsplit("/", 1)[-1]
    return None

def _by_source_priority(rows: Iterable[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: SOURCE_PRIORITY.get(r["adapter"], 99))

def build_canonical_paper(raws: list[dict]) -> dict:
    ordered = _by_source_priority(raws)
    doi = next((r["doi"] for r in raws if r.get("doi")), None)
    title = max((r["title"] for r in ordered if r.get("title")),
                key=lambda t: len(t), default="")
    authors_json = next((r["authors_json"] for r in ordered if r.get("authors_json")), "[]")
    year = min((r["year"] for r in raws if r.get("year") is not None), default=None)
    venue = next((r["venue"] for r in ordered if r.get("venue")), None)
    abstract = max((r["abstract"] for r in raws if r.get("abstract")),
                   key=lambda a: len(a), default=None)
    language = next((r["language"] for r in ordered if r.get("language")), None)
    return {
        "doi": doi,
        "title": title,
        "authors_json": authors_json,
        "year": year,
        "venue": venue,
        "abstract": abstract,
        "language": language,
    }

def _row_for_key(r: sqlite3.Row) -> dict:
    return {
        "raw_id": r["raw_id"],
        "adapter": r["adapter"],
        "doi": r["doi"],
        "title": r["title"],
        "title_norm": r["title_norm"],
        "authors_json": r["authors_json"],
        "first_author": r["first_author"],
        "year": r["year"],
        "venue": r["venue"],
        "abstract": r["abstract"],
        "language": r["language"],
        "openalex_id": _openalex_id_from_payload(r["raw_payload"]),
        "raw_payload": r["raw_payload"],
    }

# How many words of the normalized title to use in the fuzzy fingerprint.
# Six words is a compromise: long enough to distinguish unrelated papers, short
# enough that a paper with vs without a subtitle still shares the prefix.
# (A subtitle bumps a paper from N words to N+M; capping at 6 ensures the
# fingerprint stays anchored to the main title clause for typical academic
# titles.) The min-words gate prevents trivial titles from collapsing.
FUZZY_TITLE_WORDS = 6
FUZZY_TITLE_MIN_WORDS = 4
FUZZY_AUTHOR_LIMIT = 3


def fuzzy_fingerprint(title: str | None, year: int | None, authors_json: str | None) -> str | None:
    """Build a fingerprint that ignores subtitle and author-ordering differences.

    Returns None if the inputs are too thin to make a reliable match (very
    short titles, missing year, no parseable authors). Two papers with the
    same fingerprint are treated as the same paper by fuzzy_merge_pass.
    """
    if not title or year is None or not authors_json:
        return None
    norm = normalize_title(title)
    words = norm.split()
    if len(words) < FUZZY_TITLE_MIN_WORDS:
        return None
    head = " ".join(words[:FUZZY_TITLE_WORDS])
    try:
        authors = json.loads(authors_json) or []
    except (TypeError, ValueError):
        return None
    surnames = {
        normalize_author_name(a.get("family") or "")
        for a in authors if isinstance(a, dict)
    }
    surnames = sorted(s for s in surnames if s)
    if not surnames:
        return None
    author_sig = "+".join(surnames[:FUZZY_AUTHOR_LIMIT])
    return f"{head}|{year}|{author_sig}"


def fuzzy_merge_pass(conn: sqlite3.Connection, pdf_root: Path) -> int:
    """Second-pass dedup: merge papers that share a fuzzy fingerprint.

    Operates on the papers table after run_dedup. A paper without a DOI that
    fingerprint-matches another paper (with or without a DOI) is merged into
    the other, with DOI-bearing papers winning over DOI-less ones. Returns
    the number of merges performed.
    """
    from rrl.dedup.merge import merge_papers  # local import: avoids cycle

    rows = conn.execute(
        "SELECT paper_id, doi, title, year, authors_json FROM papers"
    ).fetchall()
    by_fp: dict[str, list[tuple[str, str | None]]] = defaultdict(list)
    for r in rows:
        fp = fuzzy_fingerprint(r["title"], r["year"], r["authors_json"])
        if fp is None:
            continue
        by_fp[fp].append((r["paper_id"], r["doi"]))

    merges = 0
    for fp, paper_list in by_fp.items():
        if len(paper_list) < 2:
            continue
        # Pick canonical: prefer paper with DOI; tie-break by paper_id for determinism.
        ordered = sorted(paper_list, key=lambda x: (x[1] is None or x[1] == "", x[0]))
        winner = ordered[0][0]
        for loser, _ in ordered[1:]:
            merge_papers(conn, loser_id=loser, winner_id=winner, pdf_root=pdf_root)
            merges += 1
    return merges


def run_dedup(conn: sqlite3.Connection) -> dict:
    rows = [_row_for_key(r) for r in conn.execute("SELECT * FROM raw_records").fetchall()]
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(paper_id_from_key(compute_dedup_key(r)), []).append(r)
    papers_created = 0
    for paper_id, raws in groups.items():
        canon = build_canonical_paper(raws)
        if not canon["title"] or canon["year"] is None:
            canon["title"] = canon["title"] or "(untitled)"
            canon["year"] = canon["year"] or 0
        conn.execute(
            """INSERT INTO papers (paper_id, doi, title, authors_json, year, venue,
               abstract, language, first_seen_at, last_updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(paper_id) DO UPDATE SET
                 doi=excluded.doi, title=excluded.title, authors_json=excluded.authors_json,
                 year=excluded.year, venue=excluded.venue, abstract=excluded.abstract,
                 language=excluded.language, last_updated_at=excluded.last_updated_at""",
            (paper_id, canon["doi"], canon["title"], canon["authors_json"], canon["year"],
             canon["venue"], canon["abstract"], canon["language"], _now(), _now()),
        )
        for r in raws:
            conn.execute(
                "INSERT OR IGNORE INTO paper_sources (paper_id, raw_id) VALUES (?,?)",
                (paper_id, r["raw_id"]),
            )
        papers_created += 1
    return {"raw_records": len(rows), "papers_created": papers_created}
