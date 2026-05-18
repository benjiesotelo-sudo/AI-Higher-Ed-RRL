import json
import responses
from rrl.http import build_session
from rrl.search.base import QuerySpec
from rrl.search.scopus import ScopusAdapter, BASE, OFFSET_CAP, PAGE_SIZE


def _spec(year_min=2024, year_max=2024):
    return QuerySpec(
        ai_terms=["ChatGPT", "LLM"],
        he_terms=["higher education", "university"],
        year_min=year_min,
        year_max=year_max,
    )


def _adapter(api_key="fake-key", inst_token=None):
    return ScopusAdapter(session=build_session("t@e.com"), api_key=api_key, inst_token=inst_token)


def _probe_response(total: int) -> dict:
    return {"search-results": {"opensearch:totalResults": str(total), "entry": []}}


def _page_response(entries: list[dict], total: int) -> dict:
    return {"search-results": {"opensearch:totalResults": str(total), "entry": entries}}


# --- query-rendering tests ---

def test_render_query_contains_required_filters():
    a = _adapter()
    q = a._render_query(_spec())
    assert "TITLE-ABS-KEY" in q
    assert "ChatGPT" in q
    assert "higher education" in q
    assert "PUBYEAR > 2023" in q
    assert "PUBYEAR < 2025" in q
    assert "LANGUAGE(english)" in q
    assert "DOCTYPE(ar)" in q
    assert "DOCTYPE(cp)" in q
    assert "DOCTYPE(re)" in q
    assert "DOCTYPE(ch)" in q


def test_render_query_quotes_multi_word_terms():
    a = _adapter()
    q = a._render_query(_spec())
    assert '"higher education"' in q
    assert '"ChatGPT"' in q


def test_year_query_uses_pubyear_equals():
    a = _adapter()
    yq = a._year_query(_spec(), 2024)
    assert "PUBYEAR = 2024" in yq
    assert "LANGUAGE(english)" in yq
    assert "DOCTYPE(ar)" in yq


def test_half_year_query_uses_pubdatetxt():
    a = _adapter()
    h1 = a._half_year_query(_spec(), 2025, ("January", "February", "March", "April", "May", "June"))
    assert "PUBDATETXT" in h1
    assert '"January 2025"' in h1
    assert '"June 2025"' in h1
    assert '"July 2025"' not in h1


# --- header tests ---

@responses.activate
def test_search_sends_required_headers():
    responses.add(responses.GET, BASE, json=_probe_response(0), status=200)
    a = _adapter(api_key="fake-key", inst_token="fake-token")
    list(a.search(_spec(), run_id="r1"))
    assert len(responses.calls) >= 1
    call = responses.calls[0].request
    assert call.headers.get("X-ELS-APIKey") == "fake-key"
    assert call.headers.get("X-ELS-Insttoken") == "fake-token"
    assert call.headers.get("Accept") == "application/json"


@responses.activate
def test_search_omits_insttoken_when_none():
    responses.add(responses.GET, BASE, json=_probe_response(0), status=200)
    a = _adapter(api_key="fake-key", inst_token=None)
    list(a.search(_spec(), run_id="r1"))
    call = responses.calls[0].request
    assert "X-ELS-Insttoken" not in call.headers


# --- offset-pagination tests ---

@responses.activate
def test_search_skips_empty_year():
    """A year with totalResults=0 produces just the probe call, no pagination."""
    responses.add(responses.GET, BASE, json=_probe_response(0), status=200)
    a = _adapter()
    recs = list(a.search(_spec(year_min=2024, year_max=2024), run_id="r1"))
    assert recs == []
    assert len(responses.calls) == 1


@responses.activate
def test_search_single_page_year():
    """A year with totalResults <= page size returns one page."""
    entry = {
        "dc:identifier": "SCOPUS_ID:85179000001",
        "dc:title": "ChatGPT in higher ed",
        "prism:doi": "10.1016/j.test.2024.001",
        "prism:coverDate": "2024-03-15",
        "prism:publicationName": "Journal of AI in Education",
        "dc:description": "Empirical study of ChatGPT use.",
        "subtype": "ar",
        "author": [{"surname": "Smith", "given-name": "John"}],
    }
    # First call: the probe (count=1)
    responses.add(responses.GET, BASE, json=_probe_response(1), status=200)
    # Second call: the page (count=25, start=0)
    responses.add(responses.GET, BASE, json=_page_response([entry], 1), status=200)

    recs = list(_adapter().search(_spec(year_min=2024, year_max=2024), run_id="r1"))
    assert len(recs) == 1
    assert recs[0].external_id == "SCOPUS_ID:85179000001"
    assert recs[0].doi == "10.1016/j.test.2024.001"
    assert recs[0].title == "ChatGPT in higher ed"
    assert recs[0].abstract == "Empirical study of ChatGPT use."
    assert recs[0].year == 2024
    assert recs[0].authors[0]["family"] == "Smith"
    assert recs[0].authors[0]["given"] == "John"


