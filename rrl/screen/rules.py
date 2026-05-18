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

# Methodology detection (empirical studies only per the review protocol)
# Title-level cues that the paper IS a review/editorial/conceptual piece.
NON_EMPIRICAL_TITLE_RE = re.compile(
    r"\b("
    r"(systematic|literature|scoping|narrative|umbrella|integrative|rapid|"
    r"state[ -]of[ -]the[ -]art) review"
    r"|review of (the )?literature"
    r"|meta[ -]?analysis|metaanalysis"
    r"|editorial|commentary|opinion piece|viewpoint|position paper"
    r"|perspectives? article|perspective piece"
    r"|short communication|letter to the editor"
    r"|conceptual (paper|framework|model)|theoretical (paper|framework|model)"
    r"|call (for|to) action"
    r")\b",
    re.IGNORECASE,
)

# Abstract-level cues that the paper itself describes a non-empirical work.
# Anchored to first-person/this-paper phrasing so we don't false-positive on
# empirical papers that merely cite prior reviews.
NON_EMPIRICAL_ABSTRACT_RE = re.compile(
    r"\b(this|the present|the current|our|we) (paper|study|article|review|work|chapter) "
    r"(is |presents |reports |provides |conducts |conducted |"
    r"performs |performed |offers |offered )?"
    r"(a |an |the )?"
    r"(systematic review|literature review|scoping review|narrative review|"
    r"meta[ -]?analysis|conceptual framework|theoretical framework|"
    r"editorial|commentary|opinion|viewpoint|perspective|critical analysis)\b",
    re.IGNORECASE,
)

# OpenAlex work_type values that are categorically non-empirical.
NON_EMPIRICAL_WORK_TYPES = {"editorial", "letter", "erratum", "review", "paratext"}


def methodology_exclusion(title: str | None, abstract: str | None, work_type: str | None) -> str | None:
    """Return an exclusion-reason string if the paper is non-empirical, else None.

    Conservative: only excludes on explicit non-empirical signals. Papers
    without a stereotyped review/editorial phrasing pass through (still
    subject to the other filters / quality tier).
    """
    wt = (work_type or "").strip().lower()
    if wt in NON_EMPIRICAL_WORK_TYPES:
        return "non_empirical"
    if title and NON_EMPIRICAL_TITLE_RE.search(title):
        return "non_empirical"
    if abstract and NON_EMPIRICAL_ABSTRACT_RE.search(abstract):
        return "non_empirical"
    return None


def topic_hits(text: str) -> tuple[int, int, float]:
    ai = {m.group(0).lower() for m in AI_RE.finditer(text)}
    he = {m.group(0).lower() for m in HE_RE.finditer(text)}
    return len(ai), len(he), float(len(ai) + len(he))

def era_tag_for_year(year: int) -> str:
    return "post_chatgpt" if year >= 2023 else "pre_chatgpt"

def _has_text(p: dict) -> str:
    return " ".join(filter(None, [p.get("title"), p.get("abstract"), p.get("venue")]))

def evaluate_paper(p: dict) -> dict:
    """Return a dict of screening decisions for a paper-shaped row.

    Order: cheap-and-categorical filters first (year/lang/OA), then topic
    filters (so off_topic is reported for off-topic papers regardless of
    their peer-review or methodology state), then the protocol's strict gates
    (peer-reviewed + empirical-only). This keeps the exclusion-reason
    counts maximally informative for review.
    """
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
    if p.get("is_peer_reviewed") != 1:
        return {"included": 0, "exclusion_reason": "not_peer_reviewed", "topic_match_score": score}
    nonemp = methodology_exclusion(p.get("title"), p.get("abstract"), p.get("work_type"))
    if nonemp:
        return {"included": 0, "exclusion_reason": nonemp, "topic_match_score": score}
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

def _publisher_in_allowlist(publisher: str) -> bool:
    """Match the academic-press allowlist against a publisher string with
    substring semantics. OpenAlex emits per-imprint names like
    "Springer Science+Business Media" and "Springer International Publishing"
    rather than the bare "Springer Nature" — exact-match misses those, even
    though they're the same publisher. Case-insensitive substring on either
    side: an allowlist name appearing in the publisher string (e.g. "springer"
    in "springer international publishing") is treated as a match.
    """
    if not publisher:
        return False
    p = publisher.lower()
    return any(name.lower() in p for name in ACADEMIC_PRESS_ALLOWLIST)


def decide_quality_tier(p: dict) -> str:
    """Bucket a paper into high_confidence vs review_needed.

    Note on NULL work_type: only OpenAlex sets work_type/publisher in this
    pipeline; ERIC and S2 leave them NULL. Because the screen has already
    enforced peer-review (protocol rule) and the methodology gate has already
    excluded explicit non-empirical work types (editorial/letter/review/...),
    a NULL work_type at this stage means "from a source without that
    metadata" — not "of unknown nature". Treat it as acceptable here so
    peer-reviewed ERIC papers can reach high_confidence on their own merit.
    Truly suspect work types are the explicit ones; we still flag those.
    """
    if p.get("k12_mixed") or p.get("cs_curriculum_signal"):
        return "review_needed"
    publisher = (p.get("publisher") or "").strip()
    if publisher in PREDATORY_BLOCKLIST:
        return "review_needed"
    wt = p.get("work_type")
    if wt == "book-chapter":
        if not _publisher_in_allowlist(publisher):
            return "review_needed"
    # OpenAlex's newer type taxonomy uses 'article' as the equivalent of the
    # legacy 'journal-article'. Both shapes show up in raw_payloads; treat them
    # as the same kind for tier purposes.
    elif wt is not None and wt not in {"journal-article", "article", "proceedings-article", "review"}:
        return "review_needed"
    if not (p.get("is_peer_reviewed") == 1 or p.get("is_in_doaj") == 1):
        return "review_needed"
    return "high_confidence"
