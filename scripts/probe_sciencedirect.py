"""ScienceDirect TDM smoke test — single Elsevier DOI, no DB writes.

Determines whether ELSEVIER_API_KEY has TDM (full-text) access. Used once
at the start of Phase 3 of the rescrape plan to pick branch A (fallback
in place) vs branch B (Scopus metadata only).

Usage:
    python scripts/probe_sciencedirect.py [DOI]

Without DOI argument, uses a known Elsevier OA paper as the probe target.
Exits 0 on success (PDF retrieved), 1 on any failure mode.
"""
from __future__ import annotations
import os
import sys

import requests
from dotenv import load_dotenv


DEFAULT_DOI = "10.1016/j.caeai.2023.100132"  # known Elsevier OA paper
PDF_MAGIC = b"%PDF-"
MIN_PDF_BYTES = 10 * 1024


def main(doi: str) -> int:
    load_dotenv()
    key = os.environ.get("ELSEVIER_API_KEY", "").strip()
    if not key:
        print("FAIL: ELSEVIER_API_KEY is not set in environment or .env", file=sys.stderr)
        return 1
    inst_token = os.environ.get("ELSEVIER_INSTTOKEN", "").strip() or None

    url = f"https://api.elsevier.com/content/article/doi/{doi}"
    headers = {"X-ELS-APIKey": key, "Accept": "application/pdf"}
    if inst_token:
        headers["X-ELS-Insttoken"] = inst_token

    try:
        r = requests.get(url, headers=headers, timeout=30)
    except Exception as e:
        print(f"FAIL: request error: {e}", file=sys.stderr)
        return 1

    ctype = r.headers.get("Content-Type", "")
    has_magic = r.content.startswith(PDF_MAGIC)
    big_enough = len(r.content) >= MIN_PDF_BYTES

    print(
        f"DOI:          {doi}\n"
        f"HTTP status:  {r.status_code}\n"
        f"Content-Type: {ctype}\n"
        f"Bytes:        {len(r.content)}\n"
        f"PDF magic:    {'yes' if has_magic else 'no'}\n"
        f"Size >= 10KB: {'yes' if big_enough else 'no'}"
    )

    if r.status_code == 200 and has_magic and big_enough:
        print("\nRESULT: TDM access confirmed — proceed with branch A (ScienceDirect fallback in download_pdfs).")
        return 0

    if r.status_code in (401, 403):
        print(
            "\nRESULT: TDM access denied (auth error).",
            "Proceed with branch B (Scopus metadata only; no ScienceDirect fallback).",
            sep=" ",
        )
        return 1

    if r.status_code == 200 and not has_magic:
        snippet = r.text[:300] if not r.content.startswith(b"\x00") else "<binary>"
        print(f"\nRESULT: 200 response but not a PDF. First 300 chars:\n{snippet}")
        print("Proceed with branch B (the API responded but TDM PDF not delivered).")
        return 1

    print(f"\nRESULT: unexpected response. Investigate before deciding branch.")
    return 1


if __name__ == "__main__":
    doi = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DOI
    sys.exit(main(doi))
