"""Shared HTTP session with retries, polite-pool User-Agent, and per-host rate limiting."""
from __future__ import annotations
import threading
import time
from collections import defaultdict
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from rrl import __version__

DEFAULT_TIMEOUT = 30
PDF_TIMEOUT = 60


def build_session(email: str, *, timeout: int = DEFAULT_TIMEOUT) -> requests.Session:
    """A requests.Session with retries and a polite-pool User-Agent."""
    sess = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("http://", adapter)
    sess.mount("https://", adapter)
    sess.headers["User-Agent"] = f"rrl-pipeline/{__version__} (mailto:{email})"
    sess.request = _with_default_timeout(sess.request, timeout)  # type: ignore[assignment]
    return sess


def _with_default_timeout(orig, default):
    def wrapped(method, url, **kw):
        kw.setdefault("timeout", default)
        return orig(method, url, **kw)
    return wrapped


class RateLimitedSession:
    """Wraps a requests.Session and enforces per-host token bucket pacing."""

    def __init__(self, session: requests.Session, requests_per_second: float):
        self.session = session
        self.min_interval = 1.0 / requests_per_second
        self._last_call: dict[str, float] = defaultdict(float)
        self._lock = threading.Lock()

    def _acquire(self, host: str) -> None:
        with self._lock:
            now = time.monotonic()
            wait = self._last_call[host] + self.min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_call[host] = time.monotonic()

    def get(self, url: str, **kw):
        host = urlparse(url).netloc
        self._acquire(host)
        return self.session.get(url, **kw)
