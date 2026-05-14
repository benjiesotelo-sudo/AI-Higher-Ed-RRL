import time
import responses
from rrl import __version__
from rrl.http import build_session, RateLimitedSession


@responses.activate
def test_session_sets_user_agent():
    responses.add(responses.GET, "https://example.com/", json={"ok": True}, status=200)
    sess = build_session(email="test@example.com")
    r = sess.get("https://example.com/")
    assert r.status_code == 200
    ua = responses.calls[0].request.headers["User-Agent"]
    assert "rrl-pipeline" in ua
    assert __version__ in ua
    assert "test@example.com" in ua


@responses.activate
def test_session_retries_on_5xx():
    responses.add(responses.GET, "https://example.com/x", status=503)
    responses.add(responses.GET, "https://example.com/x", status=503)
    responses.add(responses.GET, "https://example.com/x", json={"ok": True}, status=200)
    sess = build_session(email="t@e.com")
    r = sess.get("https://example.com/x")
    assert r.status_code == 200
    assert len(responses.calls) == 3


def test_rate_limited_session_paces_requests():
    sess = RateLimitedSession(build_session(email="t@e.com"), requests_per_second=10)
    t0 = time.monotonic()
    sess._acquire("example.com")
    sess._acquire("example.com")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.09
