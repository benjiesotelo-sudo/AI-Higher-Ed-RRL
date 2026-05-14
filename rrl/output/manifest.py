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
