"""Ingest hand-supplied supplementary PDFs into the corpus (PRISMA 2020 "other sources").

For each PDF in pdfs/supplementary/:
  1. Extract first-2-pages text via pypdf; pull DOI/title heuristically.
  2. Query OpenAlex (DOI if present, else title search) for canonical metadata.
  3. Compute dedup_key the same way `rrl dedup` does.
  4. If the resulting paper_id already exists → log duplicate, link the
     supplementary raw_record to it. If new → insert paper + run flag
     enrichment + screen.
  5. Move PDF to pdfs/<year>/<paper_id>.pdf and mark pdf_status='downloaded'.

Run from project root:  python scripts/ingest_supplementary_pdfs.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import requests
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rrl.db import connect, init_schema
from rrl.search.base import normalize_doi, normalize_title, normalize_author_name
from rrl.dedup.grouping import compute_dedup_key, paper_id_from_key
from rrl.enrich.openalex_flags import _flags_from_payload
from rrl.enrich.unpaywall import lookup_doi as unpaywall_lookup
from rrl.enrich.doaj import lookup_issn as doaj_lookup
from rrl.screen.rules import evaluate_paper

PDF_SRC = ROOT / "pdfs" / "supplementary"
PDF_ROOT = ROOT / "pdfs"
DB_PATH = ROOT / "data" / "rrl.sqlite"

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+", re.IGNORECASE)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_env(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip().strip('"').strip("'")
        if v and v != "your-email@example.com":
            os.environ[k.strip()] = v


def extract_pdf_metadata(path: Path) -> dict:
    """Read first 2 pages, return {text, doi_guess, title_guess}."""
    reader = PdfReader(str(path))
    n_pages = min(2, len(reader.pages))
    text = ""
    for i in range(n_pages):
        try:
            text += reader.pages[i].extract_text() or ""
        except Exception:
            pass
    pdf_meta = reader.metadata or {}
    title_guess = (pdf_meta.get("/Title") or "").strip() or None
    doi_match = DOI_RE.search(text)
    doi_guess = doi_match.group(0).rstrip(".,;)") if doi_match else None
    return {"text": text, "doi_guess": normalize_doi(doi_guess), "title_guess": title_guess, "n_pages_pdf": len(reader.pages)}


def openalex_get_by_doi(session: requests.Session, doi: str, email: str) -> dict | None:
    r = session.get(f"https://api.openalex.org/works/doi:{doi}", params={"mailto": email}, timeout=30)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def openalex_search_by_title(session: requests.Session, title: str, email: str) -> dict | None:
    if not title:
        return None
    r = session.get(
        "https://api.openalex.org/works",
        params={"search": title[:300], "per-page": 5, "mailto": email},
        timeout=30,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    if not results:
        return None
    norm_target = normalize_title(title)
    if not norm_target:
        return results[0]
    best = None
    best_overlap = 0
    target_tokens = set(norm_target.split())
    for w in results:
        ot = normalize_title(w.get("title") or "")
        overlap = len(target_tokens & set(ot.split()))
        if overlap > best_overlap:
            best_overlap = overlap
            best = w
    if best and best_overlap >= max(3, len(target_tokens) // 2):
        return best
    return results[0]  # fall back


def openalex_id_from_payload(payload: dict) -> str | None:
    pid = payload.get("id") if isinstance(payload, dict) else None
    if isinstance(pid, str) and "openalex.org/" in pid:
        return pid.rsplit("/", 1)[-1]
    return None


def decode_inverted_abstract(inv: dict | None) -> str | None:
    if not inv:
        return None
    pos = []
    for w, ixs in inv.items():
        for i in ixs:
            pos.append((i, w))
    pos.sort()
    return " ".join(w for _, w in pos) or None


def derive_filename_metadata(filename: str) -> dict:
    """Fallback parse of 'Author 2026 Title.pdf' style names."""
    stem = filename.rsplit(".", 1)[0]
    m = re.match(r"^(.*?)\s+(\d{4})\s+(.*)$", stem)
    if not m:
        return {"first_author": None, "year": None, "title": stem}
    return {"first_author": m.group(1).strip(), "year": int(m.group(2)), "title": m.group(3).strip()}


def build_raw_record_payload(pdf_path: Path, pdf_meta: dict, oa_payload: dict | None) -> dict:
    """Construct a raw_payload dict + flattened fields for raw_records insert."""
    if oa_payload:
        title = oa_payload.get("title") or ""
        doi = normalize_doi(oa_payload.get("doi"))
        year = oa_payload.get("publication_year")
        primary = oa_payload.get("primary_location") or {}
        source_obj = primary.get("source") or {}
        venue = source_obj.get("display_name")
        abstract = decode_inverted_abstract(oa_payload.get("abstract_inverted_index"))
        language = oa_payload.get("language")
        authors_payload = oa_payload.get("authorships") or []
        authors = []
        for a in authors_payload:
            au = a.get("author") or {}
            name = a.get("raw_author_name") or au.get("display_name") or ""
            parts = name.rsplit(" ", 1)
            if len(parts) == 2:
                given, family = parts
            else:
                given, family = "", name
            authors.append({"family": family, "given": given, "orcid": au.get("orcid")})
        first_author = normalize_author_name(authors[0]["family"]) if authors else None
        return {
            "doi": doi,
            "title": title,
            "title_norm": normalize_title(title),
            "year": year,
            "venue": venue,
            "abstract": abstract,
            "language": language,
            "authors_json": json.dumps(authors),
            "first_author": first_author,
            "raw_payload": oa_payload,
            "external_id": oa_payload["id"].rsplit("/", 1)[-1],
        }
    fb = derive_filename_metadata(pdf_path.name)
    return {
        "doi": pdf_meta.get("doi_guess"),
        "title": pdf_meta.get("title_guess") or fb["title"],
        "title_norm": normalize_title(pdf_meta.get("title_guess") or fb["title"]),
        "year": fb["year"],
        "venue": None,
        "abstract": None,
        "language": "en",
        "authors_json": json.dumps([{"family": fb["first_author"] or "", "given": "", "orcid": None}]) if fb["first_author"] else "[]",
        "first_author": normalize_author_name(fb["first_author"]) if fb["first_author"] else None,
        "raw_payload": {"source": "pypdf_only", "filename": pdf_path.name, "pdf_meta": pdf_meta.get("title_guess"), "doi_guess": pdf_meta.get("doi_guess")},
        "external_id": f"supplementary_{pdf_path.stem}",
    }


def ensure_search_run(conn: sqlite3.Connection) -> str:
    """Create a single search_runs row for this batch; reuse if already exists."""
    row = conn.execute(
        "SELECT run_id FROM search_runs WHERE adapter='supplementary_search' ORDER BY started_at DESC LIMIT 1"
    ).fetchone()
    if row:
        return row["run_id"]
    run_id = f"supplementary-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}-{uuid.uuid4().hex[:6]}"
    conn.execute(
        """INSERT INTO search_runs (run_id, adapter, query_hash, query_payload,
           started_at, finished_at, status, records_found, records_new)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (run_id, "supplementary_search", "n/a",
         json.dumps({"source": "supplementary_search", "batch": "2026-05-18"}),
         now(), now(), "ok", 0, 0),
    )
    return run_id


