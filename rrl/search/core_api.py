"""CORE on-demand search for OA PDFs when Unpaywall and OpenAlex links fail.

CORE rate-limits aggressively (10 req/min on the free tier). Any non-2xx
response — most commonly 429 (Too Many Requests) but also 5xx during outages
— is treated as a soft miss and returns None, so the export run does NOT
crash mid-pipeline. The pdf.py orchestrator is responsible for spacing
calls and enforcing a budget; the helpers here just don't raise.
"""
from __future__ import annotations
import logging

import requests

BASE = "https://api.core.ac.uk/v3/search/works"

log = logging.getLogger(__name__)


def _first_pdf(payload: dict) -> str | None:
    for item in payload.get("results", []):
        url = item.get("downloadUrl")
        if url:
            return url
    return None


def _safe_get(session: requests.Session, *, params: dict, api_key: str) -> str | None:
    try:
        r = session.get(BASE, params=params,
                        headers={"Authorization": f"Bearer {api_key}"},
                        timeout=30)
    except requests.RequestException as e:
        log.info("core_api request failed: %s", e)
        return None
    if r.status_code != 200:
        log.info("core_api non-200 (%s) for %s", r.status_code, params)
        return None
    try:
        return _first_pdf(r.json())
    except ValueError:
        return None


def find_pdf_by_doi(session: requests.Session, doi: str, *, api_key: str) -> str | None:
    return _safe_get(session, params={"q": f"doi:{doi}", "limit": 1}, api_key=api_key)


def find_pdf_by_title(session: requests.Session, title: str, *, api_key: str) -> str | None:
    return _safe_get(session, params={"q": f"title:\"{title}\"", "limit": 1}, api_key=api_key)
