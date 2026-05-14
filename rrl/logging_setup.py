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
