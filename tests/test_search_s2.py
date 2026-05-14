import json
import responses
from rrl.http import build_session
from rrl.search.base import QuerySpec
from rrl.search.semantic_scholar import SemanticScholarAdapter

def _spec():
    return QuerySpec(ai_terms=["LLM"], he_terms=["graduate student"], year_min=2020, year_max=2026)

@responses.activate
def test_search_paginates_with_token(fixtures_dir):
    p1 = json.loads((fixtures_dir / "s2_bulk_response.json").read_text())
    p2 = {"token": None, "data": []}
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=p1, status=200)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=p2, status=200)
    a = SemanticScholarAdapter(session=build_session("t@e.com"), api_key=None)
    recs = list(a.search(_spec(), run_id="r1"))
    assert len(recs) == 1
    assert recs[0].external_id == "abc123"
    assert recs[0].doi == "10.1/zzz"
    assert recs[0].authors[0]["family"] == "Wang"

@responses.activate
def test_api_key_is_sent_when_present():
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk",
                  json={"token": None, "data": []}, status=200)
    a = SemanticScholarAdapter(session=build_session("t@e.com"), api_key="KEY")
    list(a.search(_spec(), run_id="r1"))
    assert responses.calls[0].request.headers.get("x-api-key") == "KEY"
