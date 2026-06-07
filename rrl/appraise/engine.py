"""Deterministic emit-side of the MMAT engine: work-file build + quote checking."""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from rrl.appraise.pdftext import extract_text


def work_id(paper_id: str, task: str, pass_n: int, prompt_version: str) -> str:
    raw = f"{paper_id}|{task}|{pass_n}|{prompt_version}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def normalize_text(s: str) -> str:
    s = s.replace("­", "")              # soft hyphen
    s = re.sub(r"-\s*\n\s*", "", s)          # de-hyphenate line-wrapped words
    s = re.sub(r"\s+", " ", s)               # collapse whitespace/newlines
    return s.strip()


def quote_present(quote: str, text: str) -> bool:
    q = normalize_text(quote)
    return bool(q) and q in normalize_text(text)


CRITERIA = {
    "qualitative": ["1.1", "1.2", "1.3", "1.4", "1.5"],
    "rct": ["2.1", "2.2", "2.3", "2.4", "2.5"],
    "quant_nonrandomized": ["3.1", "3.2", "3.3", "3.4", "3.5"],
    "quant_descriptive": ["4.1", "4.2", "4.3", "4.4", "4.5"],
    "mixed_methods": ["5.1", "5.2", "5.3", "5.4", "5.5"],
}
_CLASSIFY_SCHEMA = {
    "bucket": "one of " + "|".join(CRITERIA) + "|not_assessable",
    "s1": "yes|no|cant_tell", "s2": "yes|no|cant_tell",
    "mm_quant_family": "rct|quant_nonrandomized|quant_descriptive|null",
    "rationale": "str", "source_quote": "verbatim substring", "confidence": "0..1",
}

_PENDING_CLASSIFY = """
SELECT p.paper_id, p.pdf_filename FROM papers p
JOIN mmat_dispositions d ON d.paper_id=p.paper_id AND d.disposition='ok'
WHERE NOT EXISTS (SELECT 1 FROM mmat_classifications c
                  WHERE c.paper_id=p.paper_id AND c.coder=? AND c.prompt_version=?)
ORDER BY p.paper_id
"""


def build_classify_work(conn: sqlite3.Connection, pass_n: int, prompt_version: str,
                        pdf_root: Path, out_path: Path) -> int:
    """Emit one classify work line per pending 'ok' paper (idempotent)."""
    coder = f"llm_pass_{pass_n}"
    rows = conn.execute(_PENDING_CLASSIFY, (coder, prompt_version)).fetchall()
    n = 0
    with open(out_path, "w") as fh:
        for r in rows:
            res = extract_text(Path(pdf_root) / r["pdf_filename"])
            fh.write(json.dumps({
                "work_id": work_id(r["paper_id"], "classify", pass_n, prompt_version),
                "paper_id": r["paper_id"], "task": "classify", "pass": pass_n,
                "prompt_version": prompt_version, "text": res.text,
                "schema": _CLASSIFY_SCHEMA}) + "\n")
            n += 1
    return n
