"""Scopus Search API adapter — Elsevier-tier discovery source.

Auth via X-ELS-APIKey (institutional tier; ~9 req/s, 20k/week quota).
Pagination strategy: this tier disallows cursor pagination
(ENTITLEMENTS_ERROR) and caps offset pagination at start+count <= 5000.
To cover queries with >5000 matches, the adapter iterates per-year and
splits any year over 5000 into Jan-Jun / Jul-Dec halves via PUBDATETXT.
"""
from __future__ import annotations
import logging
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord, normalize_doi

log = logging.getLogger(__name__)

BASE = "https://api.elsevier.com/content/search/scopus"
OFFSET_CAP = 5000           # start + count must be <= this
PAGE_SIZE = 25

H1_MONTHS = ("January", "February", "March", "April", "May", "June")
H2_MONTHS = ("July", "August", "September", "October", "November", "December")


def _author_dict(a: dict) -> dict:
    """Normalize a Scopus author entry into the project's author shape."""
    family = a.get("surname") or ""
    given = a.get("given-name") or ""
    if not family and not given:
        name = (a.get("authname") or "").strip()
        if " " in name:
            family, given = name.rsplit(" ", 1)
        else:
            family = name
    return {"family": family.strip(), "given": given.strip(), "orcid": None}


def _year(cover_date: str | None) -> int | None:
    if not cover_date:
        return None
    try:
        return int(cover_date.split("-", 1)[0])
    except (ValueError, AttributeError):
        return None


class ScopusAdapter:
    name = "scopus"

    def __init__(self, session: requests.Session, api_key: str, inst_token: str | None = None):
        self.session = session
        self.api_key = api_key
        self.inst_token = inst_token

    def _topic_clauses(self, q: QuerySpec) -> str:
        """The AI×HE topic block, doctype, and language — same in every sub-query."""
        ai = " OR ".join(f'"{t}"' for t in q.ai_terms)
        he = " OR ".join(f'"{t}"' for t in q.he_terms)
        return (
            f"( TITLE-ABS-KEY({ai}) ) "
            f"AND ( TITLE-ABS-KEY({he}) ) "
            f"AND LANGUAGE(english) "
            f"AND ( DOCTYPE(ar) OR DOCTYPE(cp) OR DOCTYPE(re) OR DOCTYPE(ch) )"
        )

    def _render_query(self, q: QuerySpec) -> str:
        """Single combined query for the entire year range. Used by tests and
        kept for backward compatibility — the live search() method uses
        per-year sub-queries (see _year_query / _half_year_query)."""
        return (
            f"{self._topic_clauses(q)} "
            f"AND PUBYEAR > {q.year_min - 1} AND PUBYEAR < {q.year_max + 1}"
        )

    def _year_query(self, q: QuerySpec, year: int) -> str:
        return f"{self._topic_clauses(q)} AND PUBYEAR = {year}"

    def _half_year_query(self, q: QuerySpec, year: int, months: tuple[str, ...]) -> str:
        pubdate = " OR ".join(f'"{m} {year}"' for m in months)
        return f"{self._topic_clauses(q)} AND PUBDATETXT({pubdate})"

    def _headers(self) -> dict:
        h = {"X-ELS-APIKey": self.api_key, "Accept": "application/json"}
        if self.inst_token:
            h["X-ELS-Insttoken"] = self.inst_token
        return h

    def _probe_count(self, query: str) -> int:
        """One request with count=1 to discover the total for a sub-query."""
        r = self.session.get(
            BASE,
            params={"query": query, "count": 1},
            headers=self._headers(),
        )
        r.raise_for_status()
        results = r.json().get("search-results", {})
        try:
            return int(results.get("opensearch:totalResults", "0"))
        except (TypeError, ValueError):
            return 0

    def _paginate(self, query: str) -> Iterator[RawRecord]:
        """Offset-pagination loop. Stops at the 5000-result cap with a warning
        if it would be exceeded."""
        start = 0
        while start + PAGE_SIZE <= OFFSET_CAP:
            r = self.session.get(
                BASE,
                params={"query": query, "count": PAGE_SIZE, "start": start},
                headers=self._headers(),
            )
            r.raise_for_status()
            results = r.json().get("search-results", {})
            entries = results.get("entry") or []
            if not entries:
                return
            for entry in entries:
                yield self._parse(entry)
            try:
                total = int(results.get("opensearch:totalResults", "0"))
            except (TypeError, ValueError):
                total = 0
            start += PAGE_SIZE
            if start >= total:
                return
        # Hit the cap. Anything beyond is lost; log so it shows up in the run.
        log.warning(
            "scopus bucket hit offset cap (start=%d) — query may be truncated: %s",
            start, query[:120],
        )

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        """Iterate per-year. Years over the 5000-result cap split into H1/H2
        via PUBDATETXT. Empty years are skipped (no requests beyond the probe)."""
        for year in range(q.year_min, q.year_max + 1):
            year_q = self._year_query(q, year)
            total = self._probe_count(year_q)
            log.info("scopus: year=%d total=%d", year, total)
            if total == 0:
                continue
            if total <= OFFSET_CAP:
                yield from self._paginate(year_q)
                continue
            # Year too large — split into halves and paginate each.
            for label, months in (("H1", H1_MONTHS), ("H2", H2_MONTHS)):
                half_q = self._half_year_query(q, year, months)
                half_total = self._probe_count(half_q)
                log.info("scopus: year=%d half=%s total=%d", year, label, half_total)
                yield from self._paginate(half_q)

    def _parse(self, entry: dict) -> RawRecord:
        cover_date = entry.get("prism:coverDate")
        return RawRecord(
            external_id=entry["dc:identifier"],
            doi=normalize_doi(entry.get("prism:doi")),
            title=entry.get("dc:title") or "",
            authors=[_author_dict(a) for a in (entry.get("author") or [])],
            year=_year(cover_date),
            venue=entry.get("prism:publicationName"),
            abstract=entry.get("dc:description"),
            language="en" if (entry.get("language") or "").lower().startswith("eng") else entry.get("language"),
            raw_payload=entry,
        )
