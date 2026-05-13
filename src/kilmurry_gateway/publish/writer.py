"""Write artifacts to the OneDrive-synced folder.

We do not call the Microsoft Graph API. OneDrive sync on the desktop is
responsible for the actual upload. From this code's perspective, the
"OneDrive" target is just a local path.

Writes are atomic: write to a `.tmp` then rename, so a partial file is
never visible to the consumer.
"""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..config import GatewayConfig
from ..run_context import RunContext, filename_timestamp, iso_utc


@dataclass
class PublishedArtifacts:
    feed_path: Path
    summary_path: Path
    manifest_path: Path
    feed_latest: Path | None
    summary_latest: Path | None


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    tmp.replace(path)


def _file_basename(target_date: date, ts: str) -> str:
    # Filename contract per spec: includes target date and run timestamp.
    return f"rezlynx-revenue-feed-{target_date.isoformat()}-{ts}"


def publish_outputs(
    feed: dict[str, Any],
    summary_html: str,
    *,
    cfg: GatewayConfig,
    run_ctx: RunContext,
    target_date: date,
) -> PublishedArtifacts:
    ts = filename_timestamp(run_ctx.started_at)

    feed_filename = _file_basename(target_date, ts) + ".json"
    summary_filename = f"rezlynx-summary-{target_date.isoformat()}-{ts}.html"
    manifest_filename = f"rezlynx-manifest-{target_date.isoformat()}-{ts}.json"

    feed_path = cfg.feeds_path() / feed_filename
    summary_path = cfg.summaries_path() / summary_filename
    manifest_path = cfg.manifests_path() / manifest_filename

    feed_bytes = json.dumps(feed, indent=2, ensure_ascii=False, sort_keys=False).encode("utf-8")
    _write_atomic(feed_path, feed_bytes)
    _write_atomic(summary_path, summary_html.encode("utf-8"))

    manifest = {
        "schema": "kilmurry.rezlynx.manifest.v1",
        "generated_at_utc": iso_utc(run_ctx.started_at),
        "run_id": run_ctx.run_id,
        "hostname": run_ctx.hostname,
        "target_date": target_date.isoformat(),
        "feed_file": feed_filename,
        "summary_file": summary_filename,
        "feed_bytes": len(feed_bytes),
        "elapsed_seconds": round(run_ctx.elapsed_seconds(), 3),
        "validation_warnings": feed.get("provenance", {}).get("validation_warnings", []),
        "freshness": feed.get("freshness"),
        "confidence": feed.get("confidence"),
        "kpi": feed.get("kpi"),
    }
    _write_atomic(manifest_path, json.dumps(manifest, indent=2).encode("utf-8"))

    feed_latest: Path | None = None
    summary_latest: Path | None = None
    if cfg.publish.write_latest_pointer:
        feed_latest = cfg.feeds_path() / "rezlynx-revenue-feed-latest.json"
        summary_latest = cfg.summaries_path() / "rezlynx-summary-latest.html"
        shutil.copy2(feed_path, feed_latest)
        shutil.copy2(summary_path, summary_latest)

    return PublishedArtifacts(
        feed_path=feed_path,
        summary_path=summary_path,
        manifest_path=manifest_path,
        feed_latest=feed_latest,
        summary_latest=summary_latest,
    )
