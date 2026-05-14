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
