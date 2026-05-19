import json
import responses
from rrl.http import build_session
from rrl.search.base import QuerySpec
from rrl.search.openalex import OpenAlexAdapter

def _spec():
    return QuerySpec(ai_terms=["ChatGPT", "LLM"], he_terms=["university"], year_min=2020, year_max=2026)

def test_render_query_contains_filters():
    a = OpenAlexAdapter(session=build_session("t@e.com"), email="t@e.com")
    q = a._render_filter(_spec())
    assert "from_publication_date:2020-01-01" in q
    assert "language:en" in q
    assert "abstract.search" in q
    assert "ChatGPT" in q

@responses.activate
def test_search_paginates_and_yields_records(fixtures_dir):
    p1 = json.loads((fixtures_dir / "openalex_page1.json").read_text())
    p2 = json.loads((fixtures_dir / "openalex_page2.json").read_text())
    responses.add(responses.GET, "https://api.openalex.org/works", json=p1, status=200)
    responses.add(responses.GET, "https://api.openalex.org/works", json=p2, status=200)
    a = OpenAlexAdapter(session=build_session("t@e.com"), email="t@e.com")
    recs = list(a.search(_spec(), run_id="r1"))
    assert len(recs) == 3
    ids = [r.external_id for r in recs]
    assert ids == ["W111", "W222", "W333"]
    assert recs[0].doi == "10.1/aaa"
    assert recs[0].title.startswith("ChatGPT")
    assert recs[0].abstract.startswith("Survey of 245 undergraduate participants")
    assert recs[0].authors[0]["family"] == "Smith"

@responses.activate
def test_search_handles_missing_abstract_index():
    p = {"meta": {"count": 1, "next_cursor": None}, "results": [{
        "id": "https://openalex.org/W1", "doi": None, "title": "T",
        "publication_year": 2023, "language": "en", "type": "journal-article",
        "cited_by_count": 0, "authorships": [], "primary_location": {"source": {}},
        "open_access": {"is_oa": False}, "abstract_inverted_index": None,
    }]}
    responses.add(responses.GET, "https://api.openalex.org/works", json=p, status=200)
    a = OpenAlexAdapter(session=build_session("t@e.com"), email="t@e.com")
    recs = list(a.search(_spec(), run_id="r1"))
    assert recs[0].abstract is None
