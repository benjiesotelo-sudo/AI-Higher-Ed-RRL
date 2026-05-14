from rrl.search.base import (
    QuerySpec, RawRecord,
    normalize_doi, normalize_title, normalize_author_name, query_hash,
)

def test_normalize_doi_strips_url_prefix_and_lowercases():
    assert normalize_doi("https://doi.org/10.1234/AbC") == "10.1234/abc"
    assert normalize_doi("doi:10.1234/AbC") == "10.1234/abc"
    assert normalize_doi("10.1234/abc.") == "10.1234/abc"
    assert normalize_doi(None) is None
    assert normalize_doi("") is None

def test_normalize_title_strips_punct_and_stopwords():
    a = normalize_title("The Use of ChatGPT in Higher Education!")
    b = normalize_title("Use of ChatGPT in Higher Education")
    assert a == b
    assert "the" not in a.split()

def test_normalize_title_strips_diacritics():
    assert normalize_title("Café Pédagogique") == normalize_title("Cafe Pedagogique")

def test_normalize_author_name_lowercases_and_strips():
    assert normalize_author_name("García-Márquez") == normalize_author_name("Garcia Marquez")
    assert normalize_author_name("  O'Brien  ") == "obrien"

def test_query_hash_is_deterministic():
    q1 = QuerySpec(ai_terms=["a", "b"], he_terms=["c"], year_min=2020, year_max=2026)
    q2 = QuerySpec(ai_terms=["a", "b"], he_terms=["c"], year_min=2020, year_max=2026)
    assert query_hash(q1) == query_hash(q2)
    q3 = QuerySpec(ai_terms=["b", "a"], he_terms=["c"], year_min=2020, year_max=2026)
    assert query_hash(q1) == query_hash(q3)  # order-independent

def test_rawrecord_construction():
    r = RawRecord(
        external_id="W1", doi="10.1/x", title="T", authors=[{"family": "Smith"}],
        year=2023, venue="J", abstract="A", language="en", raw_payload={"_": 1},
    )
    assert r.external_id == "W1"
