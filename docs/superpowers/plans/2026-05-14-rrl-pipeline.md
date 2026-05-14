# AI in Higher Education RRL Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI pipeline that harvests, dedupes, enriches, screens, downloads, and exports an OA corpus of academic papers on AI/GenAI/LLM adoption in higher education.

**Architecture:** Staged CLI (harvest → dedup → enrich → screen → export). State persists in SQLite. Each stage is idempotent and resumable. Source modules organized by stage. Tests use `pytest` with `responses` for HTTP mocking and fixture JSON for canned API payloads.

**Tech Stack:** Python 3.11+, click, requests + urllib3.Retry, openpyxl, structlog, rapidfuzz, langdetect, SQLite (WAL mode, raw SQL, no ORM). Dev: pytest, responses, ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-05-14-rrl-pipeline-design.md` is the source of truth. If anything in this plan conflicts with the spec, the spec wins.

**Conventions:**
- After every task: `pytest -q` must pass, then commit. Commit message format: `feat: <module>` / `test: <module>` / `chore: <thing>`.
- Source under `rrl/`, tests under `tests/` mirroring the source tree.
- Type hints required on every public function.
- No `print()`; use the configured logger.

---

## Task 1: Project scaffold

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `README.md` (skeleton with markers)
- Create: `rrl/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "rrl"
version = "0.1.0"
description = "AI in Higher Education RRL collection pipeline"
requires-python = ">=3.11"
dependencies = [
  "click>=8.1",
  "requests>=2.31",
  "urllib3>=2.0",
  "openpyxl>=3.1",
  "structlog>=24.1",
  "rapidfuzz>=3.5",
  "langdetect>=1.0",
  "pyyaml>=6.0",
  "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov", "responses>=0.25", "ruff", "mypy"]

[project.scripts]
rrl = "rrl.cli:main"

