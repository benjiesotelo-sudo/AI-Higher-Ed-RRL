import json
import responses
from rrl.http import build_session
from rrl.search.crossref import fetch_by_doi

@responses.activate
def test_fetch_returns_normalized_record(fixtures_dir):
    payload = json.loads((fixtures_dir / "crossref_doi.json").read_text())
    responses.add(responses.GET, "https://api.crossref.org/works/10.1/zzz", json=payload, status=200)
    rec = fetch_by_doi(build_session("t@e.com"), "10.1/zzz", mailto="t@e.com")
    assert rec is not None
    assert rec.doi == "10.1/zzz"
    assert rec.title.startswith("A study")
    assert rec.year == 2024
    assert rec.authors[0]["family"] == "Wang"
    assert rec.abstract == "An empirical study of faculty attitudes."

@responses.activate
def test_fetch_returns_none_on_404():
    responses.add(responses.GET, "https://api.crossref.org/works/10.1/missing", status=404)
    rec = fetch_by_doi(build_session("t@e.com"), "10.1/missing", mailto="t@e.com")
    assert rec is None
