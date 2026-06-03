"""Abstract-backfill yield pilot — measure how many `no_abstract` exclusions
are recoverable, with NO DB writes.

6,090 of the 6,104 `no_abstract` non-loser exclusions carry a DOI. This probe
takes a deterministic sample of them, tries to fetch the missing abstract from
Crossref (via the existing on-demand lookup) and Semantic Scholar (single-DOI
lookup), then re-runs the *unchanged* screen rules in memory to see how many
would now be included — and for those still excluded, why.

It faithfully mirrors `rrl/screen/runner.py`: backfill the abstract, run
langdetect to populate a missing `language`, then `evaluate_paper`. Nothing
about the other DB fields (peer-review, work_type, publisher, citations) is
touched, so this measures the recovery from adding the abstract *alone*.

Usage:
    python scripts/probe_abstract_backfill.py [SAMPLE_SIZE]   # default 200
"""
from __future__ import annotations
import os
import sqlite3
import sys
from collections import Counter

import requests
from dotenv import load_dotenv
from langdetect import detect, DetectorFactory, LangDetectException

from rrl.http import build_session, RateLimitedSession
from rrl.search import crossref
from rrl.screen.rules import evaluate_paper

DetectorFactory.seed = 0

# The screen reads exactly these columns (rrl/screen/runner.py PAPER_COLS).
PAPER_COLS = ("paper_id", "title", "abstract", "venue", "year", "language",
              "is_oa", "oa_pdf_url", "is_peer_reviewed", "is_in_doaj",
              "work_type", "publisher", "citation_count")

SAMPLE_SQL = f"""
    SELECT {','.join(PAPER_COLS)}, doi
    FROM papers
    WHERE included = 0 AND exclusion_reason = 'no_abstract'
      AND doi IS NOT NULL AND doi != ''
      AND paper_id NOT IN (SELECT loser_id FROM paper_merges)
    ORDER BY paper_id          -- paper_id is a content hash: order is random wrt content
    LIMIT ?
"""

S2_LOOKUP = "https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"


def crossref_abstract(session, doi, email):
    try:
        rec = crossref.fetch_by_doi(session, doi, mailto=email)
    except requests.RequestException:
        return None
    return rec.abstract if rec else None


def s2_abstract(session, doi, api_key):
    headers = {"x-api-key": api_key} if api_key else {}
    try:
        r = session.get(S2_LOOKUP.format(doi=doi), params={"fields": "abstract"},
                        headers=headers)
    except requests.RequestException:
        return None
    if r.status_code != 200:
        return None
    return (r.json() or {}).get("abstract")


def main(sample_size: int) -> int:
    load_dotenv()
    email = os.environ.get("OPENALEX_EMAIL", "").strip()
    if not email:
        print("FAIL: OPENALEX_EMAIL not set in .env", file=sys.stderr)
        return 1
    s2_key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip() or None

    session = RateLimitedSession(build_session(email), requests_per_second=5)

    conn = sqlite3.connect("data/rrl.sqlite")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(SAMPLE_SQL, (sample_size,)).fetchall()

    fetched_by_source: Counter = Counter()
    outcomes: Counter = Counter()       # included tier OR exclusion reason after backfill
    not_fetched = 0

    for i, row in enumerate(rows, 1):
        doi = row["doi"]
        abstract = crossref_abstract(session, doi, email)
        source = "crossref" if abstract else None
        if not abstract:
            abstract = s2_abstract(session, doi, s2_key)
            source = "s2" if abstract else None

        if not abstract or not abstract.strip():
            not_fetched += 1
            print(f"[{i}/{len(rows)}] {doi:40s} no abstract")
            continue

        fetched_by_source[source] += 1
        paper = {c: row[c] for c in PAPER_COLS}
        paper["abstract"] = abstract
        if not paper.get("language"):
            try:
                paper["language"] = detect(abstract)
            except LangDetectException:
                pass
        decision = evaluate_paper(paper)
        if decision.get("included"):
            label = f"INCLUDED:{decision.get('quality_tier')}"
        else:
            label = decision.get("exclusion_reason")
        outcomes[label] += 1
        print(f"[{i}/{len(rows)}] {doi:40s} {source:9s} -> {label}")

    n = len(rows)
    fetched = sum(fetched_by_source.values())
    included = sum(v for k, v in outcomes.items() if k.startswith("INCLUDED"))

    print("\n" + "=" * 60)
    print(f"SAMPLE:            {n} no_abstract papers (with DOI)")
    print(f"abstract fetched:  {fetched}  ({fetched / n:.0%})   "
          f"crossref={fetched_by_source['crossref']} s2={fetched_by_source['s2']}")
    print(f"  not fetchable:   {not_fetched}")
    print(f"would be INCLUDED: {included}  ({included / n:.0%} of sample, "
          f"{included / fetched:.0%} of fetched)" if fetched else "would be INCLUDED: 0")
    print("\noutcome breakdown (of fetched):")
    for label, c in outcomes.most_common():
        print(f"  {label:24s} {c:4d}")

    if fetched:
        print("\nEXTRAPOLATION to all 6,090 no_abstract-with-DOI papers:")
        print(f"  ~{round(6090 * fetched / n):,} abstracts fetchable")
        print(f"  ~{round(6090 * included / n):,} new INCLUDED papers "
              f"(current corpus is 4,832)")
    return 0


if __name__ == "__main__":
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    sys.exit(main(size))
