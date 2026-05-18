"""Lift OA / peer-review flags from cached ERIC raw payloads. No network.

ERIC records carry two signals the rest of the pipeline can't otherwise
recover:

  1. The `peerreviewed` field (`T`/`F`) — ERIC's own peer-review attestation,
     used here to set `is_peer_reviewed=1` for `peerreviewed='T'` papers.

  2. ERIC's own full-text mirror at `https://files.eric.ed.gov/fulltext/<ID>.pdf`,
     reliably available for `ED`-prefix records (the ERIC document series:
     reports, dissertations, gray literature). For these we set `is_oa=1` and
     `oa_pdf_url` to that URL, which lets the screen's `not_oa` gate clear
     them and the export's PDF downloader pull them down.

EJ-prefix records (ERIC's journal-article index) are NOT given an
`oa_pdf_url` here. Many EJ items in ERIC are abstract-only entries pointing
to publisher-hosted versions, and the `files.eric.ed.gov` mirror is not
guaranteed to host them. We accept that EJ peer-review attestation alone
isn't enough to pass the `not_oa` gate; a future pass against Unpaywall by
the EJ record's known DOI (when ERIC's API begins exposing one) would close
that gap.

All updates use COALESCE, so values already supplied by the OpenAlex
enrichment (run earlier in the enrich pipeline) take precedence — ERIC's
synthetic flags only fill in what OpenAlex did not.
"""
from __future__ import annotations
import json
import sqlite3

ERIC_FULLTEXT_URL = "https://files.eric.ed.gov/fulltext/{}.pdf"


def _flags_from_payload(external_id: str, payload: dict) -> dict:
    """Return the flag updates derivable from a single ERIC payload."""
    out: dict[str, object | None] = {
        "is_oa": None,
        "oa_pdf_url": None,
        "is_peer_reviewed": None,
    }
    if payload.get("peerreviewed") == "T":
        out["is_peer_reviewed"] = 1
    if external_id.startswith("ED"):
        out["is_oa"] = 1
        out["oa_pdf_url"] = ERIC_FULLTEXT_URL.format(external_id)
    return out


def enrich_from_eric_payloads(conn: sqlite3.Connection) -> dict:
    """Walk every paper with an ERIC source; apply OA + peer-review flags.

    Idempotent. Uses COALESCE so existing non-NULL values (typically from
    `enrich_from_openalex_payloads`, which runs first) are preserved.
    """
    rows = conn.execute(
        """SELECT p.paper_id, rr.external_id, rr.raw_payload
           FROM papers p
           JOIN paper_sources ps ON ps.paper_id = p.paper_id
           JOIN raw_records   rr ON rr.raw_id   = ps.raw_id
           WHERE rr.adapter = 'eric'"""
    ).fetchall()
    counts = {"updated": 0, "is_oa_set": 0, "is_peer_reviewed_set": 0}
    for row in rows:
        try:
            payload = json.loads(row["raw_payload"])
        except Exception:
            continue
        f = _flags_from_payload(row["external_id"], payload)
        if not any(v is not None for v in f.values()):
            continue
        conn.execute(
            """UPDATE papers SET
                 is_oa            = COALESCE(is_oa, ?),
                 oa_pdf_url       = COALESCE(oa_pdf_url, ?),
                 is_peer_reviewed = COALESCE(is_peer_reviewed, ?),
                 last_updated_at  = datetime('now')
               WHERE paper_id = ?""",
            (f["is_oa"], f["oa_pdf_url"], f["is_peer_reviewed"], row["paper_id"]),
        )
        counts["updated"] += 1
        if f["is_oa"] == 1:
            counts["is_oa_set"] += 1
        if f["is_peer_reviewed"] == 1:
            counts["is_peer_reviewed_set"] += 1
    return counts