@responses.activate
def test_search_multi_page_year_walks_start_offsets():
    """A year that requires multiple pages walks start=0, 25, 50, ..."""
    # Total = 60, page size = 25 → expect probe + ceil(60/25) = 3 pages = 4 calls
    entries_page1 = [{"dc:identifier": f"SCOPUS_ID:{i}", "dc:title": "T", "prism:coverDate": "2024-01-01", "subtype": "ar"} for i in range(25)]
    entries_page2 = [{"dc:identifier": f"SCOPUS_ID:{i+25}", "dc:title": "T", "prism:coverDate": "2024-01-01", "subtype": "ar"} for i in range(25)]
    entries_page3 = [{"dc:identifier": f"SCOPUS_ID:{i+50}", "dc:title": "T", "prism:coverDate": "2024-01-01", "subtype": "ar"} for i in range(10)]
    responses.add(responses.GET, BASE, json=_probe_response(60), status=200)
    responses.add(responses.GET, BASE, json=_page_response(entries_page1, 60), status=200)
    responses.add(responses.GET, BASE, json=_page_response(entries_page2, 60), status=200)
    responses.add(responses.GET, BASE, json=_page_response(entries_page3, 60), status=200)

    recs = list(_adapter().search(_spec(year_min=2024, year_max=2024), run_id="r1"))
    assert len(recs) == 60
    # Verify start offsets in the pagination calls (skip probe = first call)
    start_offsets = []
    for call in responses.calls[1:]:
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(call.request.url).query)
        if "start" in qs:
            start_offsets.append(int(qs["start"][0]))
    assert start_offsets == [0, 25, 50]


@responses.activate
def test_search_splits_year_over_cap_into_halves():
    """A year with totalResults > OFFSET_CAP triggers two half-year sub-queries."""
    # Probe year 2025 → returns 10000 (over cap of 5000)
    responses.add(responses.GET, BASE, json=_probe_response(10000), status=200)
    # Probe H1 → returns 3000
    responses.add(responses.GET, BASE, json=_probe_response(3000), status=200)
    # H1 page: empty result (terminates pagination immediately)
    responses.add(responses.GET, BASE, json=_page_response([], 3000), status=200)
    # Probe H2 → returns 4000
    responses.add(responses.GET, BASE, json=_probe_response(4000), status=200)
    # H2 page: empty
    responses.add(responses.GET, BASE, json=_page_response([], 4000), status=200)

    list(_adapter().search(_spec(year_min=2025, year_max=2025), run_id="r1"))

    # 5 calls total: year-probe + H1-probe + H1-page + H2-probe + H2-page
    assert len(responses.calls) == 5
    # The 2nd call (H1 probe) should mention PUBDATETXT with January–June.
    h1_url = responses.calls[1].request.url
    assert "PUBDATETXT" in h1_url
    assert "January" in h1_url and "June" in h1_url
    # 4th call (H2 probe) should mention July–December.
    h2_url = responses.calls[3].request.url
    assert "PUBDATETXT" in h2_url
    assert "July" in h2_url and "December" in h2_url


# --- field-parsing tests ---

@responses.activate
def test_search_handles_missing_doi_and_abstract():
    entry = {
        "dc:identifier": "SCOPUS_ID:1",
        "dc:title": "T",
        "prism:coverDate": "2023-11-01",
        "subtype": "cp",
        # no prism:doi, no dc:description, no author
    }
    responses.add(responses.GET, BASE, json=_probe_response(1), status=200)
    responses.add(responses.GET, BASE, json=_page_response([entry], 1), status=200)
    recs = list(_adapter().search(_spec(year_min=2023, year_max=2023), run_id="r1"))
    assert len(recs) == 1
    assert recs[0].doi is None
    assert recs[0].abstract is None
    assert recs[0].authors == []


@responses.activate
def test_search_normalizes_doi_prefix():
    entry = {
        "dc:identifier": "SCOPUS_ID:1",
        "dc:title": "T",
        "prism:doi": "HTTPS://DOI.ORG/10.1016/ABC.123",
        "prism:coverDate": "2024-01-01",
        "subtype": "ar",
    }
    responses.add(responses.GET, BASE, json=_probe_response(1), status=200)
    responses.add(responses.GET, BASE, json=_page_response([entry], 1), status=200)
    rec = next(_adapter().search(_spec(year_min=2024, year_max=2024), run_id="r1"))
    assert rec.doi == "10.1016/abc.123"


@responses.activate
def test_search_stops_when_entries_empty_mid_pagination():
    """Defensive: if Scopus returns an empty entries array, stop paginating."""
    responses.add(responses.GET, BASE, json=_probe_response(100), status=200)
    responses.add(responses.GET, BASE, json=_page_response([], 100), status=200)
    a = _adapter()
    recs = list(a.search(_spec(year_min=2024, year_max=2024), run_id="r1"))
    assert recs == []
    assert len(responses.calls) == 2
