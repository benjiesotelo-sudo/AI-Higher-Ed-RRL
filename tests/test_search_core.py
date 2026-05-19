import responses
from rrl.http import build_session
from rrl.search.core_api import find_pdf_by_doi, find_pdf_by_title

@responses.activate
def test_find_pdf_by_doi_returns_url():
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  json={"results": [{"downloadUrl": "https://core.ac.uk/a.pdf"}]}, status=200)
    url = find_pdf_by_doi(build_session("t@e.com"), "10.1/aaa", api_key="KEY")
    assert url == "https://core.ac.uk/a.pdf"

@responses.activate
def test_find_pdf_by_title_returns_first_hit():
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  json={"results": [{"downloadUrl": "https://core.ac.uk/b.pdf"}]}, status=200)
    url = find_pdf_by_title(build_session("t@e.com"), "ChatGPT in higher ed", api_key="KEY")
    assert url == "https://core.ac.uk/b.pdf"

@responses.activate
def test_find_returns_none_when_no_results():
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  json={"results": []}, status=200)
    assert find_pdf_by_doi(build_session("t@e.com"), "10.1/x", api_key="KEY") is None


# --- Phase-6 hardening: CORE failures must NOT bubble out and crash export ---

@responses.activate
def test_find_pdf_by_doi_returns_none_on_429():
    """A 429 from CORE means rate-limited — return None, don't raise."""
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  status=429, json={"message": "rate limit"})
    assert find_pdf_by_doi(build_session("t@e.com"), "10.1/x", api_key="KEY") is None


@responses.activate
def test_find_pdf_by_doi_returns_none_on_500():
    """Any 5xx from CORE → None, no exception."""
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  status=500, json={})
    assert find_pdf_by_doi(build_session("t@e.com"), "10.1/x", api_key="KEY") is None


@responses.activate
def test_find_pdf_by_title_returns_none_on_429():
    responses.add(responses.GET, "https://api.core.ac.uk/v3/search/works",
                  status=429, json={"message": "rate limit"})
    assert find_pdf_by_title(build_session("t@e.com"), "T", api_key="KEY") is None
