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
