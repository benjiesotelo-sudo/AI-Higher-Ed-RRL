"""Populate work_type/publisher/citation_count/is_in_doaj for the 5 dean
duplicates whose flags were left NULL because the ingest script's
duplicate path didn't enrich them.

One-shot, idempotent: re-fetches OpenAlex payload by DOI for each paper_id
and applies the same flag mapping the regular pipeline uses.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rrl.db import connect
from rrl.enrich.openalex_flags import _flags_from_payload
from rrl.enrich.doaj import lookup_issn as doaj_lookup
from scripts.ingest_dean_pdfs import load_env  # type: ignore

DB_PATH = ROOT / "data" / "rrl.sqlite"
DEAN_PAPER_IDS = [
    "03aa44aa607b0e73", "41f5b0c950550505", "8ab99685bf611427",
    "786b0581c04bbb7a", "281df417f101e592", "83fc40cc33332056",
]


def main() -> int:
    load_env(ROOT / ".env")
    email = os.environ["OPENALEX_EMAIL"]
    conn = connect(DB_PATH)
    session = requests.Session()
    session.headers.update({"User-Agent": f"rrl-dean-enrich ({email})"})

    for pid in DEAN_PAPER_IDS:
        row = conn.execute("SELECT doi FROM papers WHERE paper_id=?", (pid,)).fetchone()
        if not row or not row["doi"]:
            print(f"  {pid}: no DOI, skipping")
            continue
        doi = row["doi"]
        r = session.get(f"https://api.openalex.org/works/doi:{doi}", params={"mailto": email}, timeout=30)
        if r.status_code != 200:
            print(f"  {pid}: OpenAlex lookup HTTP {r.status_code}, skipping")
            continue
        payload = r.json()
        flags = _flags_from_payload(payload)
        # NOTE: don't overwrite is_oa/is_peer_reviewed (dean trust set these).
        conn.execute(
            """UPDATE papers SET
                 work_type=COALESCE(work_type, ?),
                 publisher=COALESCE(publisher, ?),
                 citation_count=COALESCE(citation_count, ?),
                 last_updated_at=datetime('now')
               WHERE paper_id=?""",
            (flags["work_type"], flags["publisher"], flags["citation_count"], pid),
        )
        src = (payload.get("primary_location") or {}).get("source") or {}
        issn = src.get("issn_l") or (src.get("issn") or [None])[0]
        if issn:
            try:
                is_in = doaj_lookup(session, issn)
            except Exception as e:
                is_in = None
                print(f"  {pid}: DOAJ lookup failed for {issn}: {e}")
            if is_in is not None:
                conn.execute(
                    """UPDATE papers SET is_in_doaj=?, doaj_checked_at=datetime('now'),
                       last_updated_at=datetime('now') WHERE paper_id=?""",
                    (1 if is_in else 0, pid),
                )
        print(f"  {pid}: work_type={flags['work_type']!r} publisher={flags['publisher']!r} "
              f"citations={flags['citation_count']} issn={issn}")
    conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
