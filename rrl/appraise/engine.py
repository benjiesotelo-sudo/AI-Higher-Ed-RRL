"""Deterministic emit-side of the MMAT engine: work-file build + quote checking."""
from __future__ import annotations

import hashlib
import re


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
