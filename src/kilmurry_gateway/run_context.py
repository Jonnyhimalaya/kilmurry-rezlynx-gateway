"""Shared per-run context: stable run_id, hostname, timing."""
from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def filename_timestamp(dt: datetime | None = None) -> str:
    """Filesystem-safe ISO8601 timestamp, e.g. 2026-05-11T180000Z."""
    dt = (dt or utcnow()).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H%M%SZ")


@dataclass
class RunContext:
    run_id: str = field(default_factory=lambda: f"gw-{uuid.uuid4().hex[:12]}")
    started_at: datetime = field(default_factory=utcnow)
    hostname: str = field(default_factory=socket.gethostname)

    def elapsed_seconds(self) -> float:
        return (utcnow() - self.started_at).total_seconds()
