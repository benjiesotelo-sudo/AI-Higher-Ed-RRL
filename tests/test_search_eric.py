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


@responses.activate
def test_search_handles_scalar_string_fields():
    # ERIC's real API returns title/description/publisher as strings when single-valued.
    # The old parser indexed [0] and grabbed the first character. Regression test.
    payload = {"response": {"numFound": 1, "start": 0, "docs": [{
        "id": "EJ200002",
        "title": "Higher education adoption of generative AI",
        "author": ["Smith, J."],
        "publicationdateyear": 2025,
        "description": "Empirical study of ChatGPT use.",
        "publisher": "Journal of Higher Ed",
        "language": ["English"],
    }]}}
    empty = {"response": {"numFound": 1, "start": 2000, "docs": []}}
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=payload, status=200)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=empty, status=200)
    a = ERICAdapter(session=build_session("t@e.com"))
    rec = list(a.search(_spec(), run_id="r2"))[0]
    assert rec.title == "Higher education adoption of generative AI"
    assert rec.abstract == "Empirical study of ChatGPT use."
    assert rec.venue == "Journal of Higher Ed"
    assert rec.language == "en"
