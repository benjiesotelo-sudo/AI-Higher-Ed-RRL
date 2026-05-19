from rrl.screen.rules import (
    topic_hits, era_tag_for_year, evaluate_paper, decide_quality_tier,
    methodology_exclusion,
)

# Realistic 500+ char abstract used across tests that don't specifically test
# methodology / topic / length gates. Contains strong-methodology signals
# ("survey of", "participants", "interviews", "thematic analysis", "regression")
# and is comfortably over the 200-char minimum.
LONG_ABSTRACT = (
    "We conducted a mixed-methods survey of 245 undergraduate participants "
    "across three universities to investigate ChatGPT usage in academic "
    "writing. Data were collected through an online questionnaire and "
    "follow-up interviews with 18 respondents. Thematic analysis of "
    "qualitative responses identified four themes: efficiency gains, "
    "concerns about plagiarism, learning effects, and assessment design. "
    "Quantitative analysis using regression models showed significant "
    "associations between frequency of use and reported learning outcomes."
)


def test_topic_hits_counts_unique():
    text = "ChatGPT in university and college: faculty perceptions"
    ai, he, score = topic_hits(text)
    assert ai >= 1 and he >= 2
    assert score == ai + he

def test_era_tag():
    assert era_tag_for_year(2020) == "pre_chatgpt"
    assert era_tag_for_year(2022) == "pre_chatgpt"
    assert era_tag_for_year(2023) == "post_chatgpt"
    assert era_tag_for_year(2026) == "post_chatgpt"

def test_evaluate_paper_includes_on_topic_oa():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education", "abstract": LONG_ABSTRACT, "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    r = evaluate_paper(p)
    assert r["included"] == 1
    assert r["era_tag"] == "post_chatgpt"
    assert r["exclusion_reason"] is None

def test_evaluate_rejects_wrong_date():
    p = {"year": 2019, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in university", "abstract": LONG_ABSTRACT, "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "wrong_date"

def test_evaluate_rejects_non_english():
    p = {"year": 2023, "language": "es", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT en universidad", "abstract": LONG_ABSTRACT, "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "non_english"

def test_evaluate_rejects_off_topic():
    # Abstract long enough to clear the non_research length gate, but neither
    # title nor abstract head contains AI/HE terms.
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Tomato cultivation in Andalusia",
         "abstract": "This paper documents the cultivation cycle of heirloom tomatoes "
                     "in the Andalusian climate. We tracked yield across seasons and "
                     "documented pest pressures with weekly surveys of plant health and "
                     "soil moisture. Findings inform farming practice in Mediterranean climates.",
         "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "off_topic"

def test_evaluate_rejects_k12_only():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in middle school classrooms",
         "abstract": "Survey of 120 middle school students and their teachers on ChatGPT use. "
                     "Data were collected through questionnaires and follow-up interviews. "
                     "Thematic analysis identified concerns about academic integrity and "
                     "effects on writing skills in elementary-school and high-school students.",
         "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "k12_only"

def test_mixed_k12_and_he_forces_review_needed():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in high school and university classrooms",
         "abstract": "Survey of 245 participants across K-12 and undergraduate cohorts at "
                     "three universities. Data were collected via online questionnaires and "
                     "follow-up interviews with 18 respondents. Thematic analysis identified "
                     "differences across grade levels. Regression analysis of usage patterns "
                     "showed significant effects across high-school and college groups.",
         "venue": "",
         "is_peer_reviewed": 1, "work_type": "journal-article", "publisher": "Springer"}
    r = evaluate_paper(p)
    assert r["included"] == 1
    assert r["quality_tier"] == "review_needed"

def test_high_confidence_for_journal_article_in_doaj():
    # Phase-6: DOAJ-listed journal article still reaches high_confidence when
    # the other gates (work_type, citations/recency, abstract length) are met.
    p = {"included": 1, "is_peer_reviewed": 0, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "Some Journal",
         "k12_mixed": False, "citation_count": 5, "year": 2024,
         "abstract_length": 500}
    assert decide_quality_tier(p) == "high_confidence"

def test_openalex_modern_article_type_is_high_confidence():
    # OpenAlex's newer type taxonomy uses 'article' instead of 'journal-article'.
    # Both should be eligible for high_confidence.
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "article", "publisher": "Emerald Publishing Limited",
         "k12_mixed": False, "citation_count": 5, "year": 2024,
         "abstract_length": 500}
    assert decide_quality_tier(p) == "high_confidence"

