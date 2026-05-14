"""CORE on-demand search for OA PDFs when Unpaywall and OpenAlex links fail."""
from __future__ import annotations
import requests

BASE = "https://api.core.ac.uk/v3/search/works"

def _first_pdf(payload: dict) -> str | None:
    for item in payload.get("results", []):
        url = item.get("downloadUrl")
        if url:
            return url
    return None

def find_pdf_by_doi(session: requests.Session, doi: str, *, api_key: str) -> str | None:
    r = session.get(BASE, params={"q": f"doi:{doi}", "limit": 1},
                    headers={"Authorization": f"Bearer {api_key}"})
    r.raise_for_status()
    return _first_pdf(r.json())

def find_pdf_by_title(session: requests.Session, title: str, *, api_key: str) -> str | None:
    r = session.get(BASE, params={"q": f"title:\"{title}\"", "limit": 1},
                    headers={"Authorization": f"Bearer {api_key}"})
    r.raise_for_status()
    return _first_pdf(r.json())
