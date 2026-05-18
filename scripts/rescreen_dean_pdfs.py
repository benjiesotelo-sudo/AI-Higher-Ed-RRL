"""Re-screen the 6 dean-provided paper_ids after PDF ingestion.

Dean-provided papers carry an editorial endorsement of peer-review and we
have the PDF locally — so the standard `not_oa` and `not_peer_reviewed`
exclusion paths shouldn't apply. We:

  1. Force is_oa=1 and oa_pdf_url='local' (PDF is locally available).
  2. Force is_peer_reviewed=1 (dean curation = peer-review endorsement).
  3. Re-evaluate via the standard screen rules (topic + methodology gates
     still apply — so e.g. an explicit "literature review" title will still
     be excluded as non_empirical, which is what we want to surface).
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rrl.db import connect
from rrl.screen.rules import evaluate_paper

DB_PATH = ROOT / "data" / "rrl.sqlite"

# The 6 dean paper_ids assigned by scripts/ingest_dean_pdfs.py
DEAN_PAPER_IDS = [
    "03aa44aa607b0e73",  # Fernandes 2025 (dup)
    "41f5b0c950550505",  # Lago 2026 (new)
    "8ab99685bf611427",  # Lawrence 2026 (dup)
    "786b0581c04bbb7a",  # Mittal 2026 (dup)
    "281df417f101e592",  # Soomro 2026 (dup)
    "83fc40cc33332056",  # Toha 2025 (dup)
]


def main() -> int:
    conn = connect(DB_PATH)
    print("Re-screening dean-provided papers with dean-trust overrides\n")
    for pid in DEAN_PAPER_IDS:
        row = conn.execute(
            """SELECT paper_id, title, abstract, venue, year, language, is_oa,
                      oa_pdf_url, is_peer_reviewed, is_in_doaj, work_type,
                      publisher, pdf_filename
               FROM papers WHERE paper_id=?""",
            (pid,),
        ).fetchone()
        if not row:
            print(f"  {pid}: NOT FOUND")
            continue

        paper = {k: row[k] for k in row.keys()}
        paper["is_oa"] = 1
        paper["oa_pdf_url"] = paper.get("oa_pdf_url") or "local"
        paper["is_peer_reviewed"] = 1
        paper["language"] = paper.get("language") or "en"

        decision = evaluate_paper(paper)

        conn.execute(
            """UPDATE papers SET
                 is_oa=1,
                 oa_pdf_url=COALESCE(oa_pdf_url, 'local'),
                 is_peer_reviewed=1,
                 language=COALESCE(language, 'en'),
                 included=?,
                 exclusion_reason=?,
                 quality_tier=?,
                 era_tag=?,
                 topic_match_score=?,
                 last_updated_at=datetime('now')
               WHERE paper_id=?""",
            (decision.get("included"), decision.get("exclusion_reason"),
             decision.get("quality_tier"), decision.get("era_tag"),
             decision.get("topic_match_score"), pid),
        )

        title = (row["title"] or "")[:55]
        print(f"  {pid} ({row['year']}): {title!r}")
        print(f"    included={decision.get('included')} reason={decision.get('exclusion_reason')} "
              f"tier={decision.get('quality_tier')} score={decision.get('topic_match_score')}")
    conn.commit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