def test_book_chapter_always_review_needed_under_revised_rules():
    """Phase-6 tightening: book chapters never reach high_confidence,
    regardless of publisher (they generally don't carry the same empirical
    rigor as journal articles, per user's manual sample review)."""
    base = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
            "work_type": "book-chapter", "k12_mixed": False,
            "citation_count": 5, "year": 2024, "abstract_length": 500}
    for pub in [
        "Random Self-Pub",
        "Springer Science+Business Media",
        "Springer Nature (Netherlands)",
        "Taylor & Francis Group",
        "The MIT Press",
    ]:
        assert decide_quality_tier({**base, "publisher": pub}) == "review_needed", pub

def test_predatory_publisher_forces_review_needed():
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "OMICS International",
         "k12_mixed": False, "citation_count": 5, "year": 2024,
         "abstract_length": 500}
    assert decide_quality_tier(p) == "review_needed"

def test_null_work_type_is_review_needed_under_revised_rules():
    """Phase-6 tightening: NULL work_type → review_needed. Previously NULL was
    treated as "metadata missing" and given the benefit of the doubt, but the
    user's manual sample review showed too many low-quality papers slipping
    through that escape hatch. Now work_type must be explicitly 'article'."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": None, "publisher": None,
         "k12_mixed": False, "citation_count": 5, "year": 2024,
         "abstract_length": 500}
    assert decide_quality_tier(p) == "review_needed"

def test_explicit_non_article_work_type_still_demoted():
    # 'dataset', 'report', 'proceedings-article', 'review' → all review_needed.
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "dataset", "publisher": "Elsevier", "k12_mixed": False,
         "citation_count": 5, "year": 2024, "abstract_length": 500}
    assert decide_quality_tier(p) == "review_needed"

# --- Protocol's stricter rules: peer-reviewed + empirical only ---

def test_evaluate_rejects_when_not_peer_reviewed():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education", "abstract": LONG_ABSTRACT, "venue": "J",
         "is_peer_reviewed": 0, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "not_peer_reviewed"

def test_evaluate_rejects_when_peer_review_unknown():
    # is_peer_reviewed missing/null is treated as not_peer_reviewed (strict).
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education", "abstract": LONG_ABSTRACT, "venue": "J"}
    assert evaluate_paper(p)["exclusion_reason"] == "not_peer_reviewed"

def test_evaluate_rejects_systematic_review_title():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education: a systematic review",
         "abstract": "We searched databases and synthesized findings. " + LONG_ABSTRACT, "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_literature_review_title():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "LLMs in universities: a literature review",
         "abstract": "We synthesize prior work. " + LONG_ABSTRACT, "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_meta_analysis():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Effects of ChatGPT on undergraduate learning: a meta-analysis",
         "abstract": "We pooled effect sizes from prior studies. " + LONG_ABSTRACT, "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_editorial_work_type():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT and university teaching",
         "abstract": "Reflections on recent debates around ChatGPT in higher education. " + LONG_ABSTRACT,
         "venue": "J", "is_peer_reviewed": 1, "work_type": "editorial"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_review_work_type():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Generative AI policy in universities",
         "abstract": "Policy survey covering 50 institutions and their stance on AI. " + LONG_ABSTRACT,
         "venue": "J", "is_peer_reviewed": 1, "work_type": "review"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_commentary_via_abstract():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT and higher education",
         "abstract": "This paper is a commentary on recent developments in AI. " + LONG_ABSTRACT,
         "venue": "J", "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_methodology_exclusion_passes_empirical_paper():
    # Empirical study that cites prior literature reviews should NOT be excluded
    # (our patterns are anchored to first-person/this-paper phrasing).
    assert methodology_exclusion(
        title="ChatGPT adoption among undergraduates",
        abstract="Building on prior literature reviews, we surveyed 350 students "
                 "and analyzed responses thematically.",
        work_type="journal-article",
    ) is None

def test_methodology_exclusion_rejects_conceptual_framework_title():
    assert methodology_exclusion(
        title="A conceptual framework for AI in higher education",
        abstract="",
        work_type="journal-article",
    ) == "non_empirical"


def test_paywalled_paper_with_full_signals_is_included():
    """With OA constraint lifted, a paywalled paper that passes every other
    gate (year, language, topic, peer-review, empirical) should be included."""
    from rrl.screen.rules import evaluate_paper
    paper = {
        "title": "ChatGPT in university classrooms: a mixed-methods study",
        "abstract": "Survey of 200 undergraduate participants on their ChatGPT use in higher education courses. Mixed methods design combining survey responses with interviews of 18 students; thematic analysis identified four themes. Regression analysis showed significant effects on writing outcomes.",
        "venue": "Computers & Education",
        "year": 2024,
        "language": "en",
        "is_oa": 0,          # paywalled — no longer disqualifying
        "oa_pdf_url": None,
        "is_peer_reviewed": 1,
        "is_in_doaj": 0,
        "work_type": "journal-article",
        "publisher": "Elsevier",
    }
    decision = evaluate_paper(paper)
    assert decision["included"] == 1, decision
    assert decision.get("exclusion_reason") is None


def test_paywalled_paper_without_oa_url_is_included():
    """is_oa=1 but no oa_pdf_url is no longer cause for exclusion either."""
    from rrl.screen.rules import evaluate_paper
    paper = {
        "title": "LLMs in faculty professional development",
        "abstract": "We conducted interviews with 30 professors about LLM adoption in higher education. " + LONG_ABSTRACT,
        "venue": "Studies in Higher Education",
        "year": 2024,
        "language": "en",
        "is_oa": 1,
        "oa_pdf_url": None,
        "is_peer_reviewed": 1,
        "is_in_doaj": 0,
        "work_type": "journal-article",
        "publisher": "Taylor & Francis",
    }
    decision = evaluate_paper(paper)
    assert decision["included"] == 1, decision


# --- Phase 6 tightening: stricter rules for the post-OA-lift corpus ---


def test_tight_topic_buried_ai_term_is_off_topic():
    """An AI keyword that only appears past char ~300 of the abstract should
    NOT save an otherwise off-topic paper. Old rule scanned the whole abstract
    and let irrelevant papers slip through (e.g. an oceanography paper that
    mentioned ChatGPT in a single throwaway sentence)."""
    filler = "This paper studies ocean current variability across regions. " * 8  # ~480 chars
    p = {
        "year": 2024, "language": "en", "is_oa": 1,
        "title": "Ocean current variability in the Pacific basin",
        "abstract": filler + " ChatGPT was briefly noted. University researchers participated in fieldwork.",
        "venue": "Journal of Oceanography",
        "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "off_topic"


def test_tight_topic_intersection_in_title_passes():
    """Both terms in title is enough — the abstract head doesn't need them."""
    p = {
        "year": 2024, "language": "en", "is_oa": 1,
        "title": "ChatGPT in university classrooms: adoption patterns",
        "abstract": LONG_ABSTRACT,
        "venue": "Computers & Education",
        "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 3,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_tight_topic_intersection_in_first_300_chars_passes():
    """Topic terms in abstract head also pass even if title is generic."""
    p = {
        "year": 2024, "language": "en", "is_oa": 1,
        "title": "An empirical study",
        "abstract": "We surveyed 245 undergraduate participants about ChatGPT use at three universities. " + LONG_ABSTRACT,
        "venue": "Higher Education Research",
        "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Springer", "citation_count": 2,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_strong_methodology_signal_required():
    """Conceptual / opinion paper with no methodology signals → no_empirical_signal."""
    p = {
        "year": 2024, "language": "en",
        "title": "Reflections on ChatGPT in higher education",
        "abstract": (
            "This article discusses the implications of generative AI tools "
            "for university teaching. We argue that AI offers opportunities "
            "but also raises concerns about academic integrity. The paper "
            "examines various perspectives on AI adoption in academia and "
            "considers the role of faculty in adapting curricula to new "
            "technology shaping higher education."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "no_empirical_signal"


def test_soft_methodology_words_alone_are_not_enough():
    """'method', 'study', 'results' without a real methodology signal are insufficient."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university curricula",
        "abstract": (
            "This study examines the role of ChatGPT in higher education. "
            "The method involves a critical review of recent literature. "
            "Results suggest a growing influence on university teaching. "
            "We discuss implications for faculty and outline a research "
            "agenda for further investigation of generative AI in academia."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "no_empirical_signal"


def test_revised_high_confidence_requires_article_work_type():
    """Proceedings articles no longer qualify for high_confidence — only 'article'/'journal-article'."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "proceedings-article", "publisher": "Elsevier",
         "k12_mixed": False, "abstract_length": 500,
         "citation_count": 5, "year": 2024}
    assert decide_quality_tier(p) == "review_needed"


def test_revised_high_confidence_requires_citations_or_recency():
    """An older paper with zero citations cannot be high_confidence."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "article", "publisher": "Elsevier",
         "k12_mixed": False, "abstract_length": 500,
         "citation_count": 0, "year": 2023}  # 2023 is older than 12 months from 2026
    assert decide_quality_tier(p) == "review_needed"


def test_revised_high_confidence_recent_paper_no_citations_ok():
    """A very recent paper (within 12 months ≈ year >= 2025) gets a pass on citations."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "article", "publisher": "Elsevier",
         "k12_mixed": False, "abstract_length": 500,
         "citation_count": 0, "year": 2025}
    assert decide_quality_tier(p) == "high_confidence"


def test_revised_high_confidence_requires_long_abstract():
    """abstract_length < 400 → review_needed."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "article", "publisher": "Elsevier",
         "k12_mixed": False, "abstract_length": 350,
         "citation_count": 5, "year": 2024}
    assert decide_quality_tier(p) == "review_needed"


def test_revised_high_confidence_requires_major_publisher_or_doaj():
    """No DOAJ + unknown small publisher → review_needed."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "article", "publisher": "Obscure Journals Inc",
         "k12_mixed": False, "abstract_length": 500,
         "citation_count": 5, "year": 2024}
    assert decide_quality_tier(p) == "review_needed"


def test_revised_high_confidence_doaj_alone_is_enough():
    """DOAJ-listed compensates for an unknown publisher."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "article", "publisher": "Unknown Press",
         "k12_mixed": False, "abstract_length": 500,
         "citation_count": 5, "year": 2024}
    assert decide_quality_tier(p) == "high_confidence"


def test_revised_high_confidence_major_publisher_examples():
    """Spot-check each named major publisher promotes to high_confidence."""
    base = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
            "work_type": "article", "k12_mixed": False,
            "abstract_length": 500, "citation_count": 5, "year": 2024}
    for pub in [
        "Elsevier", "Springer", "Springer Nature (Netherlands)", "Wiley",
        "SAGE Publications", "Taylor & Francis", "IEEE", "ACM",
        "Cambridge University Press", "Oxford University Press",
        "Nature Portfolio", "Routledge", "Emerald Publishing Limited",
    ]:
        assert decide_quality_tier({**base, "publisher": pub}) == "high_confidence", pub


def test_revised_high_confidence_book_chapter_demoted():
    """Book chapters never reach high_confidence under the revised rules."""
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "book-chapter", "publisher": "Springer",
         "k12_mixed": False, "abstract_length": 500,
         "citation_count": 5, "year": 2024}
    assert decide_quality_tier(p) == "review_needed"


def test_old_paper_zero_citations_low_topic_excluded():
    """2020-2022 paper with 0 citations and weak topic match (score<4) is excluded
    even if it otherwise passes screen — these tend to be one-off mentions that
    didn't gain traction in the field."""
    # Topic score 2 (one AI hit, one HE hit).
    p = {
        "year": 2021, "language": "en",
        "title": "ChatGPT in university dynamics",
        "abstract": (
            "Survey of 50 participants on attitudes toward technology. Mixed methods "
            "design with interviews of 5 lecturers. The paper briefly notes ChatGPT "
            "use in the university context. Thematic analysis identified themes."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier",
        "citation_count": 0,
    }
    r = evaluate_paper(p)
    assert r["exclusion_reason"] == "low_citation_old", r


def test_old_paper_with_citations_passes():
    """Same paper but with citations is kept — citations are evidence of relevance."""
    p = {
        "year": 2021, "language": "en",
        "title": "ChatGPT in university dynamics",
        "abstract": (
            "Survey of 50 participants on attitudes toward technology. Mixed methods "
            "design with interviews of 5 lecturers. The paper briefly notes ChatGPT "
            "use in the university context. Thematic analysis identified themes."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier",
        "citation_count": 5,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_recent_paper_zero_citations_not_punished_by_old_filter():
    """A 2024+ paper with 0 citations should NOT trip the old-paper filter."""
    p = {
        "year": 2025, "language": "en",
        "title": "ChatGPT in university dynamics",
        "abstract": (
            "Survey of 50 participants on attitudes toward technology. Mixed methods "
            "design with interviews of 5 lecturers. The paper briefly notes ChatGPT "
            "use in the university context. Thematic analysis identified themes."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier",
        "citation_count": 0,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_old_paper_strong_topic_match_passes_even_with_zero_citations():
    """A 2021 paper with 0 citations but strong topic (score>=4) is kept."""
    p = {
        "year": 2021, "language": "en",
        "title": "ChatGPT, large language models, and ChatGPT use in university classrooms and undergraduate courses",
        "abstract": LONG_ABSTRACT,
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier",
        "citation_count": 0,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_ideological_political_in_title_and_abstract_excluded():
    """Chinese ideological-and-political-education pedagogy is out of scope."""
    p = {
        "year": 2024, "language": "en",
        "title": "AI assistance in ideological and political education at universities",
        "abstract": (
            "We surveyed 120 undergraduate participants in ideological and political "
            "courses at a university to investigate ChatGPT adoption. Data were "
            "collected via questionnaires. Thematic analysis identified themes around "
            "AI-aided study of ideological and political curricula."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "out_of_scope_subdomain"


def test_sixixiang_chinese_chars_excluded():
    """The Chinese term 思政 (sixiang zhengzhi = ideological-political) in both
    title and abstract should also trigger out_of_scope_subdomain."""
    p = {
        "year": 2024, "language": "en",
        "title": "AI-assisted 思政 education in universities",
        "abstract": (
            "Survey of 245 undergraduate participants in 思政 courses at a university. "
            "Data were collected through questionnaires and follow-up interviews with "
            "18 faculty members. Thematic analysis identified four themes. Regression "
            "analysis showed effects of AI-assisted 思政 instruction on outcomes."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "out_of_scope_subdomain"


def test_phrase_only_in_abstract_does_not_trigger_subdomain_exclusion():
    """A passing mention of the phrase in abstract alone (not in title) should
    not exclude — the rule requires both."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university writing courses",
        "abstract": "Survey of 245 undergraduate participants on ChatGPT use, including "
                    "some discussion of ideological and political reading. Data were "
                    "collected through interviews and online questionnaires; regression "
                    "analysis showed significant outcomes across disciplines.",
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 3,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_retracted_paper_excluded_square_brackets():
    p = {
        "year": 2024, "language": "en",
        "title": "[Retracted] ChatGPT in university classrooms",
        "abstract": LONG_ABSTRACT,
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "retracted"


def test_retracted_paper_excluded_colon_prefix():
    p = {
        "year": 2024, "language": "en",
        "title": "RETRACTED: ChatGPT in higher education",
        "abstract": LONG_ABSTRACT,
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "retracted"


def test_retracted_paper_excluded_parenthetical():
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university classrooms (Retracted Article)",
        "abstract": LONG_ABSTRACT,
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "retracted"


def test_retracted_paper_excluded_retracted_article_prefix():
    """Publisher variant: 'RETRACTED ARTICLE:' (no colon-only form)."""
    p = {
        "year": 2024, "language": "en",
        "title": "RETRACTED ARTICLE: ChatGPT in higher education",
        "abstract": LONG_ABSTRACT,
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "retracted"


def test_word_retract_in_body_does_not_mark_retracted():
    """A paper that DISCUSSES retractions but isn't retracted should pass."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university classrooms: trust and retraction concerns",
        "abstract": "Survey of 245 undergraduates on AI use. Mixed methods design "
                    "with interviews of 18 faculty about retraction policies. "
                    "Thematic analysis identified four themes. Regression analysis "
                    "showed significant effects on student trust in academic AI use.",
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 3,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_non_latin_abstract_excluded_as_language_mismatch():
    """language='en' metadata but the abstract body is mostly CJK characters."""
    cjk_block = "本文研究了人工智能在高等教育中的应用，调查了大学生的使用情况，分析了不同学科的差异。" * 8
    p = {
        "year": 2024, "language": "en",
        "title": "AI in universities",
        "abstract": cjk_block,
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "language_mismatch"


def test_mostly_english_abstract_with_some_unicode_passes():
    """A normal English abstract with a few non-ASCII chars (curly quotes, é, etc.)
    should NOT trip the non-Latin detector."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university classrooms",
        "abstract": (
            "Survey of 245 undergraduate participants across three universities to "
            "investigate ChatGPT use. The students' responses (n = 245) were analyzed "
            "with regression. Café-style focus groups and interviews were conducted "
            "with 18 faculty. Thematic analysis identified four themes."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 3,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_outreach_service_activity_excluded():
    """Outreach / community-service writeups should not be treated as research."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in higher education awareness program",
        "abstract": (
            "Participants in this community service activity at a university discussed ChatGPT. "
            "The pengabdian masyarakat program included a workshop with faculty members "
            "providing understanding of generative AI tools. We interviewed 12 attendees."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "outreach_paper"


def test_outreach_collaboration_phrase_excluded():
    p = {
        "year": 2024, "language": "en",
        "title": "Faculty workshop on ChatGPT in higher education",
        "abstract": (
            "A collaboration between faculty in providing understanding of ChatGPT to "
            "undergraduate students. The workshop included a survey of 25 participants "
            "and analysis of responses. The outreach program ran for one semester."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "outreach_paper"


def test_real_research_with_word_service_is_not_outreach():
    """The word 'service' alone (e.g. 'service-learning') should not trigger outreach exclusion."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university service-learning courses",
        "abstract": (
            "Survey of 245 undergraduate participants in service-learning courses at three universities. "
            "Mixed methods design with interviews of 18 students. Thematic analysis identified "
            "four themes around ChatGPT adoption. Regression analysis showed significant effects."
        ),
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 3,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_short_abstract_excluded_as_non_research():
    """Abstracts under 200 characters indicate stubs/index entries, not research."""
    p = {
        "year": 2024, "language": "en",
        "title": "ChatGPT in university education",
        "abstract": "Survey of 25 participants. Brief.",  # <200 chars
        "venue": "J", "is_peer_reviewed": 1, "work_type": "article",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "non_research_paper"


def test_book_apparatus_titles_excluded_as_non_research():
    """Book front/back-matter titles indicate non-research book apparatus."""
    base = {
        "year": 2024, "language": "en", "abstract": LONG_ABSTRACT,
        "is_peer_reviewed": 1, "work_type": "book-chapter", "publisher": "Springer",
    }
    for bad_title in ["About the Book", "Contributors", "Conclusion",
                       "Foreword", "Preface", "Acknowledgments", "Index"]:
        assert evaluate_paper({**base, "title": bad_title})["exclusion_reason"] == "non_research_paper", bad_title


def test_apparatus_title_match_is_case_insensitive():
    p = {
        "year": 2024, "language": "en", "abstract": LONG_ABSTRACT,
        "title": "CONTRIBUTORS",
        "is_peer_reviewed": 1, "work_type": "book-chapter", "publisher": "Springer",
    }
    assert evaluate_paper(p)["exclusion_reason"] == "non_research_paper"


def test_normal_titles_not_caught_by_apparatus_check():
    """'Contributing factors...', 'Conclusions about X' should NOT match."""
    p = {
        "year": 2024, "language": "en", "abstract": LONG_ABSTRACT,
        "title": "Conclusions about ChatGPT in higher education classrooms",
        "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 3,
    }
    r = evaluate_paper(p)
    assert r["included"] == 1, r


def test_methodology_signal_examples_each_pass():
    """Spot-check a handful of phrases from the strong-signal whitelist."""
    base = {
        "year": 2024, "language": "en", "is_oa": 1,
        "title": "ChatGPT in university classrooms",
        "venue": "Computers & Education",
        "is_peer_reviewed": 1, "work_type": "article",
        "publisher": "Elsevier", "citation_count": 2,
    }
    snippets = [
        # Each phrase is embedded in enough surrounding text to clear the 200-char min.
        "We interviewed 18 faculty members about ChatGPT use. " + LONG_ABSTRACT,
        "We collected data from 305 students. Data were collected via online survey. " + LONG_ABSTRACT,
        "We employed a mixed methods design to study ChatGPT adoption. " + LONG_ABSTRACT,
        "We ran an experimental design comparing two cohorts of undergraduates. " + LONG_ABSTRACT,
        "We report an ANOVA on student outcomes following ChatGPT adoption. " + LONG_ABSTRACT,
        "We fit a structural equation model relating ChatGPT use to outcomes. " + LONG_ABSTRACT,
        "An ethnographic study of a writing classroom using ChatGPT. " + LONG_ABSTRACT,
        "We performed a case study of one university adopting ChatGPT. " + LONG_ABSTRACT,
        "Thematic analysis of 30 interviews with university instructors. " + LONG_ABSTRACT,
        "Regression analysis of 412 respondents on ChatGPT adoption in higher education. " + LONG_ABSTRACT,
        "Sample of 200 undergraduates surveyed about ChatGPT in higher education. " + LONG_ABSTRACT,
        "Mixed methods qualitative analysis of focus groups. " + LONG_ABSTRACT,
        "We surveyed N = 412 students across three universities. " + LONG_ABSTRACT,
    ]
    for s in snippets:
        r = evaluate_paper({**base, "abstract": s})
        assert r["included"] == 1, (s[:60], r)
