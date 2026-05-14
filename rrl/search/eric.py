"""ERIC adapter — education-focused, catches gray lit OpenAlex misses."""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord

BASE = "https://api.ies.ed.gov/eric/"
ROWS = 2000

def _parse_author(s: str) -> dict:
    if "," in s:
        family, given = s.split(",", 1)
        return {"family": family.strip(), "given": given.strip(), "orcid": None}
    return {"family": s.strip(), "given": "", "orcid": None}

class ERICAdapter:
    name = "eric"

    def __init__(self, session: requests.Session):
        self.session = session

    def _render_q(self, q: QuerySpec) -> str:
        # ERIC's default search field can't run phrase queries (no positions
        # indexed), so multi-word quoted terms like "artificial intelligence"
        # cause Solr errors. Restrict to single-token terms — the recall loss
        # is small because the distinctive tokens (ChatGPT, GenAI, LLM, etc.)
        # already match most relevant records.
        ai_terms = [t for t in q.ai_terms if " " not in t]
        he_terms = [t for t in q.he_terms if " " not in t]
        ai = " OR ".join(ai_terms)
        he = " OR ".join(he_terms)
        return (
            f"({ai}) "
            f"AND ({he}) "
            f"AND publicationdateyear:[{q.year_min} TO {q.year_max}]"
        )

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        # ERIC's public API uses `search=` (not `q=`).
        start = 0
        params_base = {"search": self._render_q(q), "rows": ROWS, "format": "json"}
        while True:
            params = dict(params_base, start=start)
            r = self.session.get(BASE, params=params)
            r.raise_for_status()
            docs = r.json().get("response", {}).get("docs", [])
            if not docs:
                return
            for d in docs:
                yield self._parse(d)
            if len(docs) < ROWS:
                return
            start += ROWS

    def _parse(self, d: dict) -> RawRecord:
        title_list = d.get("title") or [""]
        desc_list = d.get("description") or []
        return RawRecord(
            external_id=d["id"],
            doi=None,
            title=title_list[0] if title_list else "",
            authors=[_parse_author(a) for a in (d.get("author") or [])],
            year=d.get("publicationdateyear"),
            venue=(d.get("publisher") or [None])[0],
            abstract=desc_list[0] if desc_list else None,
            language="en" if (d.get("language") or ["English"])[0].lower().startswith("eng") else None,
            raw_payload=d,
        )
