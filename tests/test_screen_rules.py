from rrl.screen.rules import (
    topic_hits, era_tag_for_year, evaluate_paper, decide_quality_tier,
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
         "title": "ChatGPT in higher education", "abstract": "Survey of faculty.", "venue": "J"}
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

def test_book_chapter_requires_allowlisted_publisher():
    bad = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
           "work_type": "book-chapter", "publisher": "Random Self-Pub", "k12_mixed": False}
    good = {**bad, "publisher": "Springer"}
    assert decide_quality_tier(bad) == "review_needed"
    assert decide_quality_tier(good) == "high_confidence"

def test_predatory_publisher_forces_review_needed():
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "OMICS International", "k12_mixed": False}
    assert decide_quality_tier(p) == "review_needed"
