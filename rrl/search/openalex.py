"""OpenAlex adapter — primary search source."""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord, normalize_doi

BASE = "https://api.openalex.org/works"
WORK_TYPES = ("journal-article", "book-chapter", "proceedings-article", "review")

def _decode_abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, ixs in inverted.items():
        for i in ixs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions) or None

def _author_dict(authorship: dict) -> dict:
    name = authorship.get("raw_author_name") or authorship.get("author", {}).get("display_name") or ""
    parts = name.rsplit(" ", 1)
    if len(parts) == 2:
        given, family = parts
    else:
        given, family = "", name
    return {"family": family, "given": given, "orcid": authorship.get("author", {}).get("orcid")}

class OpenAlexAdapter:
    name = "openalex"

    def __init__(self, session: requests.Session, email: str):
        self.session = session
        self.email = email

    def _render_filter(self, q: QuerySpec) -> str:
        ai = "|".join(q.ai_terms)
        he = "|".join(q.he_terms)
        parts = [
            f"abstract.search:{ai}",
            f"abstract.search:{he}",
            f"from_publication_date:{q.year_min}-01-01",
            f"to_publication_date:{q.year_max}-12-31",
            f"language:{q.language}",
            "type:" + "|".join(WORK_TYPES),
        ]
        return ",".join(parts)

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        cursor: str | None = "*"
        params = {
            "filter": self._render_filter(q),
            "per-page": 200,
            "mailto": self.email,
        }
        while cursor:
            params["cursor"] = cursor
            r = self.session.get(BASE, params=params)
            r.raise_for_status()
            payload = r.json()
            for w in payload.get("results", []):
                yield self._parse(w)
            cursor = payload.get("meta", {}).get("next_cursor")

    def _parse(self, w: dict) -> RawRecord:
        ext_id = w["id"].rsplit("/", 1)[-1]
        return RawRecord(
            external_id=ext_id,
            doi=normalize_doi(w.get("doi")),
            title=w.get("title") or "",
            authors=[_author_dict(a) for a in w.get("authorships", [])],
            year=w.get("publication_year"),
            venue=(w.get("primary_location") or {}).get("source", {}).get("display_name"),
            abstract=_decode_abstract(w.get("abstract_inverted_index")),
            language=w.get("language"),
            raw_payload=w,
        )
