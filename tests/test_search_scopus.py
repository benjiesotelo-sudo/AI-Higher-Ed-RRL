import json
import responses
from rrl.http import build_session
from rrl.search.base import QuerySpec
from rrl.search.scopus import ScopusAdapter, BASE


def _spec():
    return QuerySpec(
        ai_terms=["ChatGPT", "LLM"],
        he_terms=["higher education", "university"],
        year_min=2020,
        year_max=2026,
    )


def _adapter(api_key="fake-key", inst_token=None):
    return ScopusAdapter(session=build_session("t@e.com"), api_key=api_key, inst_token=inst_token)


def test_render_query_contains_required_filters():
    a = _adapter()
    q = a._render_query(_spec())
    assert "TITLE-ABS-KEY" in q
    assert "ChatGPT" in q
    assert "higher education" in q
    assert "PUBYEAR > 2019" in q
    assert "PUBYEAR < 2027" in q
    assert "LANGUAGE(english)" in q
    assert "DOCTYPE(ar)" in q
    assert "DOCTYPE(cp)" in q
    assert "DOCTYPE(re)" in q
    assert "DOCTYPE(ch)" in q


def test_render_query_quotes_multi_word_terms():
    a = _adapter()
    q = a._render_query(_spec())
    assert '"higher education"' in q
    assert '"ChatGPT"' in q  # also quoted for consistency


@responses.activate
def test_search_sends_required_headers():
    responses.add(
        responses.GET, BASE,
        json={"search-results": {"entry": [], "cursor": {}}},
        status=200,
    )
    a = _adapter(api_key="fake-key", inst_token="fake-token")
    list(a.search(_spec(), run_id="r1"))
    assert len(responses.calls) == 1
    call = responses.calls[0].request
    assert call.headers.get("X-ELS-APIKey") == "fake-key"
    assert call.headers.get("X-ELS-Insttoken") == "fake-token"
    assert call.headers.get("Accept") == "application/json"


@responses.activate
def test_search_omits_insttoken_when_none():
    responses.add(
        responses.GET, BASE,
        json={"search-results": {"entry": [], "cursor": {}}},
        status=200,
    )
    a = _adapter(api_key="fake-key", inst_token=None)
    list(a.search(_spec(), run_id="r1"))
    call = responses.calls[0].request
    assert "X-ELS-Insttoken" not in call.headers


@responses.activate
def test_search_paginates_via_cursor(fixtures_dir):
    p1 = json.loads((fixtures_dir / "scopus_page1.json").read_text())
    p2 = json.loads((fixtures_dir / "scopus_page2.json").read_text())
    responses.add(responses.GET, BASE, json=p1, status=200)
    responses.add(responses.GET, BASE, json=p2, status=200)
    a = _adapter()
    recs = list(a.search(_spec(), run_id="r1"))
    assert len(recs) == 3
    ids = [r.external_id for r in recs]
    assert ids == ["SCOPUS_ID:85179000001", "SCOPUS_ID:85179000002", "SCOPUS_ID:85179000003"]


@responses.activate
def test_search_parses_doi_title_abstract_year(fixtures_dir):
    p1 = json.loads((fixtures_dir / "scopus_page1.json").read_text())
    p2 = json.loads((fixtures_dir / "scopus_page2.json").read_text())
    responses.add(responses.GET, BASE, json=p1, status=200)
    responses.add(responses.GET, BASE, json=p2, status=200)
    recs = list(_adapter().search(_spec(), run_id="r1"))
    r0 = recs[0]
    assert r0.doi == "10.1016/j.caeai.2024.100200"
    assert r0.title == "ChatGPT in higher education classrooms"
    assert r0.abstract == "This study explores ChatGPT adoption by university faculty."
    assert r0.year == 2024
    assert r0.venue == "Journal of AI in Education"
    assert r0.authors[0]["family"] == "Smith"
    assert r0.authors[0]["given"] == "John"


@responses.activate
def test_search_handles_missing_doi_and_abstract(fixtures_dir):
    p1 = json.loads((fixtures_dir / "scopus_page1.json").read_text())
    p2 = json.loads((fixtures_dir / "scopus_page2.json").read_text())
    responses.add(responses.GET, BASE, json=p1, status=200)
    responses.add(responses.GET, BASE, json=p2, status=200)
    recs = list(_adapter().search(_spec(), run_id="r1"))
    r2 = recs[2]
    assert r2.doi is None
    assert r2.abstract is None
    assert r2.authors == []


@responses.activate
def test_search_stops_when_cursor_absent():
    payload = {"search-results": {"entry": [{
        "dc:identifier": "SCOPUS_ID:1",
        "dc:title": "T",
        "prism:coverDate": "2023-01-01",
        "subtype": "ar",
    }], "cursor": {"@current": "*"}}}  # no @next
    responses.add(responses.GET, BASE, json=payload, status=200)
    a = _adapter()
    recs = list(a.search(_spec(), run_id="r1"))
    assert len(recs) == 1
    assert len(responses.calls) == 1


@responses.activate
def test_search_normalizes_doi_prefix():
    payload = {"search-results": {"entry": [{
        "dc:identifier": "SCOPUS_ID:1",
        "dc:title": "T",
        "prism:doi": "HTTPS://DOI.ORG/10.1016/ABC.123",
        "prism:coverDate": "2023-01-01",
        "subtype": "ar",
    }], "cursor": {}}}
    responses.add(responses.GET, BASE, json=payload, status=200)
    rec = next(_adapter().search(_spec(), run_id="r1"))
    assert rec.doi == "10.1016/abc.123"