[tool.setuptools.packages.find]
include = ["rrl*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] **Step 2: Write `.env.example`**

```
# Required for OpenAlex polite pool + Unpaywall
OPENALEX_EMAIL=your-email@example.com

# Optional: enables faster S2 harvests (5 req/s vs 1 req/s)
# Get a free key at https://www.semanticscholar.org/product/api
SEMANTIC_SCHOLAR_API_KEY=

# Optional: only needed if CORE fallback is triggered
# Get a free key at https://core.ac.uk/services/api
CORE_API_KEY=
```

- [ ] **Step 3: Write `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
.ruff_cache/
.mypy_cache/
data/
pdfs/
logs/
output/run_manifest_*.json
*.egg-info/
.coverage
```

- [ ] **Step 4: Write `README.md` skeleton with required markers**

```markdown
# AI in Higher Education RRL Pipeline

A Python CLI that harvests, dedupes, screens, and downloads open-access academic papers on AI / GenAI / ChatGPT / LLM adoption in higher education.

## Scope

**Included:** faculty using LLMs to teach; students using AI for coursework; institutional policy/governance; AI-literacy programs that teach students to use AI.

**Excluded:** K-12-only contexts; AI/ML as a CS subject; closed-access papers (corpus is OA-only).

**Date range:** 2020–2026. Papers are tagged `pre_chatgpt` (≤2022) or `post_chatgpt` (≥2023).

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -e .[dev]`
3. `cp .env.example .env` and fill in `OPENALEX_EMAIL`.
4. **Strongly recommended:** add `SEMANTIC_SCHOLAR_API_KEY`. Without it, S2 throttles to 1 req/s — an 8–15k record harvest takes 3–4 hours just for S2. With a free key, it drops to ~30 minutes.
5. Optional: `CORE_API_KEY` for PDF fallback.

## Usage

```
rrl harvest      # search OpenAlex + ERIC + S2
rrl dedup        # build canonical paper rows
rrl enrich       # DOAJ + Unpaywall + OpenAlex flags
rrl screen       # topic / OA / quality filtering
rrl export       # download PDFs, write xlsx, update README appendix
rrl all          # run all stages, resumable
rrl status       # show progress
```

## Limitations

1. OA-only corpus — significant closed-access literature is missing.
2. Topic boundary is regex-based; `review_needed` tier surfaces borderline papers for manual judgment.
3. Predatory-venue detection is best-effort (DOAJ + tiny blocklist).
4. Dedup has known gaps — preprint/journal pairs without shared DOIs may both appear; `rrl dedup --review` surfaces likely duplicates.
5. No content extraction (methods/findings columns intentionally absent).
6. English-only.

<!-- BEGIN AUTO-GENERATED -->
_Auto-generated section. Populated by `rrl export`._
<!-- END AUTO-GENERATED -->
```

- [ ] **Step 5: Write `rrl/__init__.py`**

```python
__version__ = "0.1.0"
```

- [ ] **Step 6: Write `tests/__init__.py`** (empty file)

- [ ] **Step 7: Write `tests/conftest.py`**

```python
from pathlib import Path
import pytest

FIXTURES = Path(__file__).parent / "fixtures"

@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES
```

- [ ] **Step 8: Verify install + smoke test**

Run: `pip install -e .[dev] && pytest -q`
Expected: install succeeds, `pytest` reports `no tests ran` (exit 0).

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml .env.example .gitignore README.md rrl/ tests/
git commit -m "chore: project scaffold"
```

---

## Task 2: DB module

**Files:**
- Create: `rrl/db.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_db.py
from pathlib import Path
from rrl.db import connect, init_schema, SCHEMA_VERSION

def test_init_schema_creates_all_tables(tmp_path: Path):
    db_path = tmp_path / "rrl.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = {r[0] for r in cur.fetchall()}
    assert tables >= {
        "search_runs", "raw_records", "papers", "paper_sources",
        "pdf_attempts", "paper_merges", "schema_version",
    }
    v = conn.execute("SELECT version FROM schema_version").fetchone()[0]
    assert v == SCHEMA_VERSION

def test_init_schema_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "rrl.sqlite"
    conn = connect(db_path)
    init_schema(conn)
    init_schema(conn)  # second call must not error
    count = conn.execute("SELECT COUNT(*) FROM schema_version").fetchone()[0]
    assert count == 1

def test_wal_mode_enabled(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite")
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL (ModuleNotFoundError: `rrl.db`).

- [ ] **Step 3: Implement `rrl/db.py`**

```python
"""SQLite connection + schema setup. Raw SQL; no ORM."""
from __future__ import annotations
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS search_runs (
  run_id          TEXT PRIMARY KEY,
  adapter         TEXT NOT NULL,
  query_hash      TEXT NOT NULL,
  query_payload   TEXT NOT NULL,
  started_at      TEXT NOT NULL,
  finished_at     TEXT,
  status          TEXT NOT NULL,
  records_found   INTEGER,
  records_new     INTEGER,
  error_message   TEXT,
  cursor_state    TEXT
);

CREATE TABLE IF NOT EXISTS raw_records (
  raw_id          INTEGER PRIMARY KEY,
  run_id          TEXT NOT NULL REFERENCES search_runs(run_id),
  adapter         TEXT NOT NULL,
  external_id     TEXT NOT NULL,
  doi             TEXT,
  title           TEXT,
  title_norm      TEXT,
  authors_json    TEXT,
  first_author    TEXT,
  year            INTEGER,
  venue           TEXT,
  abstract        TEXT,
  language        TEXT,
  raw_payload     TEXT NOT NULL,
  fetched_at      TEXT NOT NULL,
  UNIQUE (adapter, external_id)
);
CREATE INDEX IF NOT EXISTS idx_raw_doi     ON raw_records(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_raw_titleyr ON raw_records(title_norm, year, first_author);

CREATE TABLE IF NOT EXISTS papers (
  paper_id            TEXT PRIMARY KEY,
  doi                 TEXT UNIQUE,
  title               TEXT NOT NULL,
  authors_json        TEXT NOT NULL,
  year                INTEGER NOT NULL,
  era_tag             TEXT,
  venue               TEXT,
  publisher           TEXT,
  work_type           TEXT,
  language            TEXT,
  abstract            TEXT,
  citation_count      INTEGER,
  is_in_doaj          INTEGER,
  is_peer_reviewed    INTEGER,
  is_oa               INTEGER,
  oa_status           TEXT,
  oa_pdf_url          TEXT,
  included            INTEGER,
  exclusion_reason    TEXT,
  quality_tier        TEXT,
  topic_match_score   REAL,
  pdf_filename        TEXT,
  pdf_status          TEXT,
  first_seen_at       TEXT NOT NULL,
  last_updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_papers_year     ON papers(year);
CREATE INDEX IF NOT EXISTS idx_papers_included ON papers(included);
CREATE INDEX IF NOT EXISTS idx_papers_tier     ON papers(quality_tier);

CREATE TABLE IF NOT EXISTS paper_sources (
  paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
  raw_id          INTEGER NOT NULL REFERENCES raw_records(raw_id),
  PRIMARY KEY (paper_id, raw_id)
);
CREATE INDEX IF NOT EXISTS idx_paper_sources_raw ON paper_sources(raw_id);

CREATE TABLE IF NOT EXISTS pdf_attempts (
  attempt_id      INTEGER PRIMARY KEY,
  paper_id        TEXT NOT NULL REFERENCES papers(paper_id),
  source          TEXT NOT NULL,
  url             TEXT NOT NULL,
  http_status     INTEGER,
  content_type    TEXT,
  bytes_received  INTEGER,
  outcome         TEXT NOT NULL,
  error_message   TEXT,
  attempted_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_merges (
  loser_id        TEXT PRIMARY KEY REFERENCES papers(paper_id),
  winner_id       TEXT NOT NULL REFERENCES papers(paper_id),
  merged_at       TEXT NOT NULL,
  merged_by       TEXT NOT NULL
);
"""

def connect(db_path: Path | str) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and foreign keys on."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn

def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indices if missing. Idempotent."""
    from datetime import datetime, timezone
    conn.executescript(DDL)
    existing = conn.execute(
        "SELECT version FROM schema_version WHERE version=?", (SCHEMA_VERSION,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_db.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/db.py tests/test_db.py
git commit -m "feat: db module with schema + WAL connection"
```

---

## Task 3: Config module

**Files:**
- Create: `rrl/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from rrl.config import (
    AI_TERMS, HE_TERMS, K12_TERMS,
    YEAR_MIN, YEAR_MAX,
    PREDATORY_BLOCKLIST, ACADEMIC_PRESS_ALLOWLIST,
    RATE_PLANS, Settings,
)
import os

def test_term_lists_nonempty():
    assert len(AI_TERMS) >= 10
    assert len(HE_TERMS) >= 10
    assert len(K12_TERMS) >= 5
    assert "ChatGPT" in AI_TERMS
    assert "higher education" in HE_TERMS
    assert "AI" not in AI_TERMS  # bare AI excluded — too noisy

def test_year_range():
    assert YEAR_MIN == 2020
    assert YEAR_MAX == 2026

def test_blocklist_and_allowlist():
    assert len(PREDATORY_BLOCKLIST) >= 5
    assert len(ACADEMIC_PRESS_ALLOWLIST) >= 8
    assert "Springer" in ACADEMIC_PRESS_ALLOWLIST

def test_rate_plans_for_required_adapters():
    for adapter in ("openalex", "eric", "s2", "crossref", "core", "doaj", "unpaywall"):
        assert adapter in RATE_PLANS
        assert RATE_PLANS[adapter]["requests_per_second"] > 0

def test_settings_requires_openalex_email(monkeypatch):
    monkeypatch.delenv("OPENALEX_EMAIL", raising=False)
    try:
        Settings.from_env()
    except RuntimeError as e:
        assert "OPENALEX_EMAIL" in str(e)
    else:
        raise AssertionError("expected RuntimeError")

def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("OPENALEX_EMAIL", "test@example.com")
    monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "abc123")
    s = Settings.from_env()
    assert s.openalex_email == "test@example.com"
    assert s.s2_api_key == "abc123"
    assert s.core_api_key is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `rrl/config.py`**

```python
"""Configuration: term lists, blocklists, rate plans, env-loaded settings."""
from __future__ import annotations
import os
from dataclasses import dataclass

AI_TERMS = [
    "artificial intelligence",
    "generative AI", "generative artificial intelligence", "GenAI",
    "ChatGPT", "GPT-3", "GPT-3.5", "GPT-4", "GPT-4o",
    "large language model", "LLM", "LLMs",
    "Bard", "Gemini", "Claude", "Copilot",
]

HE_TERMS = [
    "higher education", "university", "universities",
    "college", "colleges", "undergraduate", "postgraduate",
    "graduate student", "tertiary education",
    "faculty", "professor", "instructor", "lecturer", "academia",
]

K12_TERMS = [
    "K-12", "K12", "kindergarten",
    "elementary school", "primary school",
    "secondary school", "high school", "middle school",
]

YEAR_MIN = 2020
YEAR_MAX = 2026

PREDATORY_BLOCKLIST = {
    "OMICS International", "OMICS Publishing Group", "Bentham Open",
    "Bentham Science Publishers", "SCIRP", "Scientific Research Publishing",
    "Hindawi Limited", "Academic Journals", "International Journal of Advanced Research",
    "IISTE", "International Institute for Science, Technology and Education",
}

ACADEMIC_PRESS_ALLOWLIST = {
    "Springer", "Springer Nature", "Routledge", "Cambridge University Press",
    "Oxford University Press", "MIT Press", "Elsevier", "Wiley",
    "Palgrave Macmillan", "Taylor & Francis", "Sage", "SAGE Publications",
}

RATE_PLANS: dict[str, dict] = {
    "openalex":   {"requests_per_second": 10, "per_page": 200},
    "eric":       {"requests_per_second": 1,  "per_page": 2000},
    "s2":         {"requests_per_second": 1,  "per_page": 100, "with_key_rps": 5},
    "crossref":   {"requests_per_second": 50, "per_page": 100},
    "core":       {"requests_per_second": 0.17, "per_page": 100},  # 10/min
    "doaj":       {"requests_per_second": 2,  "per_page": 1},
    "unpaywall":  {"requests_per_second": 10, "per_page": 1},
}

@dataclass(frozen=True)
class Settings:
    openalex_email: str
    s2_api_key: str | None
    core_api_key: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        email = os.environ.get("OPENALEX_EMAIL", "").strip()
        if not email:
            raise RuntimeError(
                "OPENALEX_EMAIL is required (used in User-Agent for OpenAlex and as the "
                "email param for Unpaywall). Set it in .env."
            )
        s2 = os.environ.get("SEMANTIC_SCHOLAR_API_KEY", "").strip() or None
        core = os.environ.get("CORE_API_KEY", "").strip() or None
        return cls(openalex_email=email, s2_api_key=s2, core_api_key=core)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_config.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/config.py tests/test_config.py
git commit -m "feat: config with term lists, blocklists, rate plans, env settings"
```

---

## Task 4: HTTP layer (rate-limited session)

**Files:**
- Create: `rrl/http.py`
- Create: `tests/test_http.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_http.py
import time
import pytest
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
    # Two consecutive calls to the same host must be at least 0.1s apart.
    t0 = time.monotonic()
    sess._acquire("example.com")
    sess._acquire("example.com")
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.09  # small tolerance
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_http.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `rrl/http.py`**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_http.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/http.py tests/test_http.py
git commit -m "feat: rate-limited HTTP session with retries + polite-pool UA"
```

---

## Task 5: Logging setup

**Files:**
- Create: `rrl/logging_setup.py`
- Create: `tests/test_logging_setup.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logging_setup.py
import json
from pathlib import Path
from rrl.logging_setup import configure_logging, get_logger

def test_logging_writes_jsonl(tmp_path: Path):
    log_dir = tmp_path / "logs"
    configure_logging(stage="harvest", log_dir=log_dir, console=False)
    log = get_logger()
    log.info("query_sent", adapter="openalex", page=1)
    files = list(log_dir.glob("harvest-*.jsonl"))
    assert len(files) == 1
    line = files[0].read_text().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["event"] == "query_sent"
    assert rec["adapter"] == "openalex"
    assert rec["page"] == 1
    assert rec["stage"] == "harvest"
    assert "ts" in rec
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_logging_setup.py -v`
Expected: FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement `rrl/logging_setup.py`**

```python
"""structlog config: JSON-lines to logs/<stage>-YYYY-MM-DD.jsonl + optional console."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path

import structlog

def configure_logging(stage: str, log_dir: Path, *, console: bool = True) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = log_dir / f"{stage}-{today}.jsonl"

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(message)s"))

    handlers: list[logging.Handler] = [file_handler]
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter("%(message)s"))
        handlers.append(console_handler)

    root = logging.getLogger()
    root.handlers.clear()
    for h in handlers:
        root.addHandler(h)
    root.setLevel(logging.INFO)

    def _add_ts(_, __, event_dict):
        event_dict["ts"] = datetime.now(timezone.utc).isoformat()
        event_dict["stage"] = stage
        return event_dict

    structlog.configure(
        processors=[
            _add_ts,
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

def get_logger():
    return structlog.get_logger()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_logging_setup.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/logging_setup.py tests/test_logging_setup.py
git commit -m "feat: structlog setup with per-stage JSONL files"
```

---

## Task 6: CLI skeleton

**Files:**
- Create: `rrl/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli.py
from click.testing import CliRunner
from rrl.cli import main

def test_help_lists_commands():
    r = CliRunner().invoke(main, ["--help"])
    assert r.exit_code == 0
    for cmd in ("harvest", "dedup", "enrich", "screen", "export", "all", "status"):
        assert cmd in r.output

def test_each_command_has_help():
    runner = CliRunner()
    for cmd in ("harvest", "dedup", "enrich", "screen", "export", "all", "status"):
        r = runner.invoke(main, [cmd, "--help"])
        assert r.exit_code == 0, f"{cmd} --help failed: {r.output}"

def test_status_runs_without_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    r = CliRunner().invoke(main, ["status"])
    # Should not crash even when DB doesn't exist yet.
    assert r.exit_code in (0, 2)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/cli.py`** (stubs only; stages wired in later tasks)

```python
"""rrl CLI entrypoint. Stages are wired in later tasks; this is the skeleton."""
from __future__ import annotations
from pathlib import Path

import click
from dotenv import load_dotenv

DEFAULT_DB = Path("data/rrl.sqlite")
DEFAULT_LOG_DIR = Path("logs")

@click.group()
@click.option("--db", type=click.Path(path_type=Path), default=DEFAULT_DB, show_default=True)
@click.option("--verbose", "-v", is_flag=True)
@click.pass_context
def main(ctx: click.Context, db: Path, verbose: bool) -> None:
    """RRL pipeline for AI-in-higher-ed literature."""
    load_dotenv()
    ctx.ensure_object(dict)
    ctx.obj["db"] = db
    ctx.obj["verbose"] = verbose

@main.command()
@click.option("--only", default=None, help="Comma-separated adapter names")
@click.option("--since", default=None, help="YYYY-MM-DD; harvest only papers since this date")
@click.pass_context
def harvest(ctx, only, since):
    """Search OpenAlex / ERIC / Semantic Scholar; persist raw_records."""
    click.echo("harvest: not yet implemented")  # wired in Task 11
    raise click.exceptions.Exit(2)

@main.command()
@click.option("--review", is_flag=True, help="Write data/dedup_review.csv")
@click.option("--merge", nargs=2, type=str, default=None, metavar="LOSER WINNER")
@click.pass_context
def dedup(ctx, review, merge):
    """Build canonical papers from raw_records."""
    click.echo("dedup: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command()
@click.option("--only", default=None, help="doaj|unpaywall|openalex")
@click.pass_context
def enrich(ctx, only):
    """Attach DOAJ + Unpaywall + OpenAlex quality flags."""
    click.echo("enrich: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command()
@click.option("--dry-run", is_flag=True)
@click.pass_context
def screen(ctx, dry_run):
    """Apply topic/OA/quality filters; assign tier and era."""
    click.echo("screen: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command()
@click.option("--retry-failed", is_flag=True)
@click.pass_context
def export(ctx, retry_failed):
    """Download PDFs, write xlsx + manifest, update README appendix."""
    click.echo("export: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command(name="all")
@click.option("--skip", default=None, help="Comma-separated stage names to skip")
@click.pass_context
def run_all(ctx, skip):
    """Run all stages in order; resumable."""
    click.echo("all: not yet implemented")
    raise click.exceptions.Exit(2)

@main.command()
@click.option("--paper", default=None, help="Show full lifecycle of one paper_id")
@click.pass_context
def status(ctx, paper):
    """Show per-stage counts and last-run timestamps."""
    db: Path = ctx.obj["db"]
    if not db.exists():
        click.echo(f"No database at {db}. Run `rrl harvest` to create it.")
        return
    click.echo(f"DB: {db}")  # full implementation in Task 27
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/cli.py tests/test_cli.py
git commit -m "feat: CLI skeleton with stub subcommands"
```

---

## Task 7: Search base (Protocol, dataclasses, normalizers)

**Files:**
- Create: `rrl/search/__init__.py`
- Create: `rrl/search/base.py`
- Create: `tests/test_search_base.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_base.py
from rrl.search.base import (
    QuerySpec, RawRecord,
    normalize_doi, normalize_title, normalize_author_name, query_hash,
)

def test_normalize_doi_strips_url_prefix_and_lowercases():
    assert normalize_doi("https://doi.org/10.1234/AbC") == "10.1234/abc"
    assert normalize_doi("doi:10.1234/AbC") == "10.1234/abc"
    assert normalize_doi("10.1234/abc.") == "10.1234/abc"
    assert normalize_doi(None) is None
    assert normalize_doi("") is None

def test_normalize_title_strips_punct_and_stopwords():
    a = normalize_title("The Use of ChatGPT in Higher Education!")
    b = normalize_title("Use of ChatGPT in Higher Education")
    assert a == b
    assert "the" not in a.split()

def test_normalize_title_strips_diacritics():
    assert normalize_title("Café Pédagogique") == normalize_title("Cafe Pedagogique")

def test_normalize_author_name_lowercases_and_strips():
    assert normalize_author_name("García-Márquez") == normalize_author_name("Garcia Marquez")
    assert normalize_author_name("  O'Brien  ") == "obrien"

def test_query_hash_is_deterministic():
    q1 = QuerySpec(ai_terms=["a", "b"], he_terms=["c"], year_min=2020, year_max=2026)
    q2 = QuerySpec(ai_terms=["a", "b"], he_terms=["c"], year_min=2020, year_max=2026)
    assert query_hash(q1) == query_hash(q2)
    q3 = QuerySpec(ai_terms=["b", "a"], he_terms=["c"], year_min=2020, year_max=2026)
    assert query_hash(q1) == query_hash(q3)  # order-independent

def test_rawrecord_construction():
    r = RawRecord(
        external_id="W1", doi="10.1/x", title="T", authors=[{"family": "Smith"}],
        year=2023, venue="J", abstract="A", language="en", raw_payload={"_": 1},
    )
    assert r.external_id == "W1"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_search_base.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/search/__init__.py`** (empty file).

- [ ] **Step 4: Implement `rrl/search/base.py`**

```python
"""Shared types and normalization helpers for search adapters."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterator, Protocol

STOPWORDS = {"the", "a", "an", "of", "for", "and", "to", "in", "on", "with"}

@dataclass(frozen=True)
class QuerySpec:
    ai_terms: list[str]
    he_terms: list[str]
    year_min: int
    year_max: int
    language: str = "en"

@dataclass(frozen=True)
class RawRecord:
    external_id: str
    doi: str | None
    title: str
    authors: list[dict]  # [{"family": ..., "given": ..., "orcid": ...}]
    year: int | None
    venue: str | None
    abstract: str | None
    language: str | None
    raw_payload: dict = field(default_factory=dict)

class SearchAdapter(Protocol):
    name: str
    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]: ...

# ── Normalizers ─────────────────────────────────────────────────────────────

_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.IGNORECASE)
_NON_ALNUM = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")

def _strip_diacritics(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))

def normalize_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    d = _DOI_PREFIX.sub("", doi.strip()).lower().rstrip(".,;")
    return d or None

def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    t = _strip_diacritics(title).lower()
    t = _NON_ALNUM.sub(" ", t)
    t = _WS.sub(" ", t).strip()
    return " ".join(w for w in t.split() if w not in STOPWORDS)

def normalize_author_name(name: str | None) -> str:
    if not name:
        return ""
    n = _strip_diacritics(name).lower()
    n = re.sub(r"[^a-z]+", "", n)
    return n

def query_hash(q: QuerySpec) -> str:
    payload = json.dumps({
        "ai_terms": sorted(q.ai_terms),
        "he_terms": sorted(q.he_terms),
        "year_min": q.year_min,
        "year_max": q.year_max,
        "language": q.language,
    }, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_search_base.py -v`
Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/search/ tests/test_search_base.py
git commit -m "feat: search base protocol + normalizers (DOI, title, author, query hash)"
```

---

## Task 8: OpenAlex adapter

**Files:**
- Create: `rrl/search/openalex.py`
- Create: `tests/fixtures/openalex_page1.json`
- Create: `tests/fixtures/openalex_page2.json`
- Create: `tests/test_search_openalex.py`

- [ ] **Step 1: Create fixture `tests/fixtures/openalex_page1.json`**

```json
{
  "meta": {"count": 3, "next_cursor": "CURSOR2", "per_page": 200},
  "results": [
    {
      "id": "https://openalex.org/W111",
      "doi": "https://doi.org/10.1/aaa",
      "title": "ChatGPT in undergraduate writing courses",
      "publication_year": 2023,
      "language": "en",
      "type": "journal-article",
      "cited_by_count": 12,
      "authorships": [{"author": {"display_name": "Jane Smith"}, "raw_author_name": "Jane Smith"}],
      "primary_location": {"source": {"display_name": "J. Higher Ed", "host_organization_name": "Springer", "issn_l": "1234-5678", "type": "journal", "is_in_doaj": false}},
      "open_access": {"is_oa": true, "oa_status": "gold"},
      "best_oa_location": {"pdf_url": "https://example.com/a.pdf"},
      "abstract_inverted_index": {"ChatGPT": [0], "in": [1], "education": [2]}
    },
    {
      "id": "https://openalex.org/W222",
      "doi": null,
      "title": "Faculty attitudes toward LLMs",
      "publication_year": 2024,
      "language": "en",
      "type": "journal-article",
      "cited_by_count": 4,
      "authorships": [{"author": {"display_name": "Alex Doe"}, "raw_author_name": "Alex Doe"}],
      "primary_location": {"source": {"display_name": "Univ. Review", "type": "journal"}},
      "open_access": {"is_oa": false, "oa_status": "closed"},
      "abstract_inverted_index": null
    }
  ]
}
```

- [ ] **Step 2: Create fixture `tests/fixtures/openalex_page2.json`**

```json
{
  "meta": {"count": 3, "next_cursor": null, "per_page": 200},
  "results": [
    {
      "id": "https://openalex.org/W333",
      "doi": "https://doi.org/10.1/ccc",
      "title": "Generative AI policy in universities",
      "publication_year": 2025,
      "language": "en",
      "type": "review",
      "cited_by_count": 0,
      "authorships": [{"author": {"display_name": "Pat Lee"}, "raw_author_name": "Pat Lee"}],
      "primary_location": {"source": {"display_name": "Higher Ed Policy", "type": "journal"}},
      "open_access": {"is_oa": true, "oa_status": "bronze"},
      "best_oa_location": {"pdf_url": "https://example.com/c.pdf"},
      "abstract_inverted_index": {"policy": [0]}
    }
  ]
}
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_search_openalex.py
import json
import responses
from rrl.http import build_session
from rrl.search.base import QuerySpec
from rrl.search.openalex import OpenAlexAdapter

def _spec():
    return QuerySpec(ai_terms=["ChatGPT", "LLM"], he_terms=["university"], year_min=2020, year_max=2026)

def test_render_query_contains_filters():
    a = OpenAlexAdapter(session=build_session("t@e.com"), email="t@e.com")
    q = a._render_filter(_spec())
    assert "from_publication_date:2020-01-01" in q
    assert "language:en" in q
    assert "abstract.search" in q
    assert "ChatGPT" in q

@responses.activate
def test_search_paginates_and_yields_records(fixtures_dir):
    p1 = json.loads((fixtures_dir / "openalex_page1.json").read_text())
    p2 = json.loads((fixtures_dir / "openalex_page2.json").read_text())
    responses.add(responses.GET, "https://api.openalex.org/works", json=p1, status=200)
    responses.add(responses.GET, "https://api.openalex.org/works", json=p2, status=200)
    a = OpenAlexAdapter(session=build_session("t@e.com"), email="t@e.com")
    recs = list(a.search(_spec(), run_id="r1"))
    assert len(recs) == 3
    ids = [r.external_id for r in recs]
    assert ids == ["W111", "W222", "W333"]
    assert recs[0].doi == "10.1/aaa"
    assert recs[0].title.startswith("ChatGPT")
    assert recs[0].abstract == "ChatGPT in education"
    assert recs[0].authors[0]["family"] == "Smith"

@responses.activate
def test_search_handles_missing_abstract_index():
    p = {"meta": {"count": 1, "next_cursor": None}, "results": [{
        "id": "https://openalex.org/W1", "doi": None, "title": "T",
        "publication_year": 2023, "language": "en", "type": "journal-article",
        "cited_by_count": 0, "authorships": [], "primary_location": {"source": {}},
        "open_access": {"is_oa": False}, "abstract_inverted_index": None,
    }]}
    responses.add(responses.GET, "https://api.openalex.org/works", json=p, status=200)
    a = OpenAlexAdapter(session=build_session("t@e.com"), email="t@e.com")
    recs = list(a.search(_spec(), run_id="r1"))
    assert recs[0].abstract is None
```

- [ ] **Step 4: Run test to verify failure**

Run: `pytest tests/test_search_openalex.py -v`
Expected: FAIL.

- [ ] **Step 5: Implement `rrl/search/openalex.py`**

```python
"""OpenAlex adapter — primary search source."""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord, SearchAdapter, normalize_doi

BASE = "https://api.openalex.org/works"
WORK_TYPES = ("journal-article", "book-chapter", "proceedings-article", "review")

def _decode_abstract(inverted: dict | None) -> str | None:
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, ixs in inverted.items():
        for i in ixs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions) or None

def _author_dict(authorship: dict) -> dict:
    name = authorship.get("raw_author_name") or authorship.get("author", {}).get("display_name") or ""
    parts = name.rsplit(" ", 1)
    if len(parts) == 2:
        given, family = parts
    else:
        given, family = "", name
    return {"family": family, "given": given, "orcid": authorship.get("author", {}).get("orcid")}

class OpenAlexAdapter:
    name = "openalex"

    def __init__(self, session: requests.Session, email: str):
        self.session = session
        self.email = email

    def _render_filter(self, q: QuerySpec) -> str:
        ai = "|".join(q.ai_terms)
        he = "|".join(q.he_terms)
        parts = [
            f"abstract.search:{ai}",
            f"abstract.search:{he}",
            f"from_publication_date:{q.year_min}-01-01",
            f"to_publication_date:{q.year_max}-12-31",
            f"language:{q.language}",
            "type:" + "|".join(WORK_TYPES),
        ]
        return ",".join(parts)

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        cursor: str | None = "*"
        params = {
            "filter": self._render_filter(q),
            "per-page": 200,
            "mailto": self.email,
        }
        while cursor:
            params["cursor"] = cursor
            r = self.session.get(BASE, params=params)
            r.raise_for_status()
            payload = r.json()
            for w in payload.get("results", []):
                yield self._parse(w)
            cursor = payload.get("meta", {}).get("next_cursor")

    def _parse(self, w: dict) -> RawRecord:
        ext_id = w["id"].rsplit("/", 1)[-1]
        return RawRecord(
            external_id=ext_id,
            doi=normalize_doi(w.get("doi")),
            title=w.get("title") or "",
            authors=[_author_dict(a) for a in w.get("authorships", [])],
            year=w.get("publication_year"),
            venue=(w.get("primary_location") or {}).get("source", {}).get("display_name"),
            abstract=_decode_abstract(w.get("abstract_inverted_index")),
            language=w.get("language"),
            raw_payload=w,
        )
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_search_openalex.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add rrl/search/openalex.py tests/fixtures/openalex_*.json tests/test_search_openalex.py
git commit -m "feat: OpenAlex search adapter with cursor pagination + abstract inversion"
```

---

## Task 9: ERIC adapter

**Files:**
- Create: `rrl/search/eric.py`
- Create: `tests/fixtures/eric_response.json`
- Create: `tests/test_search_eric.py`

- [ ] **Step 1: Create fixture `tests/fixtures/eric_response.json`**

```json
{
  "response": {
    "numFound": 2,
    "start": 0,
    "docs": [
      {
        "id": "EJ100001",
        "title": ["Higher education adoption of generative AI"],
        "author": ["Smith, J.", "Doe, A."],
        "publicationdateyear": 2024,
        "description": ["A study of faculty perceptions of ChatGPT."],
        "publisher": ["Journal of Higher Ed"],
        "issn": ["1234-5678"],
        "language": ["English"]
      },
      {
        "id": "ED600001",
        "title": ["AI literacy programs in colleges"],
        "author": ["Lee, P."],
        "publicationdateyear": 2025,
        "description": ["A program report on AI literacy."],
        "publisher": ["ERIC"],
        "language": ["English"]
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_search_eric.py
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
    # First call returns the records; second call returns 0 records => loop exits.
    empty = {"response": {"numFound": 2, "start": 2000, "docs": []}}
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=payload, status=200)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=empty, status=200)
    a = ERICAdapter(session=build_session("t@e.com"))
    recs = list(a.search(_spec(), run_id="r1"))
    assert [r.external_id for r in recs] == ["EJ100001", "ED600001"]
    assert recs[0].year == 2024
    assert recs[0].authors[0]["family"] == "Smith"
    assert recs[0].abstract.startswith("A study")
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/test_search_eric.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `rrl/search/eric.py`**

```python
"""ERIC adapter — education-focused, catches gray lit OpenAlex misses."""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord

BASE = "https://api.ies.ed.gov/eric/"
ROWS = 2000

def _parse_author(s: str) -> dict:
    # ERIC typically formats authors as "Family, Given"
    if "," in s:
        family, given = s.split(",", 1)
        return {"family": family.strip(), "given": given.strip(), "orcid": None}
    return {"family": s.strip(), "given": "", "orcid": None}

class ERICAdapter:
    name = "eric"

    def __init__(self, session: requests.Session):
        self.session = session

    def _render_q(self, q: QuerySpec) -> str:
        ai = " OR ".join(f'"{t}"' for t in q.ai_terms)
        he = " OR ".join(f'"{t}"' for t in q.he_terms)
        return (
            f"(title:({ai}) OR description:({ai})) "
            f"AND (descriptor:\"Higher Education\" OR description:({he})) "
            f"AND publicationdateyear:[{q.year_min} TO {q.year_max}]"
        )

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        start = 0
        params_base = {
            "q": self._render_q(q),
            "rows": ROWS,
            "format": "json",
        }
        while True:
            params = dict(params_base, start=start)
            r = self.session.get(BASE, params=params)
            r.raise_for_status()
            docs = r.json().get("response", {}).get("docs", [])
            if not docs:
                return
            for d in docs:
                yield self._parse(d)
            if len(docs) < ROWS:
                return
            start += ROWS

    def _parse(self, d: dict) -> RawRecord:
        title_list = d.get("title") or [""]
        desc_list = d.get("description") or []
        return RawRecord(
            external_id=d["id"],
            doi=None,  # ERIC rarely has DOIs
            title=title_list[0] if title_list else "",
            authors=[_parse_author(a) for a in (d.get("author") or [])],
            year=d.get("publicationdateyear"),
            venue=(d.get("publisher") or [None])[0],
            abstract=desc_list[0] if desc_list else None,
            language="en" if (d.get("language") or ["English"])[0].lower().startswith("eng") else None,
            raw_payload=d,
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_search_eric.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/search/eric.py tests/fixtures/eric_response.json tests/test_search_eric.py
git commit -m "feat: ERIC search adapter with start-based pagination"
```

---

## Task 10: Semantic Scholar adapter

**Files:**
- Create: `rrl/search/semantic_scholar.py`
- Create: `tests/fixtures/s2_bulk_response.json`
- Create: `tests/test_search_s2.py`

- [ ] **Step 1: Create fixture `tests/fixtures/s2_bulk_response.json`**

```json
{
  "token": "TOK2",
  "data": [
    {
      "paperId": "abc123",
      "externalIds": {"DOI": "10.1/zzz"},
      "title": "LLM use among graduate students",
      "year": 2023,
      "abstract": "Survey of LLM use.",
      "venue": "J. Educational Tech",
      "authors": [{"name": "Mei Wang", "authorId": "A1"}],
      "citationCount": 7
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_search_s2.py
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
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/test_search_s2.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `rrl/search/semantic_scholar.py`**

```python
"""Semantic Scholar bulk search adapter."""
from __future__ import annotations
from typing import Iterator

import requests

from rrl.search.base import QuerySpec, RawRecord, normalize_doi

BASE = "https://api.semanticscholar.org/graph/v1/paper/search/bulk"
FIELDS = "paperId,externalIds,title,year,abstract,venue,authors,citationCount"

def _author_dict(a: dict) -> dict:
    name = a.get("name") or ""
    parts = name.rsplit(" ", 1)
    given, family = (parts[0], parts[1]) if len(parts) == 2 else ("", name)
    return {"family": family, "given": given, "orcid": None}

class SemanticScholarAdapter:
    name = "s2"

    def __init__(self, session: requests.Session, api_key: str | None):
        self.session = session
        self.api_key = api_key

    def _render_query(self, q: QuerySpec) -> str:
        ai = " OR ".join(f'"{t}"' for t in q.ai_terms)
        he = " OR ".join(f'"{t}"' for t in q.he_terms)
        return f"({ai}) ({he})"

    def search(self, q: QuerySpec, run_id: str) -> Iterator[RawRecord]:
        headers = {"x-api-key": self.api_key} if self.api_key else {}
        params = {
            "query": self._render_query(q),
            "year": f"{q.year_min}-{q.year_max}",
            "fieldsOfStudy": "Education,Computer Science",
            "fields": FIELDS,
        }
        token: str | None = None
        while True:
            if token:
                params["token"] = token
            r = self.session.get(BASE, params=params, headers=headers)
            r.raise_for_status()
            payload = r.json()
            for w in payload.get("data", []):
                yield self._parse(w)
            token = payload.get("token")
            if not token:
                return

    def _parse(self, w: dict) -> RawRecord:
        ids = w.get("externalIds") or {}
        return RawRecord(
            external_id=w["paperId"],
            doi=normalize_doi(ids.get("DOI")),
            title=w.get("title") or "",
            authors=[_author_dict(a) for a in (w.get("authors") or [])],
            year=w.get("year"),
            venue=w.get("venue"),
            abstract=w.get("abstract"),
            language=None,  # S2 does not consistently expose language
            raw_payload=w,
        )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_search_s2.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/search/semantic_scholar.py tests/fixtures/s2_bulk_response.json tests/test_search_s2.py
git commit -m "feat: Semantic Scholar bulk search adapter with token pagination"
```

---

## Task 11: Harvest command (wire adapters → DB)

**Files:**
- Create: `rrl/harvest.py`
- Modify: `rrl/cli.py` (replace harvest stub)
- Create: `tests/test_harvest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harvest.py
import json
import responses
from pathlib import Path
from click.testing import CliRunner

from rrl.cli import main
from rrl.db import connect, init_schema

def _setup_responses(fixtures_dir: Path):
    oa1 = json.loads((fixtures_dir / "openalex_page1.json").read_text())
    oa2 = json.loads((fixtures_dir / "openalex_page2.json").read_text())
    eric = json.loads((fixtures_dir / "eric_response.json").read_text())
    eric_empty = {"response": {"numFound": 2, "start": 2000, "docs": []}}
    s2 = json.loads((fixtures_dir / "s2_bulk_response.json").read_text())
    s2_empty = {"token": None, "data": []}
    responses.add(responses.GET, "https://api.openalex.org/works", json=oa1)
    responses.add(responses.GET, "https://api.openalex.org/works", json=oa2)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=eric)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=eric_empty)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=s2)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=s2_empty)

@responses.activate
def test_harvest_populates_raw_records_and_search_runs(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    r = CliRunner().invoke(main, ["harvest"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    init_schema(conn)
    n_raw = conn.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]
    n_runs = conn.execute("SELECT COUNT(*) FROM search_runs").fetchone()[0]
    assert n_raw == 6  # 3 OA + 2 ERIC + 1 S2
    assert n_runs == 3
    statuses = {r[0] for r in conn.execute("SELECT status FROM search_runs").fetchall()}
    assert statuses == {"ok"}

@responses.activate
def test_harvest_is_idempotent_on_unique_constraint(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    CliRunner().invoke(main, ["harvest"])
    _setup_responses(fixtures_dir)  # second round of canned responses
    r = CliRunner().invoke(main, ["harvest"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    init_schema(conn)
    n_raw = conn.execute("SELECT COUNT(*) FROM raw_records").fetchone()[0]
    assert n_raw == 6  # unchanged — UNIQUE(adapter, external_id)

@responses.activate
def test_harvest_only_filter(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    monkeypatch.chdir(tmp_path)
    _setup_responses(fixtures_dir)
    r = CliRunner().invoke(main, ["harvest", "--only", "openalex"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    init_schema(conn)
    adapters = {r[0] for r in conn.execute("SELECT DISTINCT adapter FROM raw_records").fetchall()}
    assert adapters == {"openalex"}
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_harvest.py -v`
Expected: FAIL (the CLI harvest command is a stub).

- [ ] **Step 3: Implement `rrl/harvest.py`**

```python
"""Harvest orchestration: run adapters, persist to raw_records + search_runs."""
from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from rrl.config import AI_TERMS, HE_TERMS, RATE_PLANS, YEAR_MAX, YEAR_MIN, Settings
from rrl.db import connect, init_schema
from rrl.http import RateLimitedSession, build_session
from rrl.logging_setup import configure_logging, get_logger
from rrl.search.base import QuerySpec, RawRecord, normalize_title, normalize_author_name, query_hash
from rrl.search.openalex import OpenAlexAdapter
from rrl.search.eric import ERICAdapter
from rrl.search.semantic_scholar import SemanticScholarAdapter

ADAPTERS = ("openalex", "eric", "s2")

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _build_adapter(name: str, settings: Settings):
    sess = build_session(settings.openalex_email)
    rps = RATE_PLANS[name]["requests_per_second"]
    if name == "s2" and settings.s2_api_key:
        rps = RATE_PLANS["s2"]["with_key_rps"]
    rls = RateLimitedSession(sess, rps)
    # The adapter sees `rls` shaped like a session via attribute-forwarding;
    # for simplicity here, give adapters the raw session and let the harvester
    # pace at the page boundary (one .get per page is the rate target).
    if name == "openalex":
        return OpenAlexAdapter(session=rls, email=settings.openalex_email)
    if name == "eric":
        return ERICAdapter(session=rls)
    if name == "s2":
        return SemanticScholarAdapter(session=rls, api_key=settings.s2_api_key)
    raise ValueError(f"unknown adapter {name}")

def _persist_record(conn, run_id: str, adapter: str, rec: RawRecord) -> bool:
    first_author = normalize_author_name(rec.authors[0]["family"]) if rec.authors else None
    payload = json.dumps(rec.raw_payload, ensure_ascii=False)
    cur = conn.execute(
        """INSERT OR IGNORE INTO raw_records
           (run_id, adapter, external_id, doi, title, title_norm, authors_json,
            first_author, year, venue, abstract, language, raw_payload, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, adapter, rec.external_id, rec.doi, rec.title, normalize_title(rec.title),
         json.dumps(rec.authors, ensure_ascii=False), first_author, rec.year,
         rec.venue, rec.abstract, rec.language, payload, _now()),
    )
    return cur.rowcount > 0

def harvest(db_path: Path, *, only: list[str] | None = None) -> dict:
    settings = Settings.from_env()
    configure_logging("harvest", Path("logs"))
    log = get_logger()
    conn = connect(db_path)
    init_schema(conn)
    spec = QuerySpec(ai_terms=AI_TERMS, he_terms=HE_TERMS, year_min=YEAR_MIN, year_max=YEAR_MAX)
    qhash = query_hash(spec)
    counts: dict[str, int] = {}
    selected = only or list(ADAPTERS)
    for name in selected:
        if name not in ADAPTERS:
            log.warn("unknown_adapter", adapter=name)
            continue
        run_id = str(uuid.uuid4())
        adapter = _build_adapter(name, settings)
        conn.execute(
            """INSERT INTO search_runs (run_id, adapter, query_hash, query_payload,
               started_at, status) VALUES (?,?,?,?,?,?)""",
            (run_id, name, qhash, json.dumps({"spec": spec.__dict__}), _now(), "running"),
        )
        log.info("adapter_start", adapter=name, run_id=run_id)
        n_found = n_new = 0
        try:
            for rec in adapter.search(spec, run_id):
                n_found += 1
                if _persist_record(conn, run_id, name, rec):
                    n_new += 1
            conn.execute(
                """UPDATE search_runs SET status=?, finished_at=?, records_found=?, records_new=?
                   WHERE run_id=?""",
                ("ok", _now(), n_found, n_new, run_id),
            )
            log.info("adapter_done", adapter=name, found=n_found, new=n_new)
        except Exception as e:
            conn.execute(
                """UPDATE search_runs SET status=?, finished_at=?, error_message=?
                   WHERE run_id=?""",
                ("error", _now(), str(e), run_id),
            )
            log.error("adapter_error", adapter=name, error=str(e))
        counts[name] = n_new
    return counts
```

- [ ] **Step 4: Replace the harvest stub in `rrl/cli.py`**

Find this block:

```python
@main.command()
@click.option("--only", default=None, help="Comma-separated adapter names")
@click.option("--since", default=None, help="YYYY-MM-DD; harvest only papers since this date")
@click.pass_context
def harvest(ctx, only, since):
    """Search OpenAlex / ERIC / Semantic Scholar; persist raw_records."""
    click.echo("harvest: not yet implemented")  # wired in Task 11
    raise click.exceptions.Exit(2)
```

Replace with:

```python
@main.command()
@click.option("--only", default=None, help="Comma-separated adapter names")
@click.option("--since", default=None, help="YYYY-MM-DD; harvest only papers since this date")
@click.pass_context
def harvest(ctx, only, since):
    """Search OpenAlex / ERIC / Semantic Scholar; persist raw_records."""
    from rrl.harvest import harvest as run_harvest
    only_list = [a.strip() for a in only.split(",")] if only else None
    counts = run_harvest(ctx.obj["db"], only=only_list)
    for adapter, n in counts.items():
        click.echo(f"{adapter}: {n} new records")
```

(Note: `--since` is accepted for forward compat but not yet plumbed into the adapters; that is a later refinement noted in the spec's Section 5.)

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_harvest.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/harvest.py rrl/cli.py tests/test_harvest.py
git commit -m "feat: harvest stage wires adapters to DB with idempotent inserts"
```

---

## Task 12: Dedup module (key cascade, canonical resolution, merge ops)

**Files:**
- Create: `rrl/dedup/__init__.py`
- Create: `rrl/dedup/grouping.py`
- Create: `tests/test_dedup_grouping.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dedup_grouping.py
import json
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.dedup.grouping import (
    compute_dedup_key, paper_id_from_key, build_canonical_paper, run_dedup,
)

def _insert_raw(conn, run_id, adapter, ext_id, doi=None, title="T", year=2023,
                first_author="smith", authors=None, abstract=None, venue=None,
                openalex_id=None):
    authors = authors or [{"family": "Smith", "given": "J", "orcid": None}]
    payload = {"id": f"https://openalex.org/{openalex_id}"} if openalex_id else {}
    conn.execute(
        """INSERT INTO raw_records (run_id, adapter, external_id, doi, title, title_norm,
           authors_json, first_author, year, venue, abstract, language, raw_payload, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (run_id, adapter, ext_id, doi, title, title.lower(),
         json.dumps(authors), first_author, year, venue, abstract, "en",
         json.dumps(payload), "2026-05-14T00:00:00Z"),
    )

def _seed(conn):
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r1','openalex','h','{}','2026-05-14T00:00:00Z','ok')")
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r2','eric','h','{}','2026-05-14T00:00:00Z','ok')")

def test_doi_key_prefers_normalized():
    k1 = compute_dedup_key({"doi": "https://doi.org/10.1/X", "openalex_id": None,
                            "title_norm": "t", "year": 2023, "first_author": "smith", "raw_id": 1})
    k2 = compute_dedup_key({"doi": "10.1/x", "openalex_id": None,
                            "title_norm": "different", "year": 2024, "first_author": "doe", "raw_id": 2})
    assert k1 == k2

def test_openalex_key_used_when_no_doi():
    k = compute_dedup_key({"doi": None, "openalex_id": "W1",
                           "title_norm": "t", "year": 2023, "first_author": "smith", "raw_id": 1})
    assert k.startswith("openalex:")

def test_signature_key_fallback():
    k1 = compute_dedup_key({"doi": None, "openalex_id": None,
                            "title_norm": "study of chatgpt", "year": 2023, "first_author": "smith", "raw_id": 1})
    k2 = compute_dedup_key({"doi": None, "openalex_id": None,
                            "title_norm": "study of chatgpt", "year": 2023, "first_author": "smith", "raw_id": 2})
    assert k1 == k2 and k1.startswith("sig:")

def test_singleton_fallback_when_no_fields():
    k = compute_dedup_key({"doi": None, "openalex_id": None,
                           "title_norm": "", "year": None, "first_author": None, "raw_id": 99})
    assert k == "singleton:raw_99"

def test_paper_id_deterministic():
    k = "doi:10.1/x"
    assert paper_id_from_key(k) == paper_id_from_key(k)
    assert len(paper_id_from_key(k)) == 16

def test_run_dedup_merges_across_adapters(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W111", doi="10.1/aaa", title="ChatGPT in university", openalex_id="W111")
    _insert_raw(conn, "r2", "eric", "EJ100001", doi="10.1/aaa", title="ChatGPT in university (preprint)")
    summary = run_dedup(conn)
    assert summary["raw_records"] == 2
    assert summary["papers_created"] == 1
    n_links = conn.execute("SELECT COUNT(*) FROM paper_sources").fetchone()[0]
    assert n_links == 2

def test_run_dedup_keeps_distinct_papers(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W1", doi="10.1/a", title="A")
    _insert_raw(conn, "r1", "openalex", "W2", doi="10.1/b", title="B")
    run_dedup(conn)
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2

def test_run_dedup_is_idempotent(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn); _seed(conn)
    _insert_raw(conn, "r1", "openalex", "W1", doi="10.1/a", title="A")
    run_dedup(conn)
    run_dedup(conn)
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM paper_sources").fetchone()[0] == 1

def test_canonical_prefers_longest_title_and_openalex_source():
    raws = [
        {"adapter": "eric", "title": "Short title", "authors_json": '[{"family":"Smith"}]', "doi": None,
         "year": 2023, "venue": "X", "abstract": None, "language": "en", "first_author": "smith",
         "raw_id": 1, "raw_payload": "{}"},
        {"adapter": "openalex", "title": "Longer title from OpenAlex", "authors_json": '[{"family":"Smith"}]',
         "doi": "10.1/x", "year": 2023, "venue": "Y", "abstract": "Long abstract", "language": "en",
         "first_author": "smith", "raw_id": 2, "raw_payload": "{}"},
    ]
    canon = build_canonical_paper(raws)
    assert canon["title"] == "Longer title from OpenAlex"
    assert canon["venue"] == "Y"
    assert canon["abstract"] == "Long abstract"
    assert canon["doi"] == "10.1/x"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_dedup_grouping.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/dedup/__init__.py`** (empty file).

- [ ] **Step 4: Implement `rrl/dedup/grouping.py`**

```python
"""Dedup cascade: DOI > OpenAlex ID > signature key > singleton."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

SOURCE_PRIORITY = {"openalex": 0, "crossref": 1, "eric": 2, "s2": 3}

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def compute_dedup_key(row: dict) -> str:
    doi = row.get("doi")
    if doi:
        return f"doi:{doi}"
    oa = row.get("openalex_id")
    if oa:
        return f"openalex:{oa}"
    title = row.get("title_norm") or ""
    year = row.get("year")
    fa = row.get("first_author")
    if title and year and fa:
        return f"sig:{title}|{year}|{fa}"
    return f"singleton:raw_{row['raw_id']}"

def paper_id_from_key(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

def _openalex_id_from_payload(payload_json: str) -> str | None:
    try:
        payload = json.loads(payload_json)
    except Exception:
        return None
    pid = payload.get("id")
    if isinstance(pid, str) and "openalex.org/" in pid:
        return pid.rsplit("/", 1)[-1]
    return None

def _pick(rows: Iterable[dict], key: str, *, longest: bool = False) -> str | None:
    vals = [r.get(key) for r in rows if r.get(key)]
    if not vals:
        return None
    if longest:
        return max(vals, key=lambda v: len(str(v)))
    return vals[0]

def _by_source_priority(rows: Iterable[dict]) -> list[dict]:
    return sorted(rows, key=lambda r: SOURCE_PRIORITY.get(r["adapter"], 99))

def build_canonical_paper(raws: list[dict]) -> dict:
    ordered = _by_source_priority(raws)
    doi = next((r["doi"] for r in raws if r.get("doi")), None)
    title = max((r["title"] for r in ordered if r.get("title")),
                key=lambda t: len(t), default="")
    authors_json = next((r["authors_json"] for r in ordered if r.get("authors_json")), "[]")
    year = min((r["year"] for r in raws if r.get("year") is not None), default=None)
    venue = next((r["venue"] for r in ordered if r.get("venue")), None)
    abstract = max((r["abstract"] for r in raws if r.get("abstract")),
                   key=lambda a: len(a), default=None)
    language = next((r["language"] for r in ordered if r.get("language")), None)
    return {
        "doi": doi,
        "title": title,
        "authors_json": authors_json,
        "year": year,
        "venue": venue,
        "abstract": abstract,
        "language": language,
    }

def _row_for_key(r: sqlite3.Row) -> dict:
    return {
        "raw_id": r["raw_id"],
        "adapter": r["adapter"],
        "doi": r["doi"],
        "title": r["title"],
        "title_norm": r["title_norm"],
        "authors_json": r["authors_json"],
        "first_author": r["first_author"],
        "year": r["year"],
        "venue": r["venue"],
        "abstract": r["abstract"],
        "language": r["language"],
        "openalex_id": _openalex_id_from_payload(r["raw_payload"]),
        "raw_payload": r["raw_payload"],
    }

def run_dedup(conn: sqlite3.Connection) -> dict:
    rows = [_row_for_key(r) for r in conn.execute("SELECT * FROM raw_records").fetchall()]
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(paper_id_from_key(compute_dedup_key(r)), []).append(r)

    papers_created = 0
    for paper_id, raws in groups.items():
        canon = build_canonical_paper(raws)
        if not canon["title"] or canon["year"] is None:
            # We cannot satisfy NOT NULL constraints; skip with a singleton fallback title.
            canon["title"] = canon["title"] or "(untitled)"
            canon["year"] = canon["year"] or 0
        conn.execute(
            """INSERT INTO papers (paper_id, doi, title, authors_json, year, venue,
               abstract, language, first_seen_at, last_updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(paper_id) DO UPDATE SET
                 doi=excluded.doi, title=excluded.title, authors_json=excluded.authors_json,
                 year=excluded.year, venue=excluded.venue, abstract=excluded.abstract,
                 language=excluded.language, last_updated_at=excluded.last_updated_at""",
            (paper_id, canon["doi"], canon["title"], canon["authors_json"], canon["year"],
             canon["venue"], canon["abstract"], canon["language"], _now(), _now()),
        )
        for r in raws:
            conn.execute(
                "INSERT OR IGNORE INTO paper_sources (paper_id, raw_id) VALUES (?,?)",
                (paper_id, r["raw_id"]),
            )
        papers_created += 1
    return {"raw_records": len(rows), "papers_created": papers_created}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_dedup_grouping.py -v`
Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/dedup/ tests/test_dedup_grouping.py
git commit -m "feat: dedup cascade + canonical resolution + idempotent upsert"
```

---

## Task 13: Dedup command (incl. --review and --merge)

**Files:**
- Create: `rrl/dedup/review.py`
- Create: `rrl/dedup/merge.py`
- Modify: `rrl/cli.py` (replace dedup stub)
- Create: `tests/test_dedup_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dedup_cli.py
import json
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema

def _seed_two_papers(db_path: Path):
    conn = connect(db_path); init_schema(conn)
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','2026-05-14T00:00:00Z','ok')")
    for ext, doi, title in [("W1","10.1/a","Generative AI in colleges 2023 Smith"),
                            ("W2","10.1/b","Generative AI in colleges 2023 (preprint) Smith")]:
        conn.execute(
            """INSERT INTO raw_records (run_id, adapter, external_id, doi, title, title_norm,
               authors_json, first_author, year, venue, abstract, language, raw_payload, fetched_at)
               VALUES ('r','openalex',?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ext, doi, title, title.lower(),
             json.dumps([{"family":"Smith","given":"J","orcid":None}]),
             "smith", 2023, "J", "abs", "en", "{}", "2026-05-14T00:00:00Z"),
        )

def test_dedup_command_creates_papers(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed_two_papers(tmp_path / "data/rrl.sqlite")
    r = CliRunner().invoke(main, ["dedup"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    assert conn.execute("SELECT COUNT(*) FROM papers").fetchone()[0] == 2

def test_dedup_review_writes_csv(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed_two_papers(tmp_path / "data/rrl.sqlite")
    CliRunner().invoke(main, ["dedup"])
    r = CliRunner().invoke(main, ["dedup", "--review"])
    assert r.exit_code == 0, r.output
    review = tmp_path / "data/dedup_review.csv"
    assert review.exists()
    rows = review.read_text().strip().splitlines()
    assert len(rows) >= 2  # header + at least one pair

def test_dedup_merge_records_paper_merges(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed_two_papers(tmp_path / "data/rrl.sqlite")
    CliRunner().invoke(main, ["dedup"])
    conn = connect(tmp_path / "data/rrl.sqlite")
    ids = [r[0] for r in conn.execute("SELECT paper_id FROM papers").fetchall()]
    loser, winner = ids[0], ids[1]
    r = CliRunner().invoke(main, ["dedup", "--merge", loser, winner])
    assert r.exit_code == 0, r.output
    n = conn.execute("SELECT COUNT(*) FROM paper_merges WHERE loser_id=? AND winner_id=?", (loser, winner)).fetchone()[0]
    assert n == 1
    # paper_sources of loser repointed to winner.
    rem = conn.execute("SELECT COUNT(*) FROM paper_sources WHERE paper_id=?", (loser,)).fetchone()[0]
    assert rem == 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_dedup_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/dedup/review.py`**

```python
"""Write data/dedup_review.csv: pairs of likely-duplicate papers for manual judgment."""
from __future__ import annotations
import csv
import sqlite3
from itertools import combinations
from pathlib import Path

from rapidfuzz.fuzz import token_sort_ratio

THRESHOLD = 85.0

def write_review_csv(conn: sqlite3.Connection, out_path: Path) -> int:
    rows = conn.execute(
        """SELECT paper_id, title, year, authors_json FROM papers
           WHERE paper_id NOT IN (SELECT loser_id FROM paper_merges)"""
    ).fetchall()
    # Block by (first_author_letter, year)
    blocks: dict[tuple, list[sqlite3.Row]] = {}
    for r in rows:
        import json
        first = (json.loads(r["authors_json"]) or [{}])[0].get("family", "") or ""
        key = (first[:1].lower(), r["year"])
        blocks.setdefault(key, []).append(r)
    pairs: list[tuple[float, str, str, str, str]] = []
    for block in blocks.values():
        for a, b in combinations(block, 2):
            score = token_sort_ratio(a["title"], b["title"])
            if score >= THRESHOLD:
                pairs.append((score, a["paper_id"], a["title"], b["paper_id"], b["title"]))
    pairs.sort(reverse=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["similarity", "paper_id_a", "title_a", "paper_id_b", "title_b"])
        for row in pairs:
            w.writerow(row)
    return len(pairs)
```

- [ ] **Step 4: Implement `rrl/dedup/merge.py`**

```python
"""Manual merge: write paper_merges row and migrate paper_sources / pdf metadata."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def merge_papers(conn: sqlite3.Connection, loser_id: str, winner_id: str, pdf_root: Path) -> None:
    for pid in (loser_id, winner_id):
        if conn.execute("SELECT 1 FROM papers WHERE paper_id=?", (pid,)).fetchone() is None:
            raise ValueError(f"unknown paper_id {pid}")
    if loser_id == winner_id:
        raise ValueError("loser and winner must differ")

    # 1. Record the merge.
    conn.execute(
        "INSERT OR REPLACE INTO paper_merges (loser_id, winner_id, merged_at, merged_by) VALUES (?,?,?,?)",
        (loser_id, winner_id, _now(), "manual"),
    )
    # 2. Repoint paper_sources.
    conn.execute(
        """INSERT OR IGNORE INTO paper_sources (paper_id, raw_id)
           SELECT ?, raw_id FROM paper_sources WHERE paper_id=?""",
        (winner_id, loser_id),
    )
    conn.execute("DELETE FROM paper_sources WHERE paper_id=?", (loser_id,))
    # 3. Migrate PDF if winner lacks one.
    loser_pdf = conn.execute("SELECT pdf_filename FROM papers WHERE paper_id=?", (loser_id,)).fetchone()["pdf_filename"]
    winner_pdf = conn.execute("SELECT pdf_filename FROM papers WHERE paper_id=?", (winner_id,)).fetchone()["pdf_filename"]
    if loser_pdf and not winner_pdf:
        src = pdf_root / loser_pdf
        if src.exists():
            new_name = src.with_name(f"{winner_id}.pdf")
            src.rename(new_name)
            rel = str(new_name.relative_to(pdf_root))
            conn.execute("UPDATE papers SET pdf_filename=?, pdf_status='downloaded' WHERE paper_id=?", (rel, winner_id))
        conn.execute("UPDATE papers SET pdf_status='merged_to_winner', pdf_filename=NULL WHERE paper_id=?", (loser_id,))
    # 4. Copy enrichment fields from loser where winner is missing them.
    for col in ("is_in_doaj", "is_peer_reviewed", "is_oa", "oa_status", "oa_pdf_url",
                "citation_count", "publisher", "work_type"):
        conn.execute(
            f"UPDATE papers SET {col}=(SELECT {col} FROM papers WHERE paper_id=?) "
            f"WHERE paper_id=? AND {col} IS NULL",
            (loser_id, winner_id),
        )
```

- [ ] **Step 5: Replace the dedup stub in `rrl/cli.py`**

Find this block:

```python
@main.command()
@click.option("--review", is_flag=True, help="Write data/dedup_review.csv")
@click.option("--merge", nargs=2, type=str, default=None, metavar="LOSER WINNER")
@click.pass_context
def dedup(ctx, review, merge):
    """Build canonical papers from raw_records."""
    click.echo("dedup: not yet implemented")
    raise click.exceptions.Exit(2)
```

Replace with:

```python
@main.command()
@click.option("--review", is_flag=True, help="Write data/dedup_review.csv")
@click.option("--merge", nargs=2, type=str, default=None, metavar="LOSER WINNER")
@click.pass_context
def dedup(ctx, review, merge):
    """Build canonical papers from raw_records."""
    from rrl.db import connect, init_schema
    from rrl.dedup.grouping import run_dedup
    from rrl.dedup.review import write_review_csv
    from rrl.dedup.merge import merge_papers
    db_path = ctx.obj["db"]
    conn = connect(db_path); init_schema(conn)
    if merge:
        loser, winner = merge
        merge_papers(conn, loser, winner, pdf_root=Path("pdfs"))
        click.echo(f"merged {loser} into {winner}")
        return
    if review:
        n = write_review_csv(conn, Path("data/dedup_review.csv"))
        click.echo(f"wrote {n} candidate pair(s) to data/dedup_review.csv")
        return
    summary = run_dedup(conn)
    click.echo(f"raw_records: {summary['raw_records']}; papers: {summary['papers_created']}")
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_dedup_cli.py -v`
Expected: 3 passed.

- [ ] **Step 7: Commit**

```bash
git add rrl/dedup/review.py rrl/dedup/merge.py rrl/cli.py tests/test_dedup_cli.py
git commit -m "feat: dedup CLI with --review (CSV) and --merge ops"
```

---

## Task 14: DOAJ enrich

**Files:**
- Create: `rrl/enrich/__init__.py`
- Create: `rrl/enrich/doaj.py`
- Create: `tests/test_enrich_doaj.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_doaj.py
import responses
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.doaj import lookup_issn, enrich_papers_with_doaj
from rrl.http import build_session

@responses.activate
def test_lookup_issn_listed():
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1234-5678",
                  json={"results": [{"id": "abc"}]}, status=200)
    assert lookup_issn(build_session("t@e.com"), "1234-5678") is True

@responses.activate
def test_lookup_issn_not_listed():
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:9999-9999",
                  json={"results": []}, status=200)
    assert lookup_issn(build_session("t@e.com"), "9999-9999") is False

@responses.activate
def test_enrich_skips_papers_without_issn(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    # No raw_records → no ISSN → skipped, is_in_doaj stays NULL.
    enrich_papers_with_doaj(conn, build_session("t@e.com"))
    v = conn.execute("SELECT is_in_doaj FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert v is None

@responses.activate
def test_enrich_sets_flag_when_issn_present(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    payload = '{"primary_location":{"source":{"issn_l":"1111-2222"}}}'
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (payload, "now"))
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES ('p1', 1)")
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1111-2222",
                  json={"results": [{"id": "abc"}]}, status=200)
    enrich_papers_with_doaj(conn, build_session("t@e.com"))
    v = conn.execute("SELECT is_in_doaj FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert v == 1
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_enrich_doaj.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/enrich/__init__.py`** (empty).

- [ ] **Step 4: Implement `rrl/enrich/doaj.py`**

```python
"""DOAJ verification: is the paper's journal listed in DOAJ?"""
from __future__ import annotations
import json
import sqlite3

import requests

BASE = "https://doaj.org/api/v3/search/journals/issn:"

def lookup_issn(session: requests.Session, issn: str) -> bool:
    r = session.get(BASE + issn)
    if r.status_code == 404:
        return False
    r.raise_for_status()
    return bool(r.json().get("results"))

def _issn_for_paper(conn: sqlite3.Connection, paper_id: str) -> str | None:
    rows = conn.execute(
        """SELECT rr.raw_payload FROM raw_records rr
           JOIN paper_sources ps ON ps.raw_id = rr.raw_id
           WHERE ps.paper_id = ? AND rr.adapter = 'openalex'""",
        (paper_id,),
    ).fetchall()
    for r in rows:
        try:
            payload = json.loads(r["raw_payload"])
        except Exception:
            continue
        src = (payload.get("primary_location") or {}).get("source") or {}
        issn = src.get("issn_l") or (src.get("issn") or [None])[0]
        if issn:
            return issn
    return None

def enrich_papers_with_doaj(conn: sqlite3.Connection, session: requests.Session) -> dict:
    cache: dict[str, bool] = {}
    n_set = n_skipped = 0
    papers = conn.execute("SELECT paper_id FROM papers WHERE is_in_doaj IS NULL").fetchall()
    for row in papers:
        pid = row["paper_id"]
        issn = _issn_for_paper(conn, pid)
        if not issn:
            n_skipped += 1
            continue
        if issn not in cache:
            cache[issn] = lookup_issn(session, issn)
        conn.execute("UPDATE papers SET is_in_doaj=?, last_updated_at=datetime('now') WHERE paper_id=?",
                     (1 if cache[issn] else 0, pid))
        n_set += 1
    return {"updated": n_set, "skipped_no_issn": n_skipped}
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_enrich_doaj.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/enrich/ tests/test_enrich_doaj.py
git commit -m "feat: DOAJ ISSN verification pass"
```

---

## Task 15: Unpaywall enrich

**Files:**
- Create: `rrl/enrich/unpaywall.py`
- Create: `tests/test_enrich_unpaywall.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_unpaywall.py
import responses
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.unpaywall import enrich_papers_with_unpaywall, lookup_doi
from rrl.http import build_session

@responses.activate
def test_lookup_returns_pdf_url():
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/aaa",
                  json={"best_oa_location": {"url_for_pdf": "https://x/y.pdf"}}, status=200)
    pdf, status = lookup_doi(build_session("t@e.com"), "10.1/aaa", "t@e.com")
    assert pdf == "https://x/y.pdf"

@responses.activate
def test_lookup_handles_no_oa():
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/bbb",
                  json={"best_oa_location": None}, status=200)
    pdf, status = lookup_doi(build_session("t@e.com"), "10.1/bbb", "t@e.com")
    assert pdf is None

@responses.activate
def test_enrich_writes_oa_pdf_url(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,'now','now')")
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/aaa",
                  json={"best_oa_location": {"url_for_pdf": "https://x/y.pdf"}}, status=200)
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    v = conn.execute("SELECT oa_pdf_url FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert v == "https://x/y.pdf"

@responses.activate
def test_enrich_skips_papers_without_doi(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    enrich_papers_with_unpaywall(conn, build_session("t@e.com"), email="t@e.com")
    # No HTTP call required.
    assert len(responses.calls) == 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_enrich_unpaywall.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/enrich/unpaywall.py`**

```python
"""Unpaywall: find the authoritative OA PDF URL for a DOI."""
from __future__ import annotations
import sqlite3

import requests

BASE = "https://api.unpaywall.org/v2/"

def lookup_doi(session: requests.Session, doi: str, email: str) -> tuple[str | None, str | None]:
    r = session.get(BASE + doi, params={"email": email})
    if r.status_code == 404:
        return None, "not_found"
    r.raise_for_status()
    payload = r.json()
    loc = payload.get("best_oa_location") or {}
    return loc.get("url_for_pdf"), payload.get("oa_status")

def enrich_papers_with_unpaywall(conn: sqlite3.Connection, session: requests.Session, email: str) -> dict:
    """Per the spec, Unpaywall OVERRIDES OpenAlex's oa_pdf_url. Look up every paper
    with a DOI and overwrite oa_pdf_url when Unpaywall has a result."""
    rows = conn.execute(
        "SELECT paper_id, doi FROM papers WHERE doi IS NOT NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        pdf, status = lookup_doi(session, row["doi"], email)
        if pdf:
            conn.execute(
                """UPDATE papers SET oa_pdf_url=?, oa_status=COALESCE(?, oa_status),
                   last_updated_at=datetime('now') WHERE paper_id=?""",
                (pdf, status, row["paper_id"]),
            )
            updated += 1
    return {"updated": updated, "checked": len(rows)}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_enrich_unpaywall.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/enrich/unpaywall.py tests/test_enrich_unpaywall.py
git commit -m "feat: Unpaywall DOI lookup writes oa_pdf_url"
```

---

## Task 16: OpenAlex-derived enrich (lift flags from raw_payload)

**Files:**
- Create: `rrl/enrich/openalex_flags.py`
- Create: `tests/test_enrich_openalex_flags.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_openalex_flags.py
import json
from pathlib import Path
from rrl.db import connect, init_schema
from rrl.enrich.openalex_flags import enrich_from_openalex_payloads

def _seed(conn, paper_id, payload):
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (json.dumps(payload), "now"))
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES (?, 'T', '[]', 2023, 'now', 'now')", (paper_id,))
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES (?, 1)", (paper_id,))

def test_enrich_lifts_flags(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    payload = {
        "type": "journal-article",
        "cited_by_count": 12,
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "best_oa_location": {"pdf_url": "https://x/y.pdf"},
        "primary_location": {"source": {"host_organization_name": "Springer", "type": "journal"}},
    }
    _seed(conn, "p1", payload)
    enrich_from_openalex_payloads(conn)
    row = conn.execute("SELECT is_oa, oa_status, oa_pdf_url, work_type, publisher, citation_count, is_peer_reviewed FROM papers WHERE paper_id='p1'").fetchone()
    assert row["is_oa"] == 1
    assert row["oa_status"] == "gold"
    assert row["oa_pdf_url"] == "https://x/y.pdf"
    assert row["work_type"] == "journal-article"
    assert row["publisher"] == "Springer"
    assert row["citation_count"] == 12
    assert row["is_peer_reviewed"] == 1

def test_enrich_skips_repository_as_peer_reviewed(tmp_path: Path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    payload = {
        "type": "posted-content",
        "primary_location": {"source": {"type": "repository", "host_organization_name": "arXiv"}},
    }
    _seed(conn, "p2", payload)
    enrich_from_openalex_payloads(conn)
    row = conn.execute("SELECT is_peer_reviewed FROM papers WHERE paper_id='p2'").fetchone()
    assert row["is_peer_reviewed"] == 0
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_enrich_openalex_flags.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/enrich/openalex_flags.py`**

```python
"""Lift OA / quality flags from cached OpenAlex raw payloads. No network."""
from __future__ import annotations
import json
import sqlite3

PEER_REVIEWED_TYPES = {"journal-article", "book-chapter", "proceedings-article", "review"}

def _flags_from_payload(payload: dict) -> dict:
    oa = payload.get("open_access") or {}
    loc = (payload.get("primary_location") or {}).get("source") or {}
    best_oa = payload.get("best_oa_location") or {}
    work_type = payload.get("type")
    source_type = loc.get("type")
    is_peer_reviewed = int(work_type in PEER_REVIEWED_TYPES and source_type != "repository")
    return {
        "is_oa": int(oa.get("is_oa", False)) if oa else None,
        "oa_status": oa.get("oa_status"),
        "oa_pdf_url": best_oa.get("pdf_url"),
        "work_type": work_type,
        "publisher": loc.get("host_organization_name"),
        "citation_count": payload.get("cited_by_count"),
        "is_peer_reviewed": is_peer_reviewed,
    }

def enrich_from_openalex_payloads(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        """SELECT p.paper_id, rr.raw_payload FROM papers p
           JOIN paper_sources ps ON ps.paper_id = p.paper_id
           JOIN raw_records rr ON rr.raw_id = ps.raw_id
           WHERE rr.adapter = 'openalex'"""
    ).fetchall()
    updated = 0
    for row in rows:
        try:
            payload = json.loads(row["raw_payload"])
        except Exception:
            continue
        f = _flags_from_payload(payload)
        conn.execute(
            """UPDATE papers SET
                 is_oa=COALESCE(is_oa, ?),
                 oa_status=COALESCE(oa_status, ?),
                 oa_pdf_url=COALESCE(oa_pdf_url, ?),
                 work_type=COALESCE(work_type, ?),
                 publisher=COALESCE(publisher, ?),
                 citation_count=COALESCE(citation_count, ?),
                 is_peer_reviewed=COALESCE(is_peer_reviewed, ?),
                 last_updated_at=datetime('now')
               WHERE paper_id=?""",
            (f["is_oa"], f["oa_status"], f["oa_pdf_url"], f["work_type"], f["publisher"],
             f["citation_count"], f["is_peer_reviewed"], row["paper_id"]),
        )
        updated += 1
    return {"updated": updated}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_enrich_openalex_flags.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/enrich/openalex_flags.py tests/test_enrich_openalex_flags.py
git commit -m "feat: lift OA + quality flags from cached OpenAlex payloads"
```

---

## Task 17: Enrich command (wire passes together)

**Files:**
- Modify: `rrl/cli.py` (replace enrich stub)
- Create: `tests/test_enrich_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_enrich_cli.py
import json
import responses
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema

def _seed(db_path: Path):
    conn = connect(db_path); init_schema(conn)
    payload = {
        "type": "journal-article",
        "open_access": {"is_oa": True, "oa_status": "gold"},
        "primary_location": {"source": {"host_organization_name": "Springer", "type": "journal", "issn_l": "1111-2222"}},
        "best_oa_location": {"pdf_url": "https://x/y.pdf"},
        "cited_by_count": 3,
    }
    conn.execute("INSERT INTO search_runs (run_id, adapter, query_hash, query_payload, started_at, status) VALUES ('r','openalex','h','{}','now','ok')")
    conn.execute("INSERT INTO raw_records (run_id, adapter, external_id, title, raw_payload, fetched_at) VALUES ('r','openalex','W1','T',?,?)", (json.dumps(payload), "now"))
    conn.execute("INSERT INTO papers (paper_id, doi, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','10.1/aaa','T','[]',2023,'now','now')")
    conn.execute("INSERT INTO paper_sources (paper_id, raw_id) VALUES ('p1', 1)")

@responses.activate
def test_enrich_runs_all_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    _seed(tmp_path / "data/rrl.sqlite")
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1111-2222",
                  json={"results": [{"id": "abc"}]}, status=200)
    responses.add(responses.GET, "https://api.unpaywall.org/v2/10.1/aaa",
                  json={"best_oa_location": {"url_for_pdf": "https://better.pdf"}}, status=200)
    r = CliRunner().invoke(main, ["enrich"])
    assert r.exit_code == 0, r.output
    conn = connect(tmp_path / "data/rrl.sqlite")
    row = conn.execute("SELECT is_in_doaj, oa_pdf_url, work_type, is_peer_reviewed FROM papers WHERE paper_id='p1'").fetchone()
    assert row["is_in_doaj"] == 1
    # Unpaywall overrides OpenAlex.
    assert row["oa_pdf_url"] == "https://better.pdf"
    assert row["work_type"] == "journal-article"
    assert row["is_peer_reviewed"] == 1
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_enrich_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Replace the enrich stub in `rrl/cli.py`**

```python
@main.command()
@click.option("--only", default=None, help="doaj|unpaywall|openalex")
@click.pass_context
def enrich(ctx, only):
    """Attach DOAJ + Unpaywall + OpenAlex quality flags."""
    from rrl.db import connect, init_schema
    from rrl.config import Settings
    from rrl.http import build_session
    from rrl.enrich.openalex_flags import enrich_from_openalex_payloads
    from rrl.enrich.doaj import enrich_papers_with_doaj
    from rrl.enrich.unpaywall import enrich_papers_with_unpaywall
    settings = Settings.from_env()
    conn = connect(ctx.obj["db"]); init_schema(conn)
    sess = build_session(settings.openalex_email)
    passes = (only or "openalex,doaj,unpaywall").split(",")
    if "openalex" in passes:
        s = enrich_from_openalex_payloads(conn); click.echo(f"openalex: {s}")
    if "doaj" in passes:
        s = enrich_papers_with_doaj(conn, sess); click.echo(f"doaj: {s}")
    if "unpaywall" in passes:
        s = enrich_papers_with_unpaywall(conn, sess, settings.openalex_email); click.echo(f"unpaywall: {s}")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_enrich_cli.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/cli.py tests/test_enrich_cli.py
git commit -m "feat: enrich CLI runs openalex flags → DOAJ → Unpaywall"
```

---

## Task 18: Screen rules (regex, filter chain, tiering)

**Files:**
- Create: `rrl/screen/__init__.py`
- Create: `rrl/screen/rules.py`
- Create: `tests/test_screen_rules.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen_rules.py
from rrl.screen.rules import (
    topic_hits, era_tag_for_year, evaluate_paper, decide_quality_tier,
)

def test_topic_hits_counts_unique():
    text = "ChatGPT in university and college: faculty perceptions"
    ai, he, score = topic_hits(text)
    assert ai >= 1 and he >= 2
    assert score == ai + he

def test_era_tag():
    assert era_tag_for_year(2020) == "pre_chatgpt"
    assert era_tag_for_year(2022) == "pre_chatgpt"
    assert era_tag_for_year(2023) == "post_chatgpt"
    assert era_tag_for_year(2026) == "post_chatgpt"

def test_evaluate_paper_includes_on_topic_oa():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in higher education", "abstract": "Survey of faculty.", "venue": "J"}
    r = evaluate_paper(p)
    assert r["included"] == 1
    assert r["era_tag"] == "post_chatgpt"
    assert r["exclusion_reason"] is None

def test_evaluate_rejects_wrong_date():
    p = {"year": 2019, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in university", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "wrong_date"

def test_evaluate_rejects_non_english():
    p = {"year": 2023, "language": "es", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT en universidad", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "non_english"

def test_evaluate_rejects_not_oa():
    p = {"year": 2023, "language": "en", "is_oa": 0, "oa_pdf_url": None,
         "title": "ChatGPT in university", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "not_oa"

def test_evaluate_rejects_off_topic():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "Tomato cultivation in Andalusia", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "off_topic"

def test_evaluate_rejects_k12_only():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in middle school classrooms", "abstract": "", "venue": ""}
    assert evaluate_paper(p)["exclusion_reason"] == "k12_only"

def test_mixed_k12_and_he_forces_review_needed():
    p = {"year": 2023, "language": "en", "is_oa": 1, "oa_pdf_url": "u",
         "title": "ChatGPT in high school and university classrooms",
         "abstract": "Comparison across K-12 and undergraduate.", "venue": "",
         "is_peer_reviewed": 1, "work_type": "journal-article", "publisher": "Springer"}
    r = evaluate_paper(p)
    assert r["included"] == 1
    assert r["quality_tier"] == "review_needed"

def test_high_confidence_for_journal_article_in_doaj():
    p = {"included": 1, "is_peer_reviewed": 0, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "Some Journal", "k12_mixed": False}
    assert decide_quality_tier(p) == "high_confidence"

def test_book_chapter_requires_allowlisted_publisher():
    bad = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 0,
           "work_type": "book-chapter", "publisher": "Random Self-Pub", "k12_mixed": False}
    good = {**bad, "publisher": "Springer"}
    assert decide_quality_tier(bad) == "review_needed"
    assert decide_quality_tier(good) == "high_confidence"

def test_predatory_publisher_forces_review_needed():
    p = {"included": 1, "is_peer_reviewed": 1, "is_in_doaj": 1,
         "work_type": "journal-article", "publisher": "OMICS International", "k12_mixed": False}
    assert decide_quality_tier(p) == "review_needed"
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_screen_rules.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/screen/__init__.py`** (empty).

- [ ] **Step 4: Implement `rrl/screen/rules.py`**

```python
"""Screening rules: filter chain + quality tiering. No network calls."""
from __future__ import annotations
import re

from rrl.config import (
    AI_TERMS, HE_TERMS, K12_TERMS,
    YEAR_MIN, YEAR_MAX,
    PREDATORY_BLOCKLIST, ACADEMIC_PRESS_ALLOWLIST,
)

def _alt(terms: list[str]) -> str:
    return "|".join(re.escape(t) for t in terms)

AI_RE  = re.compile(rf"\b({_alt(AI_TERMS)})\b", re.IGNORECASE)
HE_RE  = re.compile(rf"\b({_alt(HE_TERMS)})\b", re.IGNORECASE)
K12_RE = re.compile(rf"\b({_alt(K12_TERMS)}|grade [1-9]|grade 1[0-2])\b", re.IGNORECASE)

CS_CURRICULUM_RE = re.compile(
    r"\b(AI curriculum|teaching machine learning|introductory AI course|"
    r"machine learning curriculum|computer science course on AI)\b",
    re.IGNORECASE,
)

def topic_hits(text: str) -> tuple[int, int, float]:
    ai = {m.group(0).lower() for m in AI_RE.finditer(text)}
    he = {m.group(0).lower() for m in HE_RE.finditer(text)}
    return len(ai), len(he), float(len(ai) + len(he))

def era_tag_for_year(year: int) -> str:
    return "post_chatgpt" if year >= 2023 else "pre_chatgpt"

def _has_text(p: dict) -> str:
    return " ".join(filter(None, [p.get("title"), p.get("abstract"), p.get("venue")]))

def evaluate_paper(p: dict) -> dict:
    """Return a dict of screening decisions for a paper-shaped row."""
    year = p.get("year")
    if year is None or year < YEAR_MIN or year > YEAR_MAX:
        return {"included": 0, "exclusion_reason": "wrong_date"}
    if (p.get("language") or "").lower() != "en":
        return {"included": 0, "exclusion_reason": "non_english"}
    if not p.get("is_oa") or not p.get("oa_pdf_url"):
        return {"included": 0, "exclusion_reason": "not_oa"}
    text = _has_text(p)
    ai_n, he_n, score = topic_hits(text)
    if ai_n < 1 or he_n < 1:
        return {"included": 0, "exclusion_reason": "off_topic", "topic_match_score": score}
    k12_n = len(K12_RE.findall(text))
    if k12_n > 0 and he_n == 0:
        return {"included": 0, "exclusion_reason": "k12_only", "topic_match_score": score}
    k12_mixed = k12_n > 0 and he_n > 0
    cs_curr_signal = bool(CS_CURRICULUM_RE.search(text))
    tier = decide_quality_tier({
        "included": 1,
        "is_peer_reviewed": p.get("is_peer_reviewed"),
        "is_in_doaj": p.get("is_in_doaj"),
        "work_type": p.get("work_type"),
        "publisher": p.get("publisher"),
        "k12_mixed": k12_mixed,
        "cs_curriculum_signal": cs_curr_signal,
    })
    return {
        "included": 1,
        "exclusion_reason": None,
        "topic_match_score": score,
        "era_tag": era_tag_for_year(year),
        "quality_tier": tier,
    }

def decide_quality_tier(p: dict) -> str:
    if p.get("k12_mixed") or p.get("cs_curriculum_signal"):
        return "review_needed"
    publisher = (p.get("publisher") or "").strip()
    if publisher in PREDATORY_BLOCKLIST:
        return "review_needed"
    wt = p.get("work_type")
    if wt == "book-chapter":
        if publisher not in ACADEMIC_PRESS_ALLOWLIST:
            return "review_needed"
    elif wt not in {"journal-article", "proceedings-article", "review"}:
        return "review_needed"
    if not (p.get("is_peer_reviewed") == 1 or p.get("is_in_doaj") == 1):
        return "review_needed"
    return "high_confidence"
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_screen_rules.py -v`
Expected: 12 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/screen/ tests/test_screen_rules.py
git commit -m "feat: screening rules — filter chain, K-12, OA, tiering, era"
```

---

## Task 19: Screen command

**Files:**
- Create: `rrl/screen/runner.py`
- Modify: `rrl/cli.py` (replace screen stub)
- Create: `tests/test_screen_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screen_cli.py
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema

def _insert(conn, pid, **kw):
    cols = {"paper_id": pid, "title": "T", "authors_json": "[]", "year": 2023,
            "language": "en", "is_oa": 1, "oa_pdf_url": "u",
            "first_seen_at": "now", "last_updated_at": "now"}
    cols.update(kw)
    keys = ",".join(cols.keys())
    qs = ",".join(["?"] * len(cols))
    conn.execute(f"INSERT INTO papers ({keys}) VALUES ({qs})", tuple(cols.values()))

def test_screen_assigns_included_and_tier(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    _insert(conn, "p_good", title="ChatGPT in higher education",
            is_peer_reviewed=1, work_type="journal-article", publisher="J", abstract="Survey of faculty.")
    _insert(conn, "p_offtopic", title="Tomato cultivation", abstract="No relevance")
    _insert(conn, "p_old", year=2019, title="ChatGPT in higher education", abstract="")
    r = CliRunner().invoke(main, ["screen"])
    assert r.exit_code == 0, r.output
    rows = {row[0]: row for row in conn.execute("SELECT paper_id, included, exclusion_reason, quality_tier, era_tag FROM papers").fetchall()}
    assert rows["p_good"][1] == 1
    assert rows["p_good"][3] == "high_confidence"
    assert rows["p_good"][4] == "post_chatgpt"
    assert rows["p_offtopic"][1] == 0
    assert rows["p_offtopic"][2] == "off_topic"
    assert rows["p_old"][2] == "wrong_date"

def test_screen_dry_run_does_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    _insert(conn, "p1", title="ChatGPT in university")
    r = CliRunner().invoke(main, ["screen", "--dry-run"])
    assert r.exit_code == 0
    inc = conn.execute("SELECT included FROM papers WHERE paper_id='p1'").fetchone()[0]
    assert inc is None
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_screen_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/screen/runner.py`**

```python
"""Apply screening decisions to every paper. Pure SQL + regex; no network."""
from __future__ import annotations
import sqlite3
from collections import Counter

from rrl.screen.rules import evaluate_paper

PAPER_COLS = ("paper_id", "title", "abstract", "venue", "year", "language",
              "is_oa", "oa_pdf_url", "is_peer_reviewed", "is_in_doaj",
              "work_type", "publisher")

def run_screen(conn: sqlite3.Connection, *, dry_run: bool = False) -> dict:
    rows = conn.execute(f"SELECT {','.join(PAPER_COLS)} FROM papers").fetchall()
    counts: Counter = Counter()
    for r in rows:
        decision = evaluate_paper({c: r[c] for c in PAPER_COLS})
        if decision.get("included"):
            counts["included"] += 1
            counts[decision.get("quality_tier")] += 1
        else:
            counts["excluded"] += 1
            counts[decision.get("exclusion_reason")] += 1
        if dry_run:
            continue
        conn.execute(
            """UPDATE papers SET included=?, exclusion_reason=?, quality_tier=?,
               era_tag=?, topic_match_score=?, last_updated_at=datetime('now')
               WHERE paper_id=?""",
            (decision.get("included"), decision.get("exclusion_reason"),
             decision.get("quality_tier"), decision.get("era_tag"),
             decision.get("topic_match_score"), r["paper_id"]),
        )
    return dict(counts)
```

- [ ] **Step 4: Replace the screen stub in `rrl/cli.py`**

```python
@main.command()
@click.option("--dry-run", is_flag=True)
@click.pass_context
def screen(ctx, dry_run):
    """Apply topic/OA/quality filters; assign tier and era."""
    from rrl.db import connect, init_schema
    from rrl.screen.runner import run_screen
    conn = connect(ctx.obj["db"]); init_schema(conn)
    summary = run_screen(conn, dry_run=dry_run)
    for k, v in sorted(summary.items()):
        click.echo(f"{k}: {v}")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_screen_cli.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/screen/runner.py rrl/cli.py tests/test_screen_cli.py
click_check=$(true); git commit -m "feat: screen CLI applies filter chain + writes decisions"
```

---

## Task 20: CrossRef adapter (on-demand metadata fallback)

**Files:**
- Create: `rrl/search/crossref.py`
- Create: `tests/fixtures/crossref_doi.json`
- Create: `tests/test_search_crossref.py`

- [ ] **Step 1: Create fixture `tests/fixtures/crossref_doi.json`**

```json
{
  "message": {
    "DOI": "10.1/zzz",
    "title": ["A study of ChatGPT in higher education"],
    "container-title": ["Journal of Higher Ed"],
    "publisher": "Springer",
    "type": "journal-article",
    "issued": {"date-parts": [[2024]]},
    "author": [{"given": "Mei", "family": "Wang", "ORCID": "http://orcid.org/0000-0000-0000-0001"}],
    "language": "en",
    "abstract": "<jats:p>An empirical study of faculty attitudes.</jats:p>"
  }
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_search_crossref.py
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
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/test_search_crossref.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `rrl/search/crossref.py`**

```python
"""CrossRef on-demand DOI lookup for metadata gap-filling."""
from __future__ import annotations
import re

import requests

from rrl.search.base import RawRecord, normalize_doi

BASE = "https://api.crossref.org/works/"
_JATS = re.compile(r"<[^>]+>")

def _strip_jats(text: str | None) -> str | None:
    if text is None:
        return None
    return _JATS.sub("", text).strip() or None

def fetch_by_doi(session: requests.Session, doi: str, *, mailto: str) -> RawRecord | None:
    r = session.get(BASE + doi, params={"mailto": mailto})
    if r.status_code == 404:
        return None
    r.raise_for_status()
    m = r.json().get("message", {})
    parts = (m.get("issued") or {}).get("date-parts") or [[None]]
    year = parts[0][0] if parts and parts[0] else None
    return RawRecord(
        external_id=m.get("DOI", doi),
        doi=normalize_doi(m.get("DOI")),
        title=(m.get("title") or [""])[0],
        authors=[{"family": a.get("family", ""), "given": a.get("given", ""),
                  "orcid": a.get("ORCID")} for a in (m.get("author") or [])],
        year=year,
        venue=(m.get("container-title") or [None])[0],
        abstract=_strip_jats(m.get("abstract")),
        language=m.get("language"),
        raw_payload=m,
    )
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_search_crossref.py -v`
Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/search/crossref.py tests/fixtures/crossref_doi.json tests/test_search_crossref.py
git commit -m "feat: CrossRef on-demand DOI fetch with JATS stripping"
```

---

## Task 21: CORE adapter (on-demand PDF fallback)

**Files:**
- Create: `rrl/search/core_api.py`
- Create: `tests/test_search_core.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_search_core.py
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
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_search_core.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/search/core_api.py`**

```python
"""CORE on-demand search for OA PDFs when Unpaywall and OpenAlex links fail."""
from __future__ import annotations
import requests

BASE = "https://api.core.ac.uk/v3/search/works"

def _first_pdf(payload: dict) -> str | None:
    for item in payload.get("results", []):
        url = item.get("downloadUrl")
        if url:
            return url
    return None

def find_pdf_by_doi(session: requests.Session, doi: str, *, api_key: str) -> str | None:
    r = session.get(BASE, params={"q": f"doi:{doi}", "limit": 1},
                    headers={"Authorization": f"Bearer {api_key}"})
    r.raise_for_status()
    return _first_pdf(r.json())

def find_pdf_by_title(session: requests.Session, title: str, *, api_key: str) -> str | None:
    r = session.get(BASE, params={"q": f"title:\"{title}\"", "limit": 1},
                    headers={"Authorization": f"Bearer {api_key}"})
    r.raise_for_status()
    return _first_pdf(r.json())
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_search_core.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/search/core_api.py tests/test_search_core.py
git commit -m "feat: CORE on-demand PDF lookup by DOI or title"
```

---

## Task 22: PDF download module

**Files:**
- Create: `rrl/output/__init__.py`
- Create: `rrl/output/pdf.py`
- Create: `tests/fixtures/sample.pdf` (use a minimal valid PDF — see step 1)
- Create: `tests/test_output_pdf.py`

- [ ] **Step 1: Create the test PDF fixture**

Generate `tests/fixtures/sample.pdf` with:

```bash
python -c "open('tests/fixtures/sample.pdf','wb').write(b'%PDF-1.4\n' + b'x'*20000 + b'\n%%EOF')"
```

This is a 20KB file starting with the PDF magic bytes — large enough to pass the validation threshold.

- [ ] **Step 2: Write the failing test**

```python
# tests/test_output_pdf.py
from pathlib import Path
import responses
from rrl.db import connect, init_schema
from rrl.http import build_session
from rrl.output.pdf import validate_pdf_bytes, download_pdfs

def test_validate_rejects_non_pdf_magic():
    assert validate_pdf_bytes(b"<html>error</html>") is False

def test_validate_rejects_tiny_file():
    assert validate_pdf_bytes(b"%PDF-1.4\nshort") is False

def test_validate_accepts_real_pdf(fixtures_dir):
    data = (fixtures_dir / "sample.pdf").read_bytes()
    assert validate_pdf_bytes(data) is True

@responses.activate
def test_download_pdfs_writes_file_and_records_attempt(tmp_path, fixtures_dir):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,1,'https://x/y.pdf',1,'now','now')""")
    data = (fixtures_dir / "sample.pdf").read_bytes()
    responses.add(responses.GET, "https://x/y.pdf", body=data, status=200,
                  content_type="application/pdf")
    summary = download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs", core_api_key=None)
    assert summary["downloaded"] == 1
    row = conn.execute("SELECT pdf_status, pdf_filename FROM papers WHERE paper_id='p1'").fetchone()
    assert row["pdf_status"] == "downloaded"
    assert (tmp_path / "pdfs" / row["pdf_filename"]).exists()
    att = conn.execute("SELECT outcome FROM pdf_attempts").fetchone()[0]
    assert att == "ok"

@responses.activate
def test_download_marks_oa_link_dead_after_failed_attempts(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year,
        is_oa, oa_pdf_url, included, first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,1,'https://x/y.pdf',1,'now','now')""")
    responses.add(responses.GET, "https://x/y.pdf", body=b"<html>nope</html>", status=200)
    download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs", core_api_key=None)
    row = conn.execute("SELECT pdf_status FROM papers WHERE paper_id='p1'").fetchone()
    assert row["pdf_status"] == "oa_link_dead"

@responses.activate
def test_download_skips_already_downloaded(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year,
        is_oa, oa_pdf_url, included, pdf_status, pdf_filename,
        first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,1,'u',1,'downloaded','2023/p1.pdf','now','now')""")
    summary = download_pdfs(conn, build_session("t@e.com"), pdf_root=tmp_path / "pdfs", core_api_key=None)
    assert summary["downloaded"] == 0
    assert len(responses.calls) == 0
```

- [ ] **Step 3: Run test to verify failure**

Run: `pytest tests/test_output_pdf.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement `rrl/output/__init__.py`** (empty).

- [ ] **Step 5: Implement `rrl/output/pdf.py`**

```python
"""PDF download with magic-byte validation, retries, and attempt logging."""
from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

from rrl.search.core_api import find_pdf_by_doi, find_pdf_by_title

MIN_BYTES = 10 * 1024  # 10KB

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def validate_pdf_bytes(data: bytes) -> bool:
    if not data.startswith(b"%PDF-"):
        return False
    if len(data) < MIN_BYTES:
        return False
    return True

def _log_attempt(conn, paper_id, source, url, status, content_type, n_bytes, outcome, err=None):
    conn.execute(
        """INSERT INTO pdf_attempts (paper_id, source, url, http_status, content_type,
           bytes_received, outcome, error_message, attempted_at) VALUES (?,?,?,?,?,?,?,?,?)""",
        (paper_id, source, url, status, content_type, n_bytes, outcome, err, _now()),
    )

def _try_url(session, url, source, paper_id, conn, dest: Path) -> bool:
    try:
        r = session.get(url, timeout=60)
    except Exception as e:
        _log_attempt(conn, paper_id, source, url, None, None, 0, "http_error", str(e))
        return False
    data = r.content
    if r.status_code != 200:
        _log_attempt(conn, paper_id, source, url, r.status_code, r.headers.get("Content-Type"), len(data), "http_error")
        return False
    if not validate_pdf_bytes(data):
        _log_attempt(conn, paper_id, source, url, r.status_code, r.headers.get("Content-Type"), len(data), "not_pdf")
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    _log_attempt(conn, paper_id, source, url, r.status_code, r.headers.get("Content-Type"), len(data), "ok")
    return True

def download_pdfs(conn: sqlite3.Connection, session: requests.Session, *,
                  pdf_root: Path, core_api_key: str | None,
                  retry_failed: bool = False) -> dict:
    where = "included = 1 AND pdf_status IS NULL"
    if retry_failed:
        where = "included = 1 AND (pdf_status IS NULL OR pdf_status = 'oa_link_dead')"
    rows = conn.execute(
        f"SELECT paper_id, doi, title, year, oa_pdf_url FROM papers WHERE {where}"
    ).fetchall()
    counts = {"downloaded": 0, "failed": 0}
    for r in rows:
        pid, doi, title, year, oa_url = r["paper_id"], r["doi"], r["title"], r["year"], r["oa_pdf_url"]
        dest = pdf_root / str(year) / f"{pid}.pdf"
        urls = []
        if oa_url:
            urls.append(("oa", oa_url))
        if doi and core_api_key:
            core_url = find_pdf_by_doi(session, doi, api_key=core_api_key)
            if core_url:
                urls.append(("core_doi", core_url))
        if title and core_api_key:
            core_url = find_pdf_by_title(session, title, api_key=core_api_key)
            if core_url:
                urls.append(("core_title", core_url))
        ok = False
        for source, url in urls:
            if _try_url(session, url, source, pid, conn, dest):
                ok = True
                break
        if ok:
            rel = str(dest.relative_to(pdf_root))
            conn.execute(
                "UPDATE papers SET pdf_filename=?, pdf_status='downloaded', last_updated_at=datetime('now') WHERE paper_id=?",
                (rel, pid),
            )
            counts["downloaded"] += 1
        else:
            conn.execute(
                "UPDATE papers SET pdf_status='oa_link_dead', last_updated_at=datetime('now') WHERE paper_id=?",
                (pid,),
            )
            counts["failed"] += 1
    return counts
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_output_pdf.py -v`
Expected: 6 passed.

- [ ] **Step 7: Commit**

```bash
git add rrl/output/ tests/fixtures/sample.pdf tests/test_output_pdf.py
git commit -m "feat: PDF download module with validation + attempt logging"
```

---

## Task 23: Matrix xlsx writer

**Files:**
- Create: `rrl/output/matrix.py`
- Create: `tests/test_output_matrix.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_output_matrix.py
import json
from pathlib import Path
from openpyxl import load_workbook
from rrl.db import connect, init_schema
from rrl.output.matrix import write_matrix, MATRIX_COLUMNS

def _seed(conn, pid, tier, **kw):
    base = dict(
        paper_id=pid, title="Title", authors_json=json.dumps([{"family":"S","given":"J"}]),
        year=2023, era_tag="post_chatgpt", venue="V", publisher="Springer",
        work_type="journal-article", doi="10.1/x", language="en",
        is_in_doaj=1, is_peer_reviewed=1, is_oa=1, oa_status="gold",
        citation_count=5, topic_match_score=3.0,
        included=1, quality_tier=tier,
        pdf_filename="2023/x.pdf", pdf_status="downloaded",
        first_seen_at="now", last_updated_at="now",
    )
    base.update(kw)
    keys = ",".join(base.keys()); qs = ",".join(["?"] * len(base))
    conn.execute(f"INSERT INTO papers ({keys}) VALUES ({qs})", tuple(base.values()))

def test_matrix_has_two_sheets_and_expected_columns(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    _seed(conn, "p1", "high_confidence")
    _seed(conn, "p2", "review_needed", title="Other", pdf_filename="2023/y.pdf")
    out = tmp_path / "out/matrix.xlsx"
    write_matrix(conn, out)
    wb = load_workbook(out)
    assert "high_confidence" in wb.sheetnames
    assert "review_needed" in wb.sheetnames
    hc = wb["high_confidence"]
    headers = [c.value for c in hc[1]]
    assert headers == MATRIX_COLUMNS
    assert hc.cell(row=2, column=1).value == "p1"
    rn = wb["review_needed"]
    assert rn.cell(row=2, column=1).value == "p2"

def test_matrix_excludes_unincluded_and_undownloaded_and_merged(tmp_path):
    conn = connect(tmp_path / "rrl.sqlite"); init_schema(conn)
    _seed(conn, "p1", "high_confidence")
    _seed(conn, "p_excluded", "high_confidence", included=0)
    _seed(conn, "p_no_pdf", "high_confidence", pdf_status="oa_link_dead", pdf_filename=None)
    _seed(conn, "p_merged", "high_confidence")
    conn.execute("INSERT INTO paper_merges (loser_id, winner_id, merged_at, merged_by) VALUES ('p_merged','p1','now','manual')")
    out = tmp_path / "out/matrix.xlsx"
    write_matrix(conn, out)
    wb = load_workbook(out)
    hc = wb["high_confidence"]
    ids = [hc.cell(row=i, column=1).value for i in range(2, hc.max_row + 1)]
    assert ids == ["p1"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_output_matrix.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/output/matrix.py`**

```python
"""Write the two-sheet xlsx matrix from the papers table."""
from __future__ import annotations
import json
import sqlite3
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, Alignment
from openpyxl.utils import get_column_letter

MATRIX_COLUMNS = [
    "paper_id", "title", "authors", "year", "era_tag", "venue", "publisher",
    "work_type", "doi", "language", "is_in_doaj", "is_peer_reviewed",
    "is_oa", "oa_status", "citation_count", "topic_match_score",
    "pdf_filename", "source_apis", "abstract",
]

def _yes_no_na(v):
    if v is None:
        return "N/A"
    return "Yes" if v else "No"

def _authors_str(authors_json: str) -> str:
    try:
        authors = json.loads(authors_json or "[]")
    except Exception:
        return ""
    parts = []
    for a in authors:
        family = a.get("family") or ""
        given = (a.get("given") or "").strip()
        initial = f", {given[0]}." if given else ""
        parts.append(f"{family}{initial}".strip(", "))
    return "; ".join(parts)

def _source_apis(conn: sqlite3.Connection, paper_id: str) -> str:
    rows = conn.execute(
        """SELECT DISTINCT rr.adapter FROM raw_records rr
           JOIN paper_sources ps ON ps.raw_id = rr.raw_id
           WHERE ps.paper_id = ?""",
        (paper_id,),
    ).fetchall()
    return ",".join(sorted({r["adapter"] for r in rows}))

def _row_values(conn, p) -> list:
    return [
        p["paper_id"], p["title"], _authors_str(p["authors_json"]),
        p["year"], p["era_tag"], p["venue"], p["publisher"],
        p["work_type"], p["doi"], p["language"],
        _yes_no_na(p["is_in_doaj"]), _yes_no_na(p["is_peer_reviewed"]),
        _yes_no_na(p["is_oa"]), p["oa_status"],
        p["citation_count"], p["topic_match_score"],
        p["pdf_filename"], _source_apis(conn, p["paper_id"]), p["abstract"],
    ]

QUERY = """
SELECT * FROM papers
WHERE included = 1
  AND pdf_status = 'downloaded'
  AND paper_id NOT IN (SELECT loser_id FROM paper_merges)
  AND quality_tier = ?
ORDER BY year DESC, title
"""

def _write_sheet(ws, conn, tier: str) -> None:
    ws.append(MATRIX_COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for p in conn.execute(QUERY, (tier,)).fetchall():
        ws.append(_row_values(conn, p))
        if p["doi"]:
            ws.cell(row=ws.max_row, column=MATRIX_COLUMNS.index("doi") + 1).hyperlink = f"https://doi.org/{p['doi']}"
        if p["pdf_filename"]:
            ws.cell(row=ws.max_row, column=MATRIX_COLUMNS.index("pdf_filename") + 1).hyperlink = f"pdfs/{p['pdf_filename']}"
    # Auto-fit column widths (cap abstract at 60).
    for col_idx, name in enumerate(MATRIX_COLUMNS, start=1):
        letter = get_column_letter(col_idx)
        if name == "abstract":
            ws.column_dimensions[letter].width = 60
            for c in ws[letter][1:]:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        else:
            max_len = max((len(str(c.value or "")) for c in ws[letter]), default=10)
            ws.column_dimensions[letter].width = min(max_len + 2, 50)

def write_matrix(conn: sqlite3.Connection, out_path: Path) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    # Remove default sheet, add named ones in correct order.
    default = wb.active
    wb.remove(default)
    hc = wb.create_sheet("high_confidence")
    rn = wb.create_sheet("review_needed")
    _write_sheet(hc, conn, "high_confidence")
    _write_sheet(rn, conn, "review_needed")
    wb.save(out_path)
    return {"high_confidence": hc.max_row - 1, "review_needed": rn.max_row - 1}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_output_matrix.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/output/matrix.py tests/test_output_matrix.py
git commit -m "feat: two-sheet xlsx matrix writer with formatting + hyperlinks"
```

---

## Task 24: README writer (auto-generated appendix only)

**Files:**
- Create: `rrl/output/readme.py`
- Create: `tests/test_output_readme.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_output_readme.py
from pathlib import Path
import pytest
from rrl.output.readme import update_appendix, BEGIN_MARK, END_MARK, MissingMarkers

def test_refuses_when_markers_missing(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("# No markers here\n", encoding="utf-8")
    with pytest.raises(MissingMarkers):
        update_appendix(p, "new content")
    # Unchanged.
    assert p.read_text(encoding="utf-8") == "# No markers here\n"

def test_replaces_only_between_markers(tmp_path):
    p = tmp_path / "README.md"
    original = (
        "# Header\n\nIntro text.\n\n"
        f"{BEGIN_MARK}\n_old appendix_\n{END_MARK}\n\nMore handwritten content.\n"
    )
    p.write_text(original, encoding="utf-8")
    update_appendix(p, "## Fresh\n\n_new content_")
    text = p.read_text(encoding="utf-8")
    assert "# Header" in text
    assert "More handwritten content." in text
    assert "_old appendix_" not in text
    assert "_new content_" in text
    # Markers still present.
    assert BEGIN_MARK in text and END_MARK in text

def test_preserves_handwritten_bytes_outside_block(tmp_path):
    p = tmp_path / "README.md"
    handwritten_top = "# A\n\nSome\n  indented\n  content with trailing\n  whitespace   \n\n"
    handwritten_bot = "\n\n## Footer\n\nLine.\n"
    original = handwritten_top + f"{BEGIN_MARK}\nold\n{END_MARK}" + handwritten_bot
    p.write_text(original, encoding="utf-8")
    update_appendix(p, "new")
    text = p.read_text(encoding="utf-8")
    assert text.startswith(handwritten_top)
    assert text.endswith(handwritten_bot)
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_output_readme.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/output/readme.py`**

```python
"""Replace ONLY the content between BEGIN/END markers. Refuse if markers missing."""
from __future__ import annotations
from pathlib import Path

BEGIN_MARK = "<!-- BEGIN AUTO-GENERATED -->"
END_MARK = "<!-- END AUTO-GENERATED -->"

class MissingMarkers(RuntimeError):
    pass

def update_appendix(readme_path: Path, new_inner: str) -> None:
    text = readme_path.read_text(encoding="utf-8")
    if BEGIN_MARK not in text or END_MARK not in text:
        raise MissingMarkers(
            f"README.md must contain both {BEGIN_MARK} and {END_MARK}. "
            "Add them around the auto-generated section and re-run."
        )
    start = text.index(BEGIN_MARK) + len(BEGIN_MARK)
    end = text.index(END_MARK)
    if start > end:
        raise MissingMarkers(f"{BEGIN_MARK} must appear before {END_MARK}.")
    new_block = "\n" + new_inner.strip("\n") + "\n"
    new_text = text[:start] + new_block + text[end:]
    readme_path.write_text(new_text, encoding="utf-8")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_output_readme.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/output/readme.py tests/test_output_readme.py
git commit -m "feat: README appendix writer (marker-bounded, refuse if missing)"
```

---

## Task 25: Run manifest writer

**Files:**
- Create: `rrl/output/manifest.py`
- Create: `tests/test_output_manifest.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_output_manifest.py
import hashlib
import json
from pathlib import Path
from rrl.output.manifest import build_manifest, write_manifest

def test_build_manifest_has_required_fields(tmp_path):
    xlsx = tmp_path / "m.xlsx"
    xlsx.write_bytes(b"hello")
    m = build_manifest(
        counts={"raw_records": 10, "papers_after_dedup": 7, "papers_after_screen_included": 5, "papers_in_matrix": 4},
        runtimes={"harvest": 1, "dedup": 1, "enrich": 1, "screen": 1, "export": 1},
        matrix_path=xlsx,
    )
    assert m["pipeline_version"]
    assert m["matrix_file"] == "m.xlsx"
    assert m["matrix_sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert m["query_terms"]["year_min"] == 2020
    assert "query_terms_hash" in m

def test_write_manifest_round_trip(tmp_path):
    xlsx = tmp_path / "m.xlsx"; xlsx.write_bytes(b"x")
    out = tmp_path / "run_manifest.json"
    m = build_manifest(counts={}, runtimes={}, matrix_path=xlsx)
    write_manifest(out, m)
    loaded = json.loads(out.read_text())
    assert loaded["matrix_sha256"] == m["matrix_sha256"]
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_output_manifest.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/output/manifest.py`**

```python
"""Build and write output/run_manifest.json for reproducibility."""
from __future__ import annotations
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from rrl import __version__
from rrl.config import AI_TERMS, HE_TERMS, YEAR_MIN, YEAR_MAX
from rrl.search.base import QuerySpec, query_hash

SCHEMA_VERSION = 1
SCREEN_RULE_VERSION = "v1"

def _sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def build_manifest(*, counts: dict, runtimes: dict, matrix_path: Path) -> dict:
    spec = QuerySpec(ai_terms=AI_TERMS, he_terms=HE_TERMS, year_min=YEAR_MIN, year_max=YEAR_MAX)
    return {
        "schema_version": SCHEMA_VERSION,
        "pipeline_version": __version__,
        "run_id": str(uuid.uuid4()),
        "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "query_terms": {
            "ai_terms": AI_TERMS, "he_terms": HE_TERMS,
            "year_min": YEAR_MIN, "year_max": YEAR_MAX,
        },
        "query_terms_hash": query_hash(spec),
        "screen_rule_version": SCREEN_RULE_VERSION,
        "counts": counts,
        "stage_runtimes_seconds": runtimes,
        "matrix_file": matrix_path.name,
        "matrix_sha256": _sha256_file(matrix_path),
    }

def write_manifest(out_path: Path, manifest: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_output_manifest.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add rrl/output/manifest.py tests/test_output_manifest.py
git commit -m "feat: run_manifest.json builder + writer"
```

---

## Task 26: Export command (wire PDF + matrix + readme + manifest)

**Files:**
- Create: `rrl/output/runner.py`
- Modify: `rrl/cli.py` (replace export stub)
- Create: `tests/test_export_cli.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_export_cli.py
import json
import responses
from pathlib import Path
from click.testing import CliRunner
from rrl.cli import main
from rrl.db import connect, init_schema
from rrl.output.readme import BEGIN_MARK, END_MARK

@responses.activate
def test_export_creates_matrix_manifest_pdfs_and_updates_readme(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    conn.execute("""INSERT INTO papers (paper_id, title, authors_json, year, era_tag, language,
        is_oa, oa_pdf_url, is_peer_reviewed, work_type, publisher,
        included, quality_tier, first_seen_at, last_updated_at)
        VALUES ('p1','T','[]',2023,'post_chatgpt','en',1,'https://x/y.pdf',1,'journal-article','Springer',
                1,'high_confidence','now','now')""")
    pdf_bytes = (fixtures_dir / "sample.pdf").read_bytes()
    responses.add(responses.GET, "https://x/y.pdf", body=pdf_bytes,
                  content_type="application/pdf", status=200)
    # README with markers.
    (tmp_path / "README.md").write_text(
        f"# A\n\nIntro.\n\n{BEGIN_MARK}\nold\n{END_MARK}\n\nFooter.\n", encoding="utf-8")
    r = CliRunner().invoke(main, ["export"])
    assert r.exit_code == 0, r.output
    assert (tmp_path / "output/rrl_matrix.xlsx").exists()
    assert (tmp_path / "output/run_manifest.json").exists()
    pdfs = list((tmp_path / "pdfs").rglob("*.pdf"))
    assert len(pdfs) == 1
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Run statistics" in readme or "Last run" in readme
    assert "# A" in readme and "Footer." in readme
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_export_cli.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `rrl/output/runner.py`**

```python
"""End-to-end export: PDFs → xlsx → manifest → README appendix."""
from __future__ import annotations
import sqlite3
import time
from pathlib import Path

import requests

from rrl.output.pdf import download_pdfs
from rrl.output.matrix import write_matrix
from rrl.output.readme import update_appendix
from rrl.output.manifest import build_manifest, write_manifest

def _counts(conn: sqlite3.Connection) -> dict:
    def n(sql: str, *a) -> int:
        return conn.execute(sql, a).fetchone()[0]
    return {
        "raw_records": n("SELECT COUNT(*) FROM raw_records"),
        "papers_after_dedup": n("SELECT COUNT(*) FROM papers"),
        "papers_after_screen_included": n("SELECT COUNT(*) FROM papers WHERE included = 1"),
        "papers_in_matrix": n(
            """SELECT COUNT(*) FROM papers
               WHERE included = 1 AND pdf_status = 'downloaded'
               AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"""
        ),
        "high_confidence": n("SELECT COUNT(*) FROM papers WHERE quality_tier='high_confidence' AND pdf_status='downloaded' AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"),
        "review_needed": n("SELECT COUNT(*) FROM papers WHERE quality_tier='review_needed' AND pdf_status='downloaded' AND paper_id NOT IN (SELECT loser_id FROM paper_merges)"),
        "excluded_off_topic": n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='off_topic'"),
        "excluded_not_oa":    n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='not_oa'"),
        "excluded_non_english": n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='non_english'"),
        "excluded_k12_only":  n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='k12_only'"),
        "excluded_wrong_date": n("SELECT COUNT(*) FROM papers WHERE exclusion_reason='wrong_date'"),
        "post_chatgpt": n("SELECT COUNT(*) FROM papers WHERE era_tag='post_chatgpt' AND included=1"),
        "pre_chatgpt":  n("SELECT COUNT(*) FROM papers WHERE era_tag='pre_chatgpt'  AND included=1"),
    }

def _format_appendix(counts: dict, runtimes: dict, run_at: str) -> str:
    lines = [
        "## Run statistics",
        "",
        f"_Last run: {run_at}_",
        "",
        "**Corpus summary**",
        f"- raw_records: {counts['raw_records']}",
        f"- after dedup: {counts['papers_after_dedup']}",
        f"- after screen (included): {counts['papers_after_screen_included']}",
        f"- in matrix: {counts['papers_in_matrix']}",
        "",
        "**By quality tier**",
        f"- high_confidence: {counts['high_confidence']}",
        f"- review_needed: {counts['review_needed']}",
        "",
        "**By era**",
        f"- post_chatgpt: {counts['post_chatgpt']}",
        f"- pre_chatgpt: {counts['pre_chatgpt']}",
        "",
        "**Exclusions**",
        f"- off_topic: {counts['excluded_off_topic']}",
        f"- not_oa: {counts['excluded_not_oa']}",
        f"- non_english: {counts['excluded_non_english']}",
        f"- k12_only: {counts['excluded_k12_only']}",
        f"- wrong_date: {counts['excluded_wrong_date']}",
        "",
        "**Stage runtimes (seconds)**",
        *(f"- {k}: {v:.1f}" for k, v in runtimes.items()),
    ]
    return "\n".join(lines)

def run_export(db: Path, *, session: requests.Session, pdf_root: Path, matrix_path: Path,
               manifest_path: Path, readme_path: Path, core_api_key: str | None,
               retry_failed: bool = False) -> dict:
    from rrl.db import connect, init_schema
    from datetime import datetime, timezone
    conn = connect(db); init_schema(conn)

    runtimes: dict[str, float] = {}
    t0 = time.monotonic()
    pdf_summary = download_pdfs(conn, session, pdf_root=pdf_root, core_api_key=core_api_key,
                                retry_failed=retry_failed)
    runtimes["export_pdf"] = time.monotonic() - t0

    t0 = time.monotonic()
    matrix_counts = write_matrix(conn, matrix_path)
    runtimes["export_matrix"] = time.monotonic() - t0

    counts = _counts(conn)
    manifest = build_manifest(counts=counts, runtimes=runtimes, matrix_path=matrix_path)
    write_manifest(manifest_path, manifest)

    appendix = _format_appendix(counts, runtimes, manifest["run_at_utc"])
    update_appendix(readme_path, appendix)
    return {"pdfs": pdf_summary, "matrix": matrix_counts, "counts": counts}
```

- [ ] **Step 4: Replace the export stub in `rrl/cli.py`**

```python
@main.command()
@click.option("--retry-failed", is_flag=True)
@click.pass_context
def export(ctx, retry_failed):
    """Download PDFs, write xlsx + manifest, update README appendix."""
    from rrl.config import Settings
    from rrl.http import build_session
    from rrl.output.runner import run_export
    settings = Settings.from_env()
    sess = build_session(settings.openalex_email)
    summary = run_export(
        ctx.obj["db"],
        session=sess,
        pdf_root=Path("pdfs"),
        matrix_path=Path("output/rrl_matrix.xlsx"),
        manifest_path=Path("output/run_manifest.json"),
        readme_path=Path("README.md"),
        core_api_key=settings.core_api_key,
        retry_failed=retry_failed,
    )
    click.echo(json.dumps(summary, indent=2, default=str))
```

(Also add `import json` at the top of `cli.py` if not already present.)

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_export_cli.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/output/runner.py rrl/cli.py tests/test_export_cli.py
git commit -m "feat: export CLI wires PDFs + xlsx + manifest + README appendix"
```

---

## Task 27: `rrl all` and `rrl status` commands

**Files:**
- Modify: `rrl/cli.py` (replace the `all` and `status` stubs)
- Create: `tests/test_cli_all_status.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_cli_all_status.py
from click.testing import CliRunner
from pathlib import Path
from rrl.cli import main
from rrl.db import connect, init_schema

def test_status_reports_zero_counts_on_empty_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    connect(tmp_path / "data/rrl.sqlite").executescript("")  # ensure dir
    init_schema(connect(tmp_path / "data/rrl.sqlite"))
    r = CliRunner().invoke(main, ["status"])
    assert r.exit_code == 0
    assert "raw_records" in r.output
    assert "papers" in r.output

def test_status_paper_shows_lifecycle(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    conn = connect(tmp_path / "data/rrl.sqlite"); init_schema(conn)
    conn.execute("INSERT INTO papers (paper_id, title, authors_json, year, first_seen_at, last_updated_at) VALUES ('p1','T','[]',2023,'now','now')")
    r = CliRunner().invoke(main, ["status", "--paper", "p1"])
    assert r.exit_code == 0
    assert "p1" in r.output

def test_all_runs_each_stage_in_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    called: list[str] = []
    import rrl.cli as cli_mod

    def fake_harvest(db, only=None): called.append("harvest"); return {}
    def fake_dedup(conn): called.append("dedup"); return {"raw_records": 0, "papers_created": 0}
    def fake_enrich_oa(conn): called.append("openalex_flags"); return {}
    def fake_enrich_doaj(conn, sess): called.append("doaj"); return {}
    def fake_enrich_unp(conn, sess, email): called.append("unpaywall"); return {}
    def fake_screen(conn, dry_run=False): called.append("screen"); return {}
    def fake_export(**kw): called.append("export"); return {"counts": {}}

    monkeypatch.setattr("rrl.harvest.harvest", fake_harvest)
    monkeypatch.setattr("rrl.dedup.grouping.run_dedup", fake_dedup)
    monkeypatch.setattr("rrl.enrich.openalex_flags.enrich_from_openalex_payloads", fake_enrich_oa)
    monkeypatch.setattr("rrl.enrich.doaj.enrich_papers_with_doaj", fake_enrich_doaj)
    monkeypatch.setattr("rrl.enrich.unpaywall.enrich_papers_with_unpaywall", fake_enrich_unp)
    monkeypatch.setattr("rrl.screen.runner.run_screen", fake_screen)
    monkeypatch.setattr("rrl.output.runner.run_export", fake_export)

    r = CliRunner().invoke(main, ["all", "--skip", ""])
    assert r.exit_code == 0, r.output
    assert called == ["harvest", "dedup", "openalex_flags", "doaj", "unpaywall", "screen", "export"]

def test_all_respects_skip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")
    called: list[str] = []
    monkeypatch.setattr("rrl.harvest.harvest", lambda db, only=None: called.append("harvest") or {})
    monkeypatch.setattr("rrl.dedup.grouping.run_dedup", lambda c: called.append("dedup") or {"raw_records": 0, "papers_created": 0})
    monkeypatch.setattr("rrl.enrich.openalex_flags.enrich_from_openalex_payloads", lambda c: called.append("openalex_flags") or {})
    monkeypatch.setattr("rrl.enrich.doaj.enrich_papers_with_doaj", lambda c, s: called.append("doaj") or {})
    monkeypatch.setattr("rrl.enrich.unpaywall.enrich_papers_with_unpaywall", lambda c, s, e: called.append("unpaywall") or {})
    monkeypatch.setattr("rrl.screen.runner.run_screen", lambda c, dry_run=False: called.append("screen") or {})
    monkeypatch.setattr("rrl.output.runner.run_export", lambda **k: called.append("export") or {"counts": {}})

    r = CliRunner().invoke(main, ["all", "--skip", "harvest,export"])
    assert r.exit_code == 0, r.output
    assert "harvest" not in called and "export" not in called
    assert "dedup" in called and "screen" in called
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_cli_all_status.py -v`
Expected: FAIL.

- [ ] **Step 3: Replace `run_all` in `rrl/cli.py`**

Locate the existing `run_all` stub and replace its body:

```python
@main.command(name="all")
@click.option("--skip", default="", help="Comma-separated stage names to skip")
@click.pass_context
def run_all(ctx, skip):
    """Run all stages in order; resumable."""
    from rrl.config import Settings
    from rrl.db import connect, init_schema
    from rrl.http import build_session
    skipped = {s.strip() for s in skip.split(",") if s.strip()}

    if "harvest" not in skipped:
        from rrl.harvest import harvest as run_harvest
        click.echo("== harvest ==")
        run_harvest(ctx.obj["db"])

    db = ctx.obj["db"]
    conn = connect(db); init_schema(conn)

    if "dedup" not in skipped:
        from rrl.dedup.grouping import run_dedup
        click.echo("== dedup ==")
        click.echo(run_dedup(conn))

    if "enrich" not in skipped:
        settings = Settings.from_env()
        sess = build_session(settings.openalex_email)
        from rrl.enrich.openalex_flags import enrich_from_openalex_payloads
        from rrl.enrich.doaj import enrich_papers_with_doaj
        from rrl.enrich.unpaywall import enrich_papers_with_unpaywall
        click.echo("== enrich ==")
        enrich_from_openalex_payloads(conn)
        enrich_papers_with_doaj(conn, sess)
        enrich_papers_with_unpaywall(conn, sess, settings.openalex_email)

    if "screen" not in skipped:
        from rrl.screen.runner import run_screen
        click.echo("== screen ==")
        click.echo(run_screen(conn))

    if "export" not in skipped:
        settings = Settings.from_env()
        sess = build_session(settings.openalex_email)
        from rrl.output.runner import run_export
        click.echo("== export ==")
        run_export(
            db,
            session=sess,
            pdf_root=Path("pdfs"),
            matrix_path=Path("output/rrl_matrix.xlsx"),
            manifest_path=Path("output/run_manifest.json"),
            readme_path=Path("README.md"),
            core_api_key=settings.core_api_key,
        )
```

- [ ] **Step 4: Replace `status` in `rrl/cli.py`**

```python
@main.command()
@click.option("--paper", default=None, help="Show full lifecycle of one paper_id")
@click.pass_context
def status(ctx, paper):
    """Show per-stage counts and last-run timestamps."""
    from rrl.db import connect, init_schema
    db = ctx.obj["db"]
    if not db.exists():
        click.echo(f"No database at {db}. Run `rrl harvest` to create it.")
        return
    conn = connect(db); init_schema(conn)
    if paper:
        row = conn.execute("SELECT * FROM papers WHERE paper_id=?", (paper,)).fetchone()
        if not row:
            click.echo(f"No paper with id {paper}")
            return
        for k in row.keys():
            click.echo(f"{k}: {row[k]}")
        sources = conn.execute(
            """SELECT rr.adapter, rr.external_id FROM paper_sources ps
               JOIN raw_records rr ON rr.raw_id = ps.raw_id WHERE ps.paper_id=?""",
            (paper,),
        ).fetchall()
        click.echo("sources: " + ", ".join(f"{s['adapter']}:{s['external_id']}" for s in sources))
        return
    n = lambda sql, *a: conn.execute(sql, a).fetchone()[0]
    click.echo(f"raw_records: {n('SELECT COUNT(*) FROM raw_records')}")
    click.echo(f"papers: {n('SELECT COUNT(*) FROM papers')}")
    click.echo(f"papers included: {n('SELECT COUNT(*) FROM papers WHERE included = 1')}")
    click.echo(f"papers downloaded: {n('SELECT COUNT(*) FROM papers WHERE pdf_status = ?', 'downloaded')}")
    click.echo("search_runs:")
    for r in conn.execute("SELECT adapter, status, finished_at, records_new FROM search_runs ORDER BY started_at DESC").fetchall():
        click.echo(f"  {r['adapter']:<10} {r['status']:<7} {r['finished_at'] or '':<28} new={r['records_new']}")
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_cli_all_status.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add rrl/cli.py tests/test_cli_all_status.py
git commit -m "feat: `rrl all` orchestration + `rrl status` with per-paper drilldown"
```

---

## Task 28: End-to-end smoke test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_e2e.py
"""End-to-end smoke test: every stage runs against canned HTTP responses,
producing a real xlsx + manifest + README appendix on disk."""
import json
import responses
from openpyxl import load_workbook
from click.testing import CliRunner
from pathlib import Path
from rrl.cli import main
from rrl.output.readme import BEGIN_MARK, END_MARK

@responses.activate
def test_full_pipeline_smoke(tmp_path, monkeypatch, fixtures_dir):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENALEX_EMAIL", "t@e.com")

    oa1 = json.loads((fixtures_dir / "openalex_page1.json").read_text())
    oa2 = json.loads((fixtures_dir / "openalex_page2.json").read_text())
    eric = json.loads((fixtures_dir / "eric_response.json").read_text())
    eric_empty = {"response": {"numFound": 2, "start": 2000, "docs": []}}
    s2 = json.loads((fixtures_dir / "s2_bulk_response.json").read_text())
    s2_empty = {"token": None, "data": []}
    responses.add(responses.GET, "https://api.openalex.org/works", json=oa1)
    responses.add(responses.GET, "https://api.openalex.org/works", json=oa2)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=eric)
    responses.add(responses.GET, "https://api.ies.ed.gov/eric/", json=eric_empty)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=s2)
    responses.add(responses.GET, "https://api.semanticscholar.org/graph/v1/paper/search/bulk", json=s2_empty)

    # Enrich: DOAJ + Unpaywall for any DOI we might see.
    responses.add(responses.GET, "https://doaj.org/api/v3/search/journals/issn:1234-5678",
                  json={"results": [{"id": "abc"}]}, status=200)
    for doi in ("10.1/aaa", "10.1/ccc", "10.1/zzz"):
        responses.add(responses.GET, f"https://api.unpaywall.org/v2/{doi}",
                      json={"best_oa_location": {"url_for_pdf": f"https://x/{doi.replace('/','_')}.pdf"}},
                      status=200)

    # PDFs: return valid bytes for the URLs above.
    pdf_bytes = (fixtures_dir / "sample.pdf").read_bytes()
    for doi in ("10.1/aaa", "10.1/ccc", "10.1/zzz"):
        responses.add(responses.GET, f"https://x/{doi.replace('/','_')}.pdf",
                      body=pdf_bytes, content_type="application/pdf", status=200)
    # OpenAlex's own oa pdf for W111/W333 (fallback path if Unpaywall is bypassed)
    responses.add(responses.GET, "https://example.com/a.pdf", body=pdf_bytes,
                  content_type="application/pdf", status=200)
    responses.add(responses.GET, "https://example.com/c.pdf", body=pdf_bytes,
                  content_type="application/pdf", status=200)

    # README with markers must exist for the appendix writer.
    (tmp_path / "README.md").write_text(
        f"# RRL\n\nIntro.\n\n{BEGIN_MARK}\nplaceholder\n{END_MARK}\n", encoding="utf-8")

    runner = CliRunner()
    r = runner.invoke(main, ["all"])
    assert r.exit_code == 0, r.output

    matrix = tmp_path / "output/rrl_matrix.xlsx"
    manifest = tmp_path / "output/run_manifest.json"
    assert matrix.exists() and manifest.exists()
    wb = load_workbook(matrix)
    assert {"high_confidence", "review_needed"} <= set(wb.sheetnames)
    # At least one paper should make it through screen + download in this fixture set.
    rows = sum(s.max_row - 1 for s in (wb["high_confidence"], wb["review_needed"]))
    assert rows >= 1
    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "Run statistics" in readme
    # PDFs landed in pdfs/<year>/<id>.pdf
    pdfs = list((tmp_path / "pdfs").rglob("*.pdf"))
    assert len(pdfs) >= 1
    # Manifest is well-formed.
    m = json.loads(manifest.read_text())
    assert m["pipeline_version"]
    assert "counts" in m and "matrix_sha256" in m
```

- [ ] **Step 2: Run the smoke test**

Run: `pytest tests/test_e2e.py -v`
Expected: 1 passed. If failing, the failure is almost always a missing mocked HTTP route or a screening rule rejecting all fixtures. Adjust the fixture content (longer abstracts mentioning AI + university) or add the missing route — do NOT loosen production code to make this pass.

- [ ] **Step 3: Run the full test suite**

Run: `pytest -q`
Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "test: end-to-end smoke test through every stage"
```

---

## Task 29: README hand-written content + final polish

**Files:**
- Modify: `README.md` (expand hand-written sections)

- [ ] **Step 1: Expand `README.md` hand-written content**

Replace the README with a complete hand-written guide. Keep both markers intact and identical to the existing ones:

```markdown
# AI in Higher Education RRL Pipeline

A Python CLI that harvests, deduplicates, screens, and downloads **open-access** academic papers on AI / GenAI / ChatGPT / LLM **adoption** in higher education, then produces an RRL (review-of-related-literature) matrix in xlsx, the downloaded PDFs, and structured logs.

## What this is for

A reproducible, auditable corpus you can read and cite. Two output tiers — `high_confidence` and `review_needed` — surface borderline papers for manual judgment rather than silently dropping them.

## Scope

**Included.** Faculty using ChatGPT / LLMs to teach. Students using AI tools for coursework (surveys, attitudes, academic integrity, learning outcomes). Institutional policy / governance. AI-literacy programs that teach students *to use* AI.

**Excluded.** K-12-only contexts. AI/ML as a CS subject ("AI-as-curriculum"). Closed-access papers. Non-English papers.

**Date range:** 2020–2026, tagged `pre_chatgpt` (≤2022) and `post_chatgpt` (≥2023).

**Sources:** OpenAlex (primary), ERIC (education-specific gray lit), Semantic Scholar (broad). DOAJ + Unpaywall for quality + OA verification. CrossRef + CORE on demand.

## Setup

1. `python -m venv .venv && source .venv/bin/activate`
2. `pip install -e .[dev]`
3. `cp .env.example .env`, then fill in:
   - **`OPENALEX_EMAIL`** — required. Used in the User-Agent for OpenAlex and as the `email` param for Unpaywall.
   - **`SEMANTIC_SCHOLAR_API_KEY`** — *practically required.* Without a key, Semantic Scholar throttles to 1 req/s; an 8–15k-record harvest takes 3–4 hours just for S2. With a free key (https://www.semanticscholar.org/product/api), it drops to ~30 minutes. **The pipeline runs without it but logs a warning at startup.**
   - **`CORE_API_KEY`** — optional. Only used if Unpaywall + OpenAlex OA links both fail for a paper.

## Usage

```bash
rrl harvest              # search OpenAlex + ERIC + S2 → raw_records
rrl dedup                # build canonical papers (DOI → OpenAlex ID → signature)
rrl dedup --review       # write data/dedup_review.csv of likely duplicates
rrl dedup --merge L W    # manually merge paper L into paper W
rrl enrich               # DOAJ + Unpaywall + OpenAlex flags
rrl screen               # apply topic / OA / quality filters
rrl export               # download PDFs → output/rrl_matrix.xlsx + README appendix
rrl all                  # run every stage in order, resumable
rrl status               # counts and last-run timestamps
rrl status --paper PID   # full lifecycle of one paper
```

All stages are idempotent and resumable. A crash mid-stage = rerun the same command; nothing is duplicated.

## Output

- `output/rrl_matrix.xlsx` — two sheets, `high_confidence` and `review_needed`. Columns are bibliographic + quality flags. No NLP-extracted fields (methods/findings) — you fill those manually while reading.
- `pdfs/<year>/<paper_id>.pdf` — downloaded OA PDFs.
- `output/run_manifest.json` — pipeline version, query terms hash, counts, SHA-256 of the xlsx. For reproducibility.
- `logs/<stage>-YYYY-MM-DD.jsonl` — every search query, dedup decision, screening rejection, PDF attempt.
- `data/rrl.sqlite` — internal state (WAL mode). Inspectable; restartable.

## Limitations (read this before citing)

1. **OA-only corpus.** Significant closed-access literature in flagship journals (Computers & Education, Studies in Higher Education, Internet & Higher Education) is **not** in the matrix. This is *not* "the literature" — it is the open-access slice of it.
2. **Topic boundary is regex-based.** The K-12-only / AI-as-curriculum exclusions and the AI/HE inclusion are keyword filters. The `review_needed` tier exists to surface borderline calls for human judgment.
3. **Predatory-venue detection is best-effort.** No comprehensive free machine-readable list exists. We use DOAJ membership + a tiny blocklist of universally-acknowledged repeat offenders. Anything dubious lands in `review_needed`.
4. **Dedup has known gaps.** Preprint/journal pairs without shared DOIs may both appear; `rrl dedup --review` surfaces likely duplicates for manual merge.
5. **No content interpretation.** Methods, sample, findings, theoretical framework — those columns are intentionally absent. They cannot be auto-extracted reliably.
6. **English-only.** Significant work in Mandarin, Spanish, Portuguese, and other languages is excluded.

## Architecture

```
harvest → dedup → enrich → screen → export
   ↓        ↓        ↓        ↓        ↓
            SQLite (data/rrl.sqlite)
                                       → pdfs/<year>/*.pdf
                                       → output/rrl_matrix.xlsx
                                       → output/run_manifest.json
                                       → README.md (auto-generated block below)
                                       → logs/*.jsonl
```

Full design spec: `docs/superpowers/specs/2026-05-14-rrl-pipeline-design.md`.

## Development

```bash
pytest -q            # all tests; uses mocked HTTP via the `responses` library
ruff check rrl       # lint
mypy rrl             # types
```

No live API calls in CI. For a live smoke test: `rrl harvest --only=openalex --since 2026-01-01` (small slice).

<!-- BEGIN AUTO-GENERATED -->
_Auto-generated section. Populated by `rrl export`._
<!-- END AUTO-GENERATED -->
```

- [ ] **Step 2: Verify markers preserved by running `rrl export` once on a populated DB (if available), or skip and trust the test suite**

If you have already run the smoke test, this is unnecessary. Otherwise:

```bash
pytest tests/test_output_readme.py tests/test_export_cli.py -v
```

Expected: still passing.

- [ ] **Step 3: Final full suite + commit**

```bash
pytest -q
ruff check rrl
mypy rrl
git add README.md
git commit -m "docs: complete README hand-written sections"
```

---

## Done

Every stage from the spec is implemented, tested, and committed. The corpus can be produced end-to-end with `rrl all`. The README is honest about scope; the matrix is auditable via the SQLite DB and the run manifest.

