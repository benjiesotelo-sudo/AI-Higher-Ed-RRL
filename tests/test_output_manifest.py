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
