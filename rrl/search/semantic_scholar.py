"""Semantic Scholar bulk search adapter."""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord, normalize_doi

BASE = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = "paperId,externalIds,title,year,abstract,venue,authors,citationCount"

def _author_dict(a: dict) -> dict:
    name = a.get("name") or ""
    parts = name.rsplit(" ", 1)
    given, family = (parts[0], parts[1]) if len(parts) == 2 else ("", name)
    return {"family": family, "given": given, "orcid": None}

class SemanticScholarAdapter:
    name = "s2"

    def __init__(self, session: requests.Session, api_key: str | None):
        self.session = session
        self.api_key = api_key

    def _render_query(self, q: QuerySpec) -> str:
        # S2 bulk search: space-separated tokens are AND, `|` is OR. The
        # literal word "OR" is matched as a search term, not an operator.
        ai = " | ".join(f'"{t}"' for t in q.ai_terms)
        he = " | ".join(f'"{t}"' for t in q.he_terms)
        return f"({ai}) + ({he})"

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        params = {
            "query": self._render_query(q),
            "year": f"{q.year_min}-{q.year_max}",
            "fieldsOfStudy": "Education,Computer Science",
            "fields": FIELDS,
        }
        token: str | None = None
        while True:
            if token:
                params["token"] = token
            r = self.session.get(BASE, params=params, headers=headers)
            r.raise_for_status()
            payload = r.json()
            for w in payload.get("data", []):
                yield self._parse(w)
            token = payload.get("token")
            if not token:
                return

    def _parse(self, w: dict) -> RawRecord:
        ids = w.get("externalIds") or {}
        return RawRecord(
            external_id=w["paperId"],
            doi=normalize_doi(ids.get("DOI")),
            title=w.get("title") or "",
            authors=[_author_dict(a) for a in (w.get("authors") or [])],
            year=w.get("year"),
            venue=w.get("venue"),
            abstract=w.get("abstract"),
            language=None,
            raw_payload=w,
        )
