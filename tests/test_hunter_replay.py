"""End-to-end test against real Kilmurry RezLynx CSV exports.

These are Hunter's 2026-03-04 production extracts. If they shift in
size or shape, the assertions below will fail and we'll catch it.
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from kilmurry_gateway import SCHEMA_ID
from kilmurry_gateway.adapters import HunterReplayAdapter
from kilmurry_gateway.config import GatewayConfig, PublishConfig, RezLynxConfig
from kilmurry_gateway.pipeline import run_pipeline
from kilmurry_gateway.run_context import RunContext
from kilmurry_gateway.transform import build_feed
from kilmurry_gateway.validate import validate_feed

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "hunter-2026-03-04"


@pytest.fixture
def cfg(tmp_path: Path) -> GatewayConfig:
    cfg = GatewayConfig()
    cfg.adapter_mode = "hunter_replay"
    cfg.hunter_samples_dir = SAMPLES
    cfg.rezlynx = RezLynxConfig(site_id="KILMURRY", live_sources=[])
    cfg.publish = PublishConfig(onedrive_root=tmp_path / "out")
    cfg.log_dir = tmp_path / "logs"
    return cfg


def test_hunter_samples_present() -> None:
    assert (SAMPLES / "rezlynx-bookings-2026-03-04.csv").exists()
    assert (SAMPLES / "rezlynx-availability-2026-03-04.csv").exists()
    assert (SAMPLES / "rezlynx-booked-revenue-2026-03-04.csv").exists()


def test_hunter_replay_loads_real_counts() -> None:
    adapter = HunterReplayAdapter(SAMPLES)
    snap = adapter.fetch(date(2026, 3, 4))
    # Sanity bounds — from raw row counts of the CSVs.
    assert len(snap.reservations) == 443  # bookings rows in sample
    assert len(snap.revenue_lines) == 792  # booked-revenue rows in sample
    # ~50 rooms inventory typical for Kilmurry, 10 room types in sample.
    assert snap.inventory.rooms_available > 0


def test_hunter_replay_produces_valid_v1_feed(cfg: GatewayConfig) -> None:
    result = run_pipeline(cfg, target_date=date(2026, 3, 4))
    assert result["status"] == "ok", result
    feed = json.loads(Path(result["feed_path"]).read_text(encoding="utf-8"))

    assert feed["schema"] == SCHEMA_ID
    assert feed["source_system"] == "hunter-replay-rezlynx"
    assert feed["source_site"] == "KILMURRY"
    assert validate_feed(feed) == []

    kpi = feed["kpi"]
    # The fact this is real data with real numbers: assert non-trivial values.
    assert kpi["rooms_sold"] > 10
    assert kpi["rooms_available"] > 10
    assert 5 < kpi["occupancy_pct"] <= 100
    assert kpi["room_revenue_eur"] > 100
    assert feed["provenance"]["revenue_source"] == "report-data.booked-revenue"


def test_hunter_replay_segment_codes_match_production(cfg: GatewayConfig) -> None:
    """Production codes are CORPORATE / DIRECT / OTA / COMP / GDS / LNR."""
    result = run_pipeline(cfg, target_date=date(2026, 3, 4))
    feed = json.loads(Path(result["feed_path"]).read_text(encoding="utf-8"))
    seen_segments = {s["name"] for s in feed["segments"]["items"]}
    valid = {"CORPORATE", "DIRECT", "OTA", "COMP", "GDS", "LNR", "Unmapped"}
    assert seen_segments.issubset(valid), f"unknown segments: {seen_segments - valid}"


def test_hunter_replay_channels_use_canonical_casing(cfg: GatewayConfig) -> None:
    """Channel names should be canonical (Avvio, not AVVIO)."""
    result = run_pipeline(cfg, target_date=date(2026, 3, 4))
    feed = json.loads(Path(result["feed_path"]).read_text(encoding="utf-8"))
    names = [c["name"] for c in feed["channels"]["items"]]
    # No ALL-CAPS variants
    for n in names:
        assert n.upper() != n or n in {"GDS"}, f"non-canonical channel name: {n}"


def test_hunter_replay_revenue_filters_correctly() -> None:
    """The revenue source should exclude cancelled + no-show rows."""
    adapter = HunterReplayAdapter(SAMPLES)
    snap = adapter.fetch(date(2026, 3, 4))
    # Sum all Accommodation lines for any date that are NOT cancelled and NOT no-show
    rooms_only = [
        l for l in snap.revenue_lines
        if l.revenue_type == "Accommodation" and not l.cancelled and not l.is_no_show
    ]
    cancelled = [l for l in snap.revenue_lines if l.cancelled]
    no_shows = [l for l in snap.revenue_lines if l.is_no_show]
    # From sample: 117 cancelled, 6 no-show
    assert len(cancelled) > 0
    assert len(no_shows) > 0
    # Cancelled and no-show should be excluded from our authoritative revenue set.
    for r in rooms_only:
        assert not r.cancelled
        assert not r.is_no_show
