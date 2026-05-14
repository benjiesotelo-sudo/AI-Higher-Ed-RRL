"""Dedup cascade: DOI > OpenAlex ID > signature key > singleton."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

from rrl.search.base import normalize_doi

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
