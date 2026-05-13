"""Logging that produces both human and JSONL streams.

Why JSONL: lets OpenClaw (or any downstream) tail/inspect runs structurally
without grepping prose. Each line is one event.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class JsonlFormatter(logging.Formatter):
    """Render log record as a single JSON line with stable keys."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401 - std lib
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Surface structured extras attached via `logger.info(..., extra={...})`.
        for k, v in record.__dict__.items():
            if k in {
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "msg", "name", "pathname", "process", "processName", "relativeCreated",
                "stack_info", "thread", "threadName", "message",
            }:
                continue
            try:
                json.dumps(v)
                payload[k] = v
            except TypeError:
                payload[k] = repr(v)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(log_dir: Path, level: str = "INFO", run_id: str | None = None) -> logging.Logger:
    """Set up root logger with human stderr handler + JSONL file handler.

    Returns the gateway-scoped logger.
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    # Wipe previously-installed handlers (re-runs in same process)
    for h in list(root.handlers):
        root.removeHandler(h)

    human = logging.StreamHandler(sys.stderr)
    human.setLevel(level)
    human.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s - %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%SZ",
        )
    )

    jsonl = logging.handlers.RotatingFileHandler(
        log_dir / "gateway.jsonl",
        maxBytes=2_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    jsonl.setLevel(level)
    jsonl.setFormatter(JsonlFormatter())

    root.addHandler(human)
    root.addHandler(jsonl)

    logger = logging.getLogger("kilmurry_gateway")
    if run_id:
        logger = logging.LoggerAdapter(logger, {"run_id": run_id})  # type: ignore[assignment]
    return logger  # type: ignore[return-value]