def insert_raw_record(conn: sqlite3.Connection, run_id: str, rec: dict) -> int:
    conn.execute(
        """INSERT OR IGNORE INTO raw_records (run_id, adapter, external_id, doi,
           title, title_norm, authors_json, first_author, year, venue, abstract,
           language, raw_payload, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, "supplementary_search", rec["external_id"], rec["doi"], rec["title"],
         rec["title_norm"], rec["authors_json"], rec["first_author"], rec["year"],
         rec["venue"], rec["abstract"], rec["language"],
         json.dumps(rec["raw_payload"]), now()),
    )
    row = conn.execute(
        "SELECT raw_id FROM raw_records WHERE adapter='supplementary_search' AND external_id=?",
        (rec["external_id"],),
    ).fetchone()
    return row["raw_id"]


def find_existing_paper_id(conn: sqlite3.Connection, rec: dict, oa_payload: dict | None) -> str | None:
    """Apply the dedup cascade against existing papers."""
    if rec["doi"]:
        row = conn.execute("SELECT paper_id FROM papers WHERE doi=?", (rec["doi"],)).fetchone()
        if row:
            return row["paper_id"]
    oa_id = openalex_id_from_payload(oa_payload) if oa_payload else None
    if oa_id:
        row = conn.execute(
            """SELECT DISTINCT p.paper_id FROM papers p
               JOIN paper_sources ps ON ps.paper_id = p.paper_id
               JOIN raw_records rr ON rr.raw_id = ps.raw_id
               WHERE rr.adapter='openalex' AND json_extract(rr.raw_payload, '$.id')
                     LIKE ?""",
            (f"%/{oa_id}",),
        ).fetchone()
        if row:
            return row["paper_id"]
    # signature key
    key_input = {
        "raw_id": -1,
        "doi": rec["doi"],
        "openalex_id": oa_id,
        "title_norm": rec["title_norm"],
        "year": rec["year"],
        "first_author": rec["first_author"],
    }
    candidate_pid = paper_id_from_key(compute_dedup_key(key_input))
    row = conn.execute("SELECT paper_id FROM papers WHERE paper_id=?", (candidate_pid,)).fetchone()
    if row:
        return row["paper_id"]
    return None


def insert_new_paper(conn: sqlite3.Connection, rec: dict, oa_payload: dict | None) -> str:
    oa_id = openalex_id_from_payload(oa_payload) if oa_payload else None
    key_input = {
        "raw_id": -1,
        "doi": rec["doi"],
        "openalex_id": oa_id,
        "title_norm": rec["title_norm"],
        "year": rec["year"],
        "first_author": rec["first_author"],
    }
    paper_id = paper_id_from_key(compute_dedup_key(key_input))
    conn.execute(
        """INSERT INTO papers (paper_id, doi, title, authors_json, year, venue,
           abstract, language, first_seen_at, last_updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(paper_id) DO NOTHING""",
        (paper_id, rec["doi"], rec["title"] or "(untitled)", rec["authors_json"],
         rec["year"] or 0, rec["venue"], rec["abstract"], rec["language"], now(), now()),
    )
    return paper_id


def link_paper_source(conn: sqlite3.Connection, paper_id: str, raw_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO paper_sources (paper_id, raw_id) VALUES (?,?)",
        (paper_id, raw_id),
    )


def apply_openalex_flags(conn: sqlite3.Connection, paper_id: str, oa_payload: dict) -> None:
    f = _flags_from_payload(oa_payload)
    conn.execute(
        """UPDATE papers SET
             is_oa=COALESCE(is_oa, ?),
             oa_status=COALESCE(oa_status, ?),
             oa_pdf_url=COALESCE(oa_pdf_url, ?),
             work_type=COALESCE(work_type, ?),
             publisher=COALESCE(publisher, ?),
             citation_count=COALESCE(citation_count, ?),
             is_peer_reviewed=COALESCE(is_peer_reviewed, ?),
             last_updated_at=datetime('now')
           WHERE paper_id=?""",
        (f["is_oa"], f["oa_status"], f["oa_pdf_url"], f["work_type"], f["publisher"],
         f["citation_count"], f["is_peer_reviewed"], paper_id),
    )


def run_doaj_for_paper(conn: sqlite3.Connection, session: requests.Session, paper_id: str, oa_payload: dict | None) -> None:
    issn = None
    if oa_payload:
        src = (oa_payload.get("primary_location") or {}).get("source") or {}
        issn = src.get("issn_l") or (src.get("issn") or [None])[0]
    if not issn:
        conn.execute("UPDATE papers SET doaj_checked_at=datetime('now') WHERE paper_id=?", (paper_id,))
        return
    try:
        is_in = doaj_lookup(session, issn)
    except Exception as e:
        conn.execute("UPDATE papers SET doaj_checked_at=datetime('now') WHERE paper_id=?", (paper_id,))
        return
    conn.execute(
        """UPDATE papers SET is_in_doaj=?, doaj_checked_at=datetime('now'),
           last_updated_at=datetime('now') WHERE paper_id=?""",
        (1 if is_in else 0, paper_id),
    )


def run_unpaywall_for_paper(conn: sqlite3.Connection, session: requests.Session, paper_id: str, doi: str | None, email: str) -> None:
    if not doi:
        conn.execute("UPDATE papers SET unpaywall_checked_at=datetime('now') WHERE paper_id=?", (paper_id,))
        return
    try:
        pdf, status = unpaywall_lookup(session, doi, email)
    except Exception:
        conn.execute("UPDATE papers SET unpaywall_checked_at=datetime('now') WHERE paper_id=?", (paper_id,))
        return
    if pdf:
        conn.execute(
            """UPDATE papers SET oa_pdf_url=?, oa_status=COALESCE(?, oa_status),
               is_oa=1, unpaywall_checked_at=datetime('now'),
               last_updated_at=datetime('now') WHERE paper_id=?""",
            (pdf, status, paper_id),
        )
    else:
        conn.execute(
            """UPDATE papers SET unpaywall_checked_at=datetime('now'),
               last_updated_at=datetime('now') WHERE paper_id=?""",
            (paper_id,),
        )


def screen_paper(conn: sqlite3.Connection, paper_id: str) -> dict:
    row = conn.execute(
        """SELECT paper_id, title, abstract, venue, year, language, is_oa, oa_pdf_url,
                  is_peer_reviewed, is_in_doaj, work_type, publisher
           FROM papers WHERE paper_id=?""",
        (paper_id,),
    ).fetchone()
    paper = {k: row[k] for k in row.keys()}
    # Supplementary PDFs: we *have* the PDF locally, so OA status is moot for
    # accessibility. Force is_oa=1 / oa_pdf_url='local' so the screen's not_oa
    # gate doesn't reject papers we already possess.
    paper["is_oa"] = 1
    paper["oa_pdf_url"] = paper.get("oa_pdf_url") or "local"
    decision = evaluate_paper(paper)
    conn.execute(
        """UPDATE papers SET included=?, exclusion_reason=?, quality_tier=?,
           era_tag=?, topic_match_score=?, is_oa=COALESCE(is_oa, 1),
           oa_pdf_url=COALESCE(oa_pdf_url, 'local'),
           last_updated_at=datetime('now') WHERE paper_id=?""",
        (decision.get("included"), decision.get("exclusion_reason"),
         decision.get("quality_tier"), decision.get("era_tag"),
         decision.get("topic_match_score"), paper_id),
    )
    return decision


def move_pdf(pdf_path: Path, paper_id: str, year: int) -> Path:
    year_dir = PDF_ROOT / str(year or "unknown")
    year_dir.mkdir(parents=True, exist_ok=True)
    dest = year_dir / f"{paper_id}.pdf"
    if dest.exists():
        # Existing copy from a prior pipeline run — prefer the supplementary
        # version so the supplementary folder ends up empty after ingest.
        dest.unlink()
    shutil.move(str(pdf_path), str(dest))
    return dest


def main() -> int:
    load_env(ROOT / ".env")
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    if not email or email == "your-email@example.com":
        print("ERROR: OPENALEX_EMAIL not set", file=sys.stderr)
        return 2

    if not PDF_SRC.exists():
        print(f"ERROR: {PDF_SRC} does not exist", file=sys.stderr)
        return 2

    pdfs = sorted(PDF_SRC.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDF(s) in {PDF_SRC.relative_to(ROOT)}")
    for p in pdfs:
        print(f"  - {p.name}")

    conn = connect(DB_PATH)
    init_schema(conn)
    session = requests.Session()
    session.headers.update({"User-Agent": f"rrl-supplementary-ingest ({email})"})

    run_id = ensure_search_run(conn)
    print(f"\nUsing search_run: {run_id}\n")

    results = []
    for p in pdfs:
        print(f"=== {p.name} ===")
        pdf_meta = extract_pdf_metadata(p)
        print(f"  DOI in PDF text: {pdf_meta['doi_guess']!r}")
        print(f"  /Title in PDF metadata: {(pdf_meta['title_guess'] or '')[:80]!r}")

        oa_payload = None
        if pdf_meta["doi_guess"]:
            oa_payload = openalex_get_by_doi(session, pdf_meta["doi_guess"], email)
            print(f"  OpenAlex DOI lookup: {'hit' if oa_payload else 'miss'}")
        if oa_payload is None:
            # Try filename-based title first (cleaner than PDF /Title)
            fb = derive_filename_metadata(p.name)
            search_title = (pdf_meta["title_guess"] or fb["title"]).strip()
            oa_payload = openalex_search_by_title(session, search_title, email)
            print(f"  OpenAlex title search: {'hit' if oa_payload else 'miss'} (title={search_title[:60]!r})")

        rec = build_raw_record_payload(p, pdf_meta, oa_payload)
        print(f"  Resolved: doi={rec['doi']!r} year={rec['year']} title={rec['title'][:60]!r}")

        existing_pid = find_existing_paper_id(conn, rec, oa_payload)
        if existing_pid:
            # Existing — just link the supplementary source.
            raw_id = insert_raw_record(conn, run_id, rec)
            link_paper_source(conn, existing_pid, raw_id)
            existing = conn.execute(
                "SELECT title, year, included, exclusion_reason, quality_tier, pdf_filename FROM papers WHERE paper_id=?",
                (existing_pid,),
            ).fetchone()
            print(f"  → DUPLICATE of existing paper {existing_pid}: {existing['title'][:60]!r} ({existing['year']})")
            print(f"     existing screen: included={existing['included']} reason={existing['exclusion_reason']} tier={existing['quality_tier']} pdf={existing['pdf_filename']!r}")
            # Adopt the supplementary local copy unconditionally — it is the
            # only PDF on hand for these S2-only papers that the original
            # pipeline could not download.
            yr = existing["year"] or rec["year"] or 0
            dest = move_pdf(p, existing_pid, yr)
            rel = str(dest.relative_to(PDF_ROOT))
            conn.execute(
                "UPDATE papers SET pdf_filename=?, pdf_status='downloaded', last_updated_at=datetime('now') WHERE paper_id=?",
                (rel, existing_pid),
            )
            print(f"     supplementary PDF → {rel} (overwrote any prior copy)")
            results.append({"pdf": p.name, "outcome": "duplicate", "paper_id": existing_pid,
                            "existing_included": existing["included"], "existing_reason": existing["exclusion_reason"]})
            continue

        # New paper
        paper_id = insert_new_paper(conn, rec, oa_payload)
        raw_id = insert_raw_record(conn, run_id, rec)
        link_paper_source(conn, paper_id, raw_id)
        if oa_payload:
            apply_openalex_flags(conn, paper_id, oa_payload)
        # Enrich
        run_doaj_for_paper(conn, session, paper_id, oa_payload)
        run_unpaywall_for_paper(conn, session, paper_id, rec["doi"], email)
        # Screen
        decision = screen_paper(conn, paper_id)
        # Move PDF
        yr = rec["year"] or 0
        dest = move_pdf(p, paper_id, yr)
        rel = str(dest.relative_to(PDF_ROOT))
        conn.execute(
            "UPDATE papers SET pdf_filename=?, pdf_status='downloaded', last_updated_at=datetime('now') WHERE paper_id=?",
            (rel, paper_id),
        )
        print(f"  → NEW paper {paper_id}: included={decision.get('included')} reason={decision.get('exclusion_reason')} tier={decision.get('quality_tier')}")
        print(f"     PDF → {rel}")
        results.append({
            "pdf": p.name, "outcome": "new", "paper_id": paper_id,
            "included": decision.get("included"),
            "exclusion_reason": decision.get("exclusion_reason"),
            "tier": decision.get("quality_tier"),
            "year": rec["year"], "doi": rec["doi"],
        })

    conn.commit()
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for r in results:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
