"""Scopus Search API adapter — Elsevier-tier discovery source.

Auth via X-ELS-APIKey (institutional tier; ~9 req/s, 20k/week quota).
Cursor pagination, 25 results/page, view=COMPLETE for inline abstracts.
"""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord, normalize_doi

BASE = "https://api.elsevier.com/content/search/scopus"


def _author_dict(a: dict) -> dict:
    """Normalize a Scopus author entry into the project's author shape."""
    family = a.get("surname") or ""
    given = a.get("given-name") or ""
    if not family and not given:
        # Fall back to authname (e.g., "Smith J.") split into surname/initial.
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

    def _render_query(self, q: QuerySpec) -> str:
        """Build the Scopus search expression: AI block AND HE block AND year/lang/doctype filters."""
        ai = " OR ".join(f'"{t}"' for t in q.ai_terms)
        he = " OR ".join(f'"{t}"' for t in q.he_terms)
        # Scopus uses strict >, so to include year_min we need year_min - 1
        # and to include year_max we need year_max + 1.
        return (
            f"( TITLE-ABS-KEY({ai}) ) "
            f"AND ( TITLE-ABS-KEY({he}) ) "
            f"AND PUBYEAR > {q.year_min - 1} AND PUBYEAR < {q.year_max + 1} "
            f"AND LANGUAGE(english) "
            f"AND ( DOCTYPE(ar) OR DOCTYPE(cp) OR DOCTYPE(re) OR DOCTYPE(ch) )"
        )

    def _headers(self) -> dict:
        h = {"X-ELS-APIKey": self.api_key, "Accept": "application/json"}
        if self.inst_token:
            h["X-ELS-Insttoken"] = self.inst_token
        return h

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        cursor: str | None = "*"
        params = {
            "query": self._render_query(q),
            "count": 25,
        }
        while cursor is not None:
            params["cursor"] = cursor
            r = self.session.get(BASE, params=params, headers=self._headers())
            r.raise_for_status()
            results = r.json().get("search-results", {})
            for entry in (results.get("entry") or []):
                yield self._parse(entry)
            next_cursor = (results.get("cursor") or {}).get("@next")
            if not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

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
