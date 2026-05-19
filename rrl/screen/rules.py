"""Screening rules: filter chain + quality tiering. No network calls."""
from __future__ import annotations
import re
import unicodedata

from rrl.config import (
    AI_TERMS, HE_TERMS, K12_TERMS,
    YEAR_MIN, YEAR_MAX,
    PREDATORY_BLOCKLIST, ACADEMIC_PRESS_ALLOWLIST, MAJOR_PUBLISHER_ALLOWLIST,
)

# Papers published in this year or later count as "within the last 12 months"
# for the high_confidence citation-leniency rule. Anchored to YEAR_MAX rather
# than a real date so tests are deterministic and the rule advances naturally
# when the corpus window slides.
RECENT_YEAR_THRESHOLD = YEAR_MAX - 1
HIGH_CONFIDENCE_MIN_ABSTRACT_CHARS = 400
HIGH_CONFIDENCE_WORK_TYPES = frozenset({"article", "journal-article"})

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


# Positive empirical signal: the abstract must contain at least one of these
# strong methodology phrases to be considered an empirical study. Soft words
# like "method", "study", "results" alone are insufficient — those appear in
# conceptual/opinion pieces too.
STRONG_METHODOLOGY_RE = re.compile(
    r"\b(?:"
    r"participants?|respondents?|sample of|survey of|"
    r"interviews?|interviewed|"
    r"data (?:was|were) collected|"
    r"mixed methods?|"
    r"qualitative analysis|quantitative analysis|"
    r"experimental design|case study of|"
    r"ethnograph[a-z]*|"
    r"thematic analysis|structural equation|"
    r"ANOVA|regression"
    r")\b",
    re.IGNORECASE,
)
# Separate pattern for sample-size notation (\b doesn't compose with the
# digit-anchored form cleanly inside the alternation).
SAMPLE_SIZE_RE = re.compile(r"\b[Nn]\s*=\s*\d")


def has_strong_methodology_signal(abstract: str | None) -> bool:
    if not abstract:
        return False
    return bool(STRONG_METHODOLOGY_RE.search(abstract) or SAMPLE_SIZE_RE.search(abstract))


# Outreach / community-service writeups: these have many surface features of
# empirical work (participants, interviews, workshops) but are not research —
# they're event reports. Catch them by their specific phrasing.
OUTREACH_RE = re.compile(
    r"\b("
    r"service activity"
    r"|community service"
    r"|pengabdian masyarakat"
    r"|outreach program"
    r"|providing understanding"
    r"|collaboration between (?:lecturers|faculty) in providing"
    r"|workshop with (?:lecturers|faculty)"
    r")\b",
    re.IGNORECASE,
)


def is_outreach_paper(abstract: str | None) -> bool:
    if not abstract:
        return False
    return bool(OUTREACH_RE.search(abstract))


# Book apparatus and front/back-matter titles: front-of-book or end-of-book
# chapters whose entire "abstract" is structural, not research.
NON_RESEARCH_TITLES = frozenset({
    "about the book", "contributors", "conclusion",
    "foreword", "preface", "acknowledgments", "acknowledgements", "index",
})

MIN_ABSTRACT_CHARS = 200


def is_non_research_paper(title: str | None, abstract: str | None) -> bool:
    """Apparatus-style title, or abstract too short to be a real paper."""
    t = (title or "").strip().rstrip(".").lower()
    if t in NON_RESEARCH_TITLES:
        return True
    if len((abstract or "").strip()) < MIN_ABSTRACT_CHARS:
        return True
    return False


# Non-Latin script detection: catches abstracts whose language metadata says
# 'en' but whose body is dominated by CJK / Cyrillic / Arabic / etc. characters.
LANGUAGE_MISMATCH_HEAD_CHARS = 200
LANGUAGE_MISMATCH_THRESHOLD = 0.20  # >20% non-Latin letters in the first 200 chars


def _is_latin_letter(ch: str) -> bool:
    if not ch.isalpha():
        return False
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return False


# Retracted-paper title markers. Publishers use a few standard prefixes/suffixes
# to flag retraction; ANY of these in the title is grounds for exclusion.
RETRACTED_TITLE_RE = re.compile(
    r"(\[Retracted\]|RETRACTED:|RETRACTED ARTICLE:|\(Retracted Article\))",
    re.IGNORECASE,
)


def is_retracted(title: str | None) -> bool:
    if not title:
        return False
    return bool(RETRACTED_TITLE_RE.search(title))


# Ideological-and-political education is a Chinese curriculum subdomain that
# is out of scope for this review. Excluded only when BOTH title and abstract
# carry the marker — a passing mention in the abstract alone is not enough.
IDEOLOGICAL_POLITICAL_RE = re.compile(
    r"(ideological\s+and\s+political|ideological-political|思政)",
    re.IGNORECASE,
)


def is_ideological_political_subdomain(title: str | None, abstract: str | None) -> bool:
    if not title or not abstract:
        return False
    return bool(
        IDEOLOGICAL_POLITICAL_RE.search(title)
        and IDEOLOGICAL_POLITICAL_RE.search(abstract)
    )


