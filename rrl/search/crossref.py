"""CrossRef on-demand DOI lookup for metadata gap-filling."""
from __future__ import annotations
import re

import requests

from rrl.search.base import RawRecord, normalize_doi

BASE = "https://api.crossref.org/works/"
_JATS = re.compile(r"<[^>]+>")

def _strip_jats(text: str | None) -> str | None:
    if text is None:
        return None
    return _JATS.sub("", text).strip() or None

def fetch_by_doi(session: requests.Session, doi: str, *, mailto: str) -> RawRecord | None:
    r = session.get(BASE + doi, params={"mailto": mailto})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    m = r.json().get("message", {})
    parts = (m.get("issued") or {}).get("date-parts") or [[None]]
    year = parts[0][0] if parts and parts[0] else None
    return RawRecord(
        external_id=m.get("DOI", doi),
        doi=normalize_doi(m.get("DOI")),
        title=(m.get("title") or [""])[0],
        authors=[{"family": a.get("family", ""), "given": a.get("given", ""),
                  "orcid": a.get("ORCID")} for a in (m.get("author") or [])],
        year=year,
        venue=(m.get("container-title") or [None])[0],
        abstract=_strip_jats(m.get("abstract")),
        language=m.get("language"),
        raw_payload=m,
    )
