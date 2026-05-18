from rrl.screen.rules import (
    topic_hits, era_tag_for_year, evaluate_paper, decide_quality_tier,
    methodology_exclusion,
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
         "title": "ChatGPT in higher education", "abstract": "Survey of faculty.", "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    r = evaluate_paper(p)
    assert r["included"] == 1
    assert r["era_tag"] == "post_chatgpt"
    assert r["exclusion_reason"] is None

def test_evaluate_rejects_wrong_date():
    p = {"year": 2019, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in university", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "wrong_date"

def test_evaluate_rejects_non_english():
    p = {"year": 2023, "language": "es", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT en universidad", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "non_english"

def test_evaluate_rejects_not_oa():
    p = {"year": 2023, "language": "en", "is_oa": 0, "oa_pdf_url": None,
         "title": "ChatGPT in university", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "not_oa"

def test_evaluate_rejects_off_topic():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Tomato cultivation in Andalusia", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "off_topic"

def test_evaluate_rejects_k12_only():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in middle school classrooms", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "k12_only"

def test_mixed_k12_and_he_forces_review_needed():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in high school and university classrooms",
         "abstract": "Comparison across K-12 and undergraduate.", "venue": "",
         "is_peer_reviewed": 1, "work_type": "journal-article", "publisher": "Springer"}
    r = evaluate_paper(p)
    assert r["included"] == 1
    assert r["quality_tier"] == "review_needed"

def test_high_confidence_for_journal_article_in_doaj():
    p = {"included": 1, "is_peer_reviewed": 0, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "Some Journal", "k12_mixed": False}
    assert decide_quality_tier(p) == "high_confidence"

def test_openalex_modern_article_type_is_high_confidence():
    # OpenAlex's newer type taxonomy uses 'article' instead of 'journal-article'.
    # Without this synonym, peer-reviewed papers from journals get demoted to
    # review_needed for no semantic reason.
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": "article", "publisher": "Emerald Publishing Limited", "k12_mixed": False}
    assert decide_quality_tier(p) == "high_confidence"

def test_book_chapter_requires_allowlisted_publisher():
    bad = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
           "work_type": "book-chapter", "publisher": "Random Self-Pub", "k12_mixed": False}
    good = {**bad, "publisher": "Springer"}
    assert decide_quality_tier(bad) == "review_needed"
    assert decide_quality_tier(good) == "high_confidence"

def test_book_chapter_allowlist_matches_publisher_variants():
    # OpenAlex emits "Springer Science+Business Media" and similar imprint
    # variants, not just "Springer Nature". Substring match should accept
    # these as legitimate.
    base = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
            "work_type": "book-chapter", "k12_mixed": False}
    for pub in [
        "Springer Science+Business Media",
        "Springer International Publishing",
        "Springer Nature (Netherlands)",
        "SAGE Publishing",
        "Taylor & Francis Group",
        "The MIT Press",
    ]:
        assert decide_quality_tier({**base, "publisher": pub}) == "high_confidence", pub
    # But a non-academic-press still gets review_needed.
    assert decide_quality_tier({**base, "publisher": "Atlantis Press"}) == "review_needed"
    assert decide_quality_tier({**base, "publisher": ""}) == "review_needed"

def test_predatory_publisher_forces_review_needed():
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "OMICS International", "k12_mixed": False}
    assert decide_quality_tier(p) == "review_needed"

def test_null_work_type_with_peer_review_is_high_confidence():
    # ERIC papers don't carry work_type/publisher in this pipeline, but
    # ERIC's peerreviewed='T' is authoritative. A NULL work_type with a
    # confirmed peer-review flag should NOT be demoted to review_needed.
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
         "work_type": None, "publisher": None, "k12_mixed": False}
    assert decide_quality_tier(p) == "high_confidence"

def test_null_work_type_without_peer_review_is_review_needed():
    # Same NULL work_type but no peer-review/DOAJ signal still warrants
    # manual review.
    p = {"included": 1, "is_peer_reviewed": 0, "is_in_doaj": 0,
         "work_type": None, "publisher": None, "k12_mixed": False}
    assert decide_quality_tier(p) == "review_needed"

def test_explicit_non_article_work_type_still_demoted():
    # NULL is treated as "metadata missing", but an explicit non-article
    # work_type (e.g. "dataset", "report") still gets review_needed.
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "dataset", "publisher": "X", "k12_mixed": False}
    assert decide_quality_tier(p) == "review_needed"

# --- Dean's stricter rules: peer-reviewed + empirical only ---

def test_evaluate_rejects_when_not_peer_reviewed():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education", "abstract": "Survey of faculty.", "venue": "J",
         "is_peer_reviewed": 0, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "not_peer_reviewed"

def test_evaluate_rejects_when_peer_review_unknown():
    # is_peer_reviewed missing/null is treated as not_peer_reviewed (strict).
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education", "abstract": "Survey of faculty.", "venue": "J"}
    assert evaluate_paper(p)["exclusion_reason"] == "not_peer_reviewed"

def test_evaluate_rejects_systematic_review_title():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education: a systematic review",
         "abstract": "We searched databases.", "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_literature_review_title():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "LLMs in universities: a literature review",
         "abstract": "We synthesize prior work.", "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_meta_analysis():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Effects of ChatGPT on undergraduate learning: a meta-analysis",
         "abstract": "We pooled effect sizes.", "venue": "J",
         "is_peer_reviewed": 1, "work_type": "journal-article"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_editorial_work_type():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT and university teaching",
         "abstract": "Reflections.", "venue": "J",
         "is_peer_reviewed": 1, "work_type": "editorial"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_review_work_type():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Generative AI policy in universities",
         "abstract": "policy", "venue": "J",
         "is_peer_reviewed": 1, "work_type": "review"}
    assert evaluate_paper(p)["exclusion_reason"] == "non_empirical"

def test_evaluate_rejects_commentary_via_abstract():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT and higher education",
         "abstract": "This paper is a commentary on recent developments in AI.",
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