def is_language_mismatch(abstract: str | None) -> bool:
    """True if the abstract head is dominated by non-Latin-script letters."""
    if not abstract:
        return False
    head = abstract[:LANGUAGE_MISMATCH_HEAD_CHARS]
    if not head:
        return False
    non_latin = sum(1 for c in head if c.isalpha() and not _is_latin_letter(c))
    return (non_latin / len(head)) > LANGUAGE_MISMATCH_THRESHOLD


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


# How many characters of the abstract count toward topic relevance. Anything
# past this is treated as "buried" — a paper that only mentions AI in passing
# at the end of a long off-topic abstract shouldn't be considered AI-relevant.
TOPIC_ABSTRACT_HEAD_CHARS = 300


def _topic_text(p: dict) -> str:
    """Text used for AI/HE/K-12 topic detection: title + first 300 chars of abstract."""
    title = p.get("title") or ""
    abstract = (p.get("abstract") or "")[:TOPIC_ABSTRACT_HEAD_CHARS]
    return f"{title} {abstract}".strip()


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
    if is_retracted(p.get("title")):
        return {"included": 0, "exclusion_reason": "retracted"}
    if is_language_mismatch(p.get("abstract")):
        return {"included": 0, "exclusion_reason": "language_mismatch"}
    if is_non_research_paper(p.get("title"), p.get("abstract")):
        return {"included": 0, "exclusion_reason": "non_research_paper"}
    if is_ideological_political_subdomain(p.get("title"), p.get("abstract")):
        return {"included": 0, "exclusion_reason": "out_of_scope_subdomain"}
    text = _topic_text(p)
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
    if is_outreach_paper(p.get("abstract")):
        return {"included": 0, "exclusion_reason": "outreach_paper", "topic_match_score": score}
    if not has_strong_methodology_signal(p.get("abstract")):
        return {"included": 0, "exclusion_reason": "no_empirical_signal", "topic_match_score": score}
    # Old papers with no citation traction AND a weak topic match are excluded
    # as low-signal: they're typically one-off mentions that didn't gain
    # traction in the AI-in-HE literature.
    if 2020 <= year <= 2022 and (p.get("citation_count") or 0) == 0 and score < 4:
        return {"included": 0, "exclusion_reason": "low_citation_old", "topic_match_score": score}
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
        "citation_count": p.get("citation_count"),
        "year": year,
        "abstract_length": len((p.get("abstract") or "").strip()),
    })
    return {
        "included": 1,
        "exclusion_reason": None,
        "topic_match_score": score,
        "era_tag": era_tag_for_year(year),
        "quality_tier": tier,
    }

def _publisher_substring_match(publisher: str, allowlist) -> bool:
    """Case-insensitive substring match against an allowlist of publisher names."""
    if not publisher:
        return False
    p = publisher.lower()
    return any(name.lower() in p for name in allowlist)


def _publisher_in_allowlist(publisher: str) -> bool:
    """Legacy academic-press allowlist match (used by book-chapter check)."""
    return _publisher_substring_match(publisher, ACADEMIC_PRESS_ALLOWLIST)


def _publisher_is_major(publisher: str) -> bool:
    """Phase-6 major-publisher allowlist match for high_confidence promotion."""
    return _publisher_substring_match(publisher, MAJOR_PUBLISHER_ALLOWLIST)


def decide_quality_tier(p: dict) -> str:
    """Bucket a paper into high_confidence vs review_needed.

    Revised in Phase 6 to be substantially stricter than the prior rules.
    A paper reaches high_confidence only when ALL hold:
      * work_type is 'article' / 'journal-article' (book-chapter / proceedings /
        review / dataset / etc. → review_needed)
      * citation_count >= 1 OR year is within the last 12 months (RECENT_YEAR_THRESHOLD)
      * abstract length >= 400 characters
      * DOAJ-listed OR publisher matches MAJOR_PUBLISHER_ALLOWLIST
    The existing demotion signals (k12_mixed, cs_curriculum_signal, predatory
    publisher) still force review_needed.
    """
    if p.get("k12_mixed") or p.get("cs_curriculum_signal"):
        return "review_needed"
    publisher = (p.get("publisher") or "").strip()
    if publisher in PREDATORY_BLOCKLIST:
        return "review_needed"
    wt = p.get("work_type")
    if wt not in HIGH_CONFIDENCE_WORK_TYPES:
        return "review_needed"
    citations = p.get("citation_count") or 0
    year = p.get("year") or 0
    if citations < 1 and year < RECENT_YEAR_THRESHOLD:
        return "review_needed"
    if (p.get("abstract_length") or 0) < HIGH_CONFIDENCE_MIN_ABSTRACT_CHARS:
        return "review_needed"
    if not (p.get("is_in_doaj") == 1 or _publisher_is_major(publisher)):
        return "review_needed"
    return "high_confidence"
