"""Deterministic persistence + validation for MMAT appraisal (no model calls)."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rrl.appraise.engine import quote_present, CRITERIA

BUCKETS = set(CRITERIA) | {"not_assessable"}
RATINGS = {"yes", "no", "cant_tell"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def set_disposition(conn: sqlite3.Connection, paper_id: str,
                    disposition: str, detail: str = "") -> None:
    """Upsert one paper's disposition so a row can transition (ok -> appraised)."""
    conn.execute(
        "INSERT INTO mmat_dispositions (paper_id, disposition, detail, created_at) "
        "VALUES (?,?,?,?) "
        "ON CONFLICT(paper_id) DO UPDATE SET "
        "disposition=excluded.disposition, detail=excluded.detail, created_at=excluded.created_at",
        (paper_id, disposition, detail, _now()),
    )


_IN_SCOPE = ("SELECT paper_id FROM papers WHERE included=1 AND pdf_status='downloaded' "
             "AND pdf_filename IS NOT NULL AND paper_id NOT IN (SELECT loser_id FROM paper_merges)")


def reconcile_dispositions(conn: sqlite3.Connection) -> dict:
    """LEFT-JOIN reconciliation: every in-scope paper has exactly one disposition."""
    in_scope = {r[0] for r in conn.execute(_IN_SCOPE).fetchall()}
    rows = conn.execute(
        f"SELECT d.disposition, COUNT(*) FROM mmat_dispositions d "
        f"WHERE d.paper_id IN ({_IN_SCOPE}) GROUP BY d.disposition").fetchall()
    counts = {r[0]: r[1] for r in rows}
    dispositioned = sum(counts.values())
    return {"in_scope": len(in_scope), "dispositioned": dispositioned,
            "counts": counts, "balanced": dispositioned == len(in_scope)}


def _log(conn, batch, work_id, paper_id, outcome, reason=""):
    conn.execute("INSERT INTO mmat_import_log (batch,work_id,paper_id,outcome,reason,created_at) "
                 "VALUES (?,?,?,?,?,?)", (batch, work_id, paper_id, outcome, reason, _now()))


def import_classify_answers(conn, work_path, answers_path, model, engine) -> dict:
    """Validate classify answers against their work file, UPSERT, transition dispositions."""
    work = {json.loads(l)["work_id"]: json.loads(l)
            for l in Path(work_path).read_text().splitlines() if l.strip()}
    batch = Path(answers_path).name
    counts = {"persisted": 0, "flagged": 0, "rejected": 0}
    for line in Path(answers_path).read_text().splitlines():
        if not line.strip():
            continue
        a = json.loads(line)
        w = work.get(a.get("work_id"))
        if w is None or a.get("bucket") not in BUCKETS:
            counts["rejected"] += 1
            _log(conn, batch, a.get("work_id"), w and w["paper_id"], "rejected",
                 "unknown work_id" if w is None else "bad bucket")
            continue
        pid, coder, pv = w["paper_id"], f"llm_pass_{w['pass']}", w["prompt_version"]
        trigger = a.get("s1") in {"no", "cant_tell"} or a.get("s2") in {"no", "cant_tell"}
        flagged = 1 if (trigger or not quote_present(a.get("source_quote", ""), w["text"])) else 0
        conn.execute(
            "INSERT INTO mmat_classifications (paper_id,coder,mmat_category,mm_quant_family,"
            "s1,s2,rationale,source_quote,confidence,flagged,prompt_version,model,engine,created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(paper_id,coder,prompt_version) DO UPDATE SET "
            "mmat_category=excluded.mmat_category, mm_quant_family=excluded.mm_quant_family, "
            "s1=excluded.s1, s2=excluded.s2, rationale=excluded.rationale, "
            "source_quote=excluded.source_quote, confidence=excluded.confidence, "
            "flagged=excluded.flagged, model=excluded.model, engine=excluded.engine, "
            "created_at=excluded.created_at",
            (pid, coder, a["bucket"], a.get("mm_quant_family"), a.get("s1"), a.get("s2"),
             a.get("rationale"), a.get("source_quote"), a.get("confidence"), flagged,
             pv, model, engine, _now()))
        if trigger or a["bucket"] == "not_assessable":
            set_disposition(conn, pid, "not_assessable",
                            "s1/s2 trigger" if trigger else "classified not_assessable")
        counts["flagged" if flagged else "persisted"] += 1
        _log(conn, batch, a["work_id"], pid, "flagged" if flagged else "persisted", "")
    return counts
