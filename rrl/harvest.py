"""Harvest orchestration: run adapters, persist to raw_records + search_runs."""
from __future__ import annotations
import dataclasses
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

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

def harvest(db_path: Path, *, only: list[str] | None = None, since: str | None = None) -> dict:
    settings = Settings.from_env()
    configure_logging("harvest", Path("logs"))
    log = get_logger()
    conn = connect(db_path)
    init_schema(conn)
    spec = QuerySpec(ai_terms=AI_TERMS, he_terms=HE_TERMS, year_min=YEAR_MIN, year_max=YEAR_MAX)
    if since is not None:
        year_min = int(since.split("-")[0])
        spec = dataclasses.replace(spec, year_min=year_min)
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
