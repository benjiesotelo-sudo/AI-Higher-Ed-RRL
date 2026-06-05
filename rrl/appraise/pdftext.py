"""PDF -> text extraction + per-paper disposition for MMAT appraisal.

Deterministic; no DB, no network, no LLM. The disposition is a coarse triage:
- 'ok'            : a usable English text layer was extracted
- 'no_text_layer' : missing/unreadable file, or too little text (likely scanned)
- 'non_english'   : a text layer exists but is not English (safety net; the
                    corpus is already English-screened on metadata)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

# Below this many extracted characters we assume there is no usable text layer
# (an image-only / scanned PDF). OCR is out of scope (see spec §7); these are
# recorded and worklisted, not silently dropped.
MIN_TEXT_CHARS = 500

# Common English function words for a coarse language gate.
_EN_STOPWORDS = {
    "the", "of", "and", "to", "in", "a", "is", "that", "for", "are", "with",
    "as", "was", "this", "be", "by", "an", "at", "which", "or", "from", "we",
    "it", "not", "were", "study", "students", "research", "data",
}
_EN_MIN_RATIO = 0.04


@dataclass(frozen=True)
class ExtractionResult:
    text: str
    char_count: int
    disposition: str  # 'ok' | 'no_text_layer' | 'non_english'
    detail: str


def looks_english(text: str) -> bool:
    """Coarse English check: fraction of the first 500 word-tokens that are
    common English function words clears a low threshold."""
    words = re.findall(r"[A-Za-z']+", text.lower())[:500]
    if not words:
        return False
    hits = sum(1 for w in words if w in _EN_STOPWORDS)
    return (hits / len(words)) >= _EN_MIN_RATIO


def extract_text(pdf_path: Path) -> ExtractionResult:
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return ExtractionResult("", 0, "no_text_layer", "file missing")
    try:
        doc = fitz.open(pdf_path)
        text = "".join(page.get_text() for page in doc)
        doc.close()
    except Exception as exc:  # corrupt/unreadable PDF — a real case across 2,648 files
        return ExtractionResult("", 0, "no_text_layer", f"open error: {exc}")
    n = len(text.strip())
    if n < MIN_TEXT_CHARS:
        return ExtractionResult(text, n, "no_text_layer", f"{n} chars < {MIN_TEXT_CHARS}")
    if not looks_english(text):
        return ExtractionResult(text, n, "non_english", "english stopword ratio below threshold")
    return ExtractionResult(text, n, "ok", "")
