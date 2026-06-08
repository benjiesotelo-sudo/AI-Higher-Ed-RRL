"""Deterministic persistence + validation for MMAT appraisal (no model calls)."""
from __future__ import annotations

import json
import random
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


def _compute_5_5(components: dict) -> str:
    """MMAT 5.5 = weakest component: No if any applicable component is No;
    Can't-tell if any is cant_tell and none No; else Yes."""
    vals = list(components.values())
    if "no" in vals:
        return "no"
    if "cant_tell" in vals:
        return "cant_tell"
    return "yes"


def import_rate_answers(conn, work_path, answers_path, model, engine) -> dict:
    """Group answers by paper, require a complete criterion set, compute 5.5,
    UPSERT in one per-paper transaction, and roll the paper up to 'appraised'."""
    work = {json.loads(l)["work_id"]: json.loads(l)
            for l in Path(work_path).read_text().splitlines() if l.strip()}
    batch = Path(answers_path).name
    by_wid: dict = {}
    for line in Path(answers_path).read_text().splitlines():
        if line.strip():
            a = json.loads(line)
            by_wid.setdefault(a.get("work_id"), []).append(a)
    counts = {"persisted": 0, "flagged": 0, "rejected": 0}
    for wid, answers in by_wid.items():
        w = work.get(wid)
        if w is None:
            counts["rejected"] += len(answers)
            _log(conn, batch, wid, None, "rejected", "unknown work_id")
            continue
        rated = {a["criterion_id"]: a["rating"] for a in answers}
        if not set(w["criteria"]) <= set(rated) or any(v not in RATINGS for v in rated.values()):
            counts["rejected"] += len(answers)
            _log(conn, batch, wid, w["paper_id"], "rejected", "incomplete or bad rating")
            continue
        if w["mmat_category"] == "mixed_methods":
            components = {c: rated[c] for c in CRITERIA["qualitative"] + CRITERIA[w["mm_quant_family"]]}
            rated["5.5"] = _compute_5_5(components)
        coder, pv, pid = f"llm_pass_{w['pass']}", w["prompt_version"], w["paper_id"]
        ans_by_cid = {a["criterion_id"]: a for a in answers}
        conn.execute("BEGIN")
        for cid, rating in rated.items():
            a = ans_by_cid.get(cid, {"source_quote": "", "rationale": "computed (5.5)"})
            qp = 1 if quote_present(a.get("source_quote", ""), w["text"]) else 0
            conn.execute(
                "INSERT INTO mmat_appraisals (paper_id,coder,mmat_category,criterion_id,rating,"
                "rationale,source_quote,quote_verified,prompt_version,model,engine,created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(paper_id,coder,criterion_id,prompt_version) DO UPDATE SET "
                "rating=excluded.rating, rationale=excluded.rationale, source_quote=excluded.source_quote, "
                "quote_verified=excluded.quote_verified, model=excluded.model, created_at=excluded.created_at",
                (pid, coder, w["mmat_category"], cid, rating, a.get("rationale"),
                 a.get("source_quote"), qp, pv, model, engine, _now()))
        conn.execute("COMMIT")
        set_disposition(conn, pid, "appraised", f"{w['mmat_category']} ({coder})")
        counts["persisted"] += 1
        _log(conn, batch, wid, pid, "persisted", "")
    return counts


def status_counts(conn: sqlite3.Connection) -> dict:
    """Per-phase progress: disposition counts, import-log outcomes, reconciliation."""
    disp = {r[0]: r[1] for r in conn.execute(
        "SELECT disposition, COUNT(*) FROM mmat_dispositions GROUP BY disposition").fetchall()}
    log = {r[0]: r[1] for r in conn.execute(
        "SELECT outcome, COUNT(*) FROM mmat_import_log GROUP BY outcome").fetchall()}
    return {"dispositions": disp, "import_log": log,
            "reconciliation": reconcile_dispositions(conn)}


def assign_samples(conn: sqlite3.Connection, role: str, n: int, seed: int,
                   tier: str | None = None) -> list[str]:
    """Seeded, append-only sample membership; roles are mutually exclusive. When
    `tier` is given, draw only from that quality_tier and record it as the stratum
    (call once per stratum, topping `n` up, to build a stratified sample)."""
    existing = [r[0] for r in conn.execute(
        "SELECT paper_id FROM mmat_samples WHERE role=? ORDER BY paper_id", (role,)).fetchall()]
    if len(existing) >= n:
        return existing
    taken = {r[0] for r in conn.execute("SELECT paper_id FROM mmat_samples").fetchall()}
    tier_sql = " AND p.quality_tier=?" if tier else ""
    params = (tier,) if tier else ()
    pool = [r[0] for r in conn.execute(
        f"SELECT d.paper_id FROM mmat_dispositions d JOIN papers p ON p.paper_id=d.paper_id "
        f"WHERE d.disposition='ok' AND d.paper_id IN ({_IN_SCOPE}){tier_sql} "
        f"ORDER BY d.paper_id", params).fetchall() if r[0] not in taken]
    random.Random(seed).shuffle(pool)
    chosen = sorted(pool[:n - len(existing)])      # top up to n; existing membership is preserved
    for pid in chosen:
        conn.execute("INSERT INTO mmat_samples (paper_id,role,stratum,rng_seed,assigned_at) "
                     "VALUES (?,?,?,?,?)", (pid, role, tier, seed, _now()))
    return sorted(existing + chosen)
