"""Smoke tests for the full pipeline against the mock adapter."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from kilmurry_gateway import SCHEMA_ID
from kilmurry_gateway.config import GatewayConfig, PublishConfig, RezLynxConfig
from kilmurry_gateway.pipeline import run_pipeline
from kilmurry_gateway.validate import validate_feed


def _cfg(tmp_path: Path) -> GatewayConfig:
    cfg = GatewayConfig()
    cfg.adapter_mode = "mock"
    cfg.rezlynx = RezLynxConfig(site_id="KILMURRY", live_sources=[])
    cfg.publish = PublishConfig(onedrive_root=tmp_path / "out")
    cfg.log_dir = tmp_path / "logs"
    cfg.poll_interval_hours = 6
    return cfg


def test_pipeline_dry_run_returns_kpi(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = run_pipeline(cfg, target_date=date(2026, 5, 11), dry_run=True)
    assert result["status"] == "dry_run_ok"
    kpi = result["kpi"]
    assert kpi["rooms_available"] > 0
    assert 0 <= kpi["occupancy_pct"] <= 100
    assert kpi["revpar_eur"] >= 0


def test_pipeline_publishes_valid_feed(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = run_pipeline(cfg, target_date=date(2026, 5, 11))
    assert result["status"] == "ok", result

    feed_path = Path(result["feed_path"])
    assert feed_path.exists()
    feed = json.loads(feed_path.read_text(encoding="utf-8"))

    assert feed["schema"] == SCHEMA_ID
    assert feed["source_site"] == "KILMURRY"
    assert feed["freshness"]["status"] == "LIVE"
    assert feed["confidence"] in {"high", "medium", "low"}
    assert feed["kpi"]["rooms_sold"] >= 0
    assert validate_feed(feed) == []

    summary_path = Path(result["summary_path"])
    assert summary_path.exists()
    html = summary_path.read_text(encoding="utf-8")
    assert "Revenue Snapshot" in html
    assert "KILMURRY" in html

    manifest_path = Path(result["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["feed_file"] == feed_path.name
    assert manifest["target_date"] == "2026-05-11"


def test_pipeline_writes_latest_pointer(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    result = run_pipeline(cfg, target_date=date(2026, 5, 11))
    assert result["feed_latest"]
    assert Path(result["feed_latest"]).exists()
    assert Path(result["summary_latest"]).exists()


def test_pipeline_is_deterministic_for_seed(tmp_path: Path) -> None:
    """Same target_date + mock seed -> identical KPI block (stability)."""
    cfg1 = _cfg(tmp_path / "a")
    cfg2 = _cfg(tmp_path / "b")
    r1 = run_pipeline(cfg1, target_date=date(2026, 5, 11), dry_run=True)
    r2 = run_pipeline(cfg2, target_date=date(2026, 5, 11), dry_run=True)
    assert r1["kpi"] == r2["kpi"]
    assert r1["operations"] == r2["operations"]
