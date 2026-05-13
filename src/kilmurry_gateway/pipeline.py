"""End-to-end pipeline: fetch -> transform -> validate -> publish."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from pathlib import Path

from .adapters import FetchError, HunterReplayAdapter, MockRezLynxAdapter, RezLynxAdapter
from .config import GatewayConfig
from .publish import PublishedArtifacts, publish_outputs
from .run_context import RunContext, utcnow
from .transform import build_feed, build_summary
from .validate import FeedValidationError, validate_feed

logger = logging.getLogger("kilmurry_gateway.pipeline")


def select_adapter(cfg: GatewayConfig) -> RezLynxAdapter:
    """Pick the adapter for the configured mode."""
    mode = cfg.adapter_mode
    if mode == "mock":
        logger.info("adapter.mock", extra={"event": "adapter.selected", "mode": "mock"})
        return MockRezLynxAdapter(site_id=cfg.site_id)

    if mode == "hunter_replay":
        logger.info(
            "adapter.hunter_replay",
            extra={"event": "adapter.selected", "mode": "hunter_replay", "samples_dir": str(cfg.hunter_samples_dir)},
        )
        return HunterReplayAdapter(cfg.hunter_samples_dir, site_id=cfg.site_id)

    if mode == "live":
        if not cfg.rezlynx.has_credentials():
            missing = []
            if "soap" in cfg.rezlynx.live_sources and not cfg.rezlynx.has_soap_credentials():
                missing.append("REZLYNX_PASSWORD")
            if "report_data" in cfg.rezlynx.live_sources and not cfg.rezlynx.has_report_data_credentials():
                missing.append("REZLYNX_REPORT_DATA_API_KEY")
            raise FetchError(
                f"live mode requires credentials; missing: {', '.join(missing)}"
            )
        # Lazy import so non-live modes don't pay the cost.
        from .adapters.composite import CompositeLiveAdapter
        logger.info(
            "adapter.live",
            extra={"event": "adapter.selected", "mode": "live", "sources": cfg.rezlynx.live_sources},
        )
        return CompositeLiveAdapter(cfg)

    raise FetchError(f"unknown adapter_mode={mode!r}; use mock | hunter_replay | live")


def default_target_date() -> date:
    return utcnow().date()


def run_pipeline(
    cfg: GatewayConfig,
    *,
    target_date: date | None = None,
    dry_run: bool = False,
) -> dict:
    """Execute fetch -> transform -> validate -> publish.

    Returns a result dict suitable for printing/logging.
    """
    run_ctx = RunContext()
    target = target_date or default_target_date()

    logger.info(
        "pipeline.start",
        extra={"event": "pipeline.start", "run_id": run_ctx.run_id, "target_date": target.isoformat(), "dry_run": dry_run},
    )

    adapter = select_adapter(cfg)
    try:
        snapshot = adapter.fetch(target)
    except FetchError as e:
        logger.error(
            "pipeline.fetch_failed",
            extra={"event": "pipeline.fetch_failed", "endpoint": e.endpoint, "error": str(e)},
        )
        # Per spec: do NOT publish a false-success JSON on fetch failure.
        return {
            "status": "fetch_failed",
            "run_id": run_ctx.run_id,
            "target_date": target.isoformat(),
            "error": str(e),
            "endpoint": e.endpoint,
        }

    feed = build_feed(
        snapshot,
        run_ctx=run_ctx,
        source_label=adapter.source_label,
        poll_interval_hours=cfg.poll_interval_hours,
    )

    errors = validate_feed(feed)
    if errors:
        logger.error(
            "pipeline.validation_failed",
            extra={"event": "pipeline.validation_failed", "errors": errors},
        )
        return {
            "status": "validation_failed",
            "run_id": run_ctx.run_id,
            "target_date": target.isoformat(),
            "errors": errors,
        }

    summary = build_summary(feed)

    if dry_run:
        logger.info("pipeline.dry_run_complete", extra={"event": "pipeline.dry_run_complete"})
        return {
            "status": "dry_run_ok",
            "run_id": run_ctx.run_id,
            "target_date": target.isoformat(),
            "feed_preview_keys": sorted(feed.keys()),
            "kpi": feed["kpi"],
            "operations": feed["operations"],
            "freshness": feed["freshness"],
            "confidence": feed["confidence"],
        }

    artifacts: PublishedArtifacts = publish_outputs(
        feed,
        summary,
        cfg=cfg,
        run_ctx=run_ctx,
        target_date=target,
    )

    logger.info(
        "pipeline.published",
        extra={
            "event": "pipeline.published",
            "run_id": run_ctx.run_id,
            "feed_path": str(artifacts.feed_path),
            "summary_path": str(artifacts.summary_path),
            "manifest_path": str(artifacts.manifest_path),
        },
    )

    return {
        "status": "ok",
        "run_id": run_ctx.run_id,
        "target_date": target.isoformat(),
        "feed_path": str(artifacts.feed_path),
        "summary_path": str(artifacts.summary_path),
        "manifest_path": str(artifacts.manifest_path),
        "feed_latest": str(artifacts.feed_latest) if artifacts.feed_latest else None,
        "summary_latest": str(artifacts.summary_latest) if artifacts.summary_latest else None,
        "freshness": feed["freshness"],
        "confidence": feed["confidence"],
        "elapsed_seconds": round(run_ctx.elapsed_seconds(), 3),
    }
