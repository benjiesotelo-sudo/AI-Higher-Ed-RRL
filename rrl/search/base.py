"""Shared types and normalization helpers for search adapters."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator, Protocol

STOPWORDS = {"the", "a", "an", "of", "for", "and", "to", "in", "on", "with"}

@dataclass(frozen=True)
class QuerySpec:
    ai_terms: list[str]
    he_terms: list[str]
    year_min: int
    year_max: int
    language: str = "en"

@dataclass(frozen=True)
class RawRecord:
    external_id: str
    doi: str | None
    title: str
    authors: list[dict]
    year: int | None
    venue: str | None
    abstract: str | None
    language: str | None
    raw_payload: dict = field(default_factory=dict)

class SearchAdapter(Protocol):
    name: str
    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]: ...

_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = _DOI_PREFIX.sub("", doi.strip()).lower().rstrip(".,;")
    return d or None

def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    t = _strip_diacritics(title).lower()
    t = _NON_ALNUM.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return " ".join(w for w in t.split() if w not in STOPWORDS)

def normalize_author_name(name: str | None) -> str:
    if not name:
        return ""
    n = _strip_diacritics(name).lower()
    n = re.sub(r"[^a-z]+", "", n)
    return n

def query_hash(q: QuerySpec) -> str:
    payload = json.dumps({
        "ai_terms": sorted(q.ai_terms),
        "he_terms": sorted(q.he_terms),
        "year_min": q.year_min,
        "year_max": q.year_max,
        "language": q.language,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
