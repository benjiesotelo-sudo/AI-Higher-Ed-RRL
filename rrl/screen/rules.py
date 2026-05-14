"""Screening rules: filter chain + quality tiering. No network calls."""
from __future__ import annotations
import re

from rrl.config import (
    AI_TERMS, HE_TERMS, K12_TERMS,
    YEAR_MIN, YEAR_MAX,
    PREDATORY_BLOCKLIST, ACADEMIC_PRESS_ALLOWLIST,
)

def _alt(terms: list[str]) -> str:
    return "|".join(re.escape(t) for t in terms)

AI_RE  = re.compile(rf"\b({_alt(AI_TERMS)})\b", re.IGNORECASE)
HE_RE  = re.compile(rf"\b({_alt(HE_TERMS)})\b", re.IGNORECASE)
K12_RE = re.compile(rf"\b({_alt(K12_TERMS)}|grade [1-9]|grade 1[0-2])\b", re.IGNORECASE)

CS_CURRICULUM_RE = re.compile(
    r"\b(AI curriculum|teaching machine learning|introductory AI course|"
    r"machine learning curriculum|computer science course on AI)\b",
    re.IGNORECASE,
)

def topic_hits(text: str) -> tuple[int, int, float]:
    ai = {m.group(0).lower() for m in AI_RE.finditer(text)}
    he = {m.group(0).lower() for m in HE_RE.finditer(text)}
    return len(ai), len(he), float(len(ai) + len(he))

def era_tag_for_year(year: int) -> str:
    return "post_chatgpt" if year >= 2023 else "pre_chatgpt"

def _has_text(p: dict) -> str:
    return " ".join(filter(None, [p.get("title"), p.get("abstract"), p.get("venue")]))

def evaluate_paper(p: dict) -> dict:
    """Return a dict of screening decisions for a paper-shaped row."""
    year = p.get("year")
    if year is None or year < YEAR_MIN or year > YEAR_MAX:
        return {"included": 0, "exclusion_reason": "wrong_date"}
    if (p.get("language") or "").lower() != "en":
        return {"included": 0, "exclusion_reason": "non_english"}
    if not p.get("is_oa") or not p.get("oa_pdf_url"):
        return {"included": 0, "exclusion_reason": "not_oa"}
    text = _has_text(p)
    ai_n, he_n, score = topic_hits(text)
    k12_n = len(K12_RE.findall(text))
    if ai_n >= 1 and k12_n > 0 and he_n == 0:
        return {"included": 0, "exclusion_reason": "k12_only", "topic_match_score": score}
    if ai_n < 1 or he_n < 1:
        return {"included": 0, "exclusion_reason": "off_topic", "topic_match_score": score}
    k12_mixed = k12_n > 0 and he_n > 0
    cs_curr_signal = bool(CS_CURRICULUM_RE.search(text))
    tier = decide_quality_tier({
        "included": 1,
        "is_peer_reviewed": p.get("is_peer_reviewed"),
        "is_in_doaj": p.get("is_in_doaj"),
        "work_type": p.get("work_type"),
        "publisher": p.get("publisher"),
        "k12_mixed": k12_mixed,
        "cs_curriculum_signal": cs_curr_signal,
    })
    return {
        "included": 1,
        "exclusion_reason": None,
        "topic_match_score": score,
        "era_tag": era_tag_for_year(year),
        "quality_tier": tier,
    }

def decide_quality_tier(p: dict) -> str:
    if p.get("k12_mixed") or p.get("cs_curriculum_signal"):
        return "review_needed"
    publisher = (p.get("publisher") or "").strip()
    if publisher in PREDATORY_BLOCKLIST:
        return "review_needed"
    wt = p.get("work_type")
    if wt == "book-chapter":
        if publisher not in ACADEMIC_PRESS_ALLOWLIST:
            return "review_needed"
    elif wt not in {"journal-article", "proceedings-article", "review"}:
        return "review_needed"
    if not (p.get("is_peer_reviewed") == 1 or p.get("is_in_doaj") == 1):
        return "review_needed"
    return "high_confidence"
