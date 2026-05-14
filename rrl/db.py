"""SQLite connection + schema setup. Raw SQL; no ORM."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
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
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create tables/indices if missing. Idempotent."""
    conn.executescript(DDL)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(papers)").fetchall()}
    for col in ("unpaywall_checked_at", "doaj_checked_at"):
        if col not in cols:
            conn.execute(f"ALTER TABLE papers ADD COLUMN {col} TEXT")
    existing = conn.execute(
        "SELECT version FROM schema_version WHERE version=?", (SCHEMA_VERSION,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
