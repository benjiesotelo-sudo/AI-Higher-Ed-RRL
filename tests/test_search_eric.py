import json
import responses
from rrl.http import build_session
from rrl.search.base import QuerySpec
from rrl.search.eric import ERICAdapter

def _spec():
    return QuerySpec(ai_terms=["ChatGPT"], he_terms=["college"], year_min=2020, year_max=2026)

@responses.activate
def test_search_yields_records(fixtures_dir):
    payload = json.loads((fixtures_dir / "eric_response.json").read_text())
    empty = {"response": {"numFound": 2, "start": 2000, "docs": []}}
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=payload, status=200)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=empty, status=200)
    a = ERICAdapter(session=build_session("t@e.com"))
    recs = list(a.search(_spec(), run_id="r1"))
    assert [r.external_id for r in recs] == ["EJ100001", "ED600001"]
    assert recs[0].year == 2024
    assert recs[0].authors[0]["family"] == "Smith"
    assert recs[0].abstract.startswith("A study")
