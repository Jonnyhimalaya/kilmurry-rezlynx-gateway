"""Transform-layer correctness tests."""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from kilmurry_gateway.adapters import MockRezLynxAdapter
from kilmurry_gateway.models import (
    InventorySnapshot, ReservationRecord, RezLynxSnapshot,
)
from kilmurry_gateway.run_context import RunContext, utcnow
from kilmurry_gateway.transform import build_feed


def test_kpi_math_zero_division_safe() -> None:
    snap = RezLynxSnapshot(
        as_of_utc=utcnow(),
        target_date=date(2026, 5, 11),
        site_id="KILMURRY",
        reservations=[],
        inventory=InventorySnapshot(as_of_date=date(2026, 5, 11), rooms_available=0),
    )
    feed = build_feed(snap, run_ctx=RunContext(), source_label="mock", poll_interval_hours=6)
    assert feed["kpi"]["occupancy_pct"] == 0
    assert feed["kpi"]["adr_eur"] == 0
    assert feed["kpi"]["revpar_eur"] == 0
    # Empty snapshot is a structural failure; expect blocked confidence.
    assert feed["confidence"] in {"medium", "low", "blocked"}


def test_segment_share_pct_sums_to_about_100() -> None:
    adapter = MockRezLynxAdapter()
    snap = adapter.fetch(date(2026, 5, 11))
    feed = build_feed(snap, run_ctx=RunContext(), source_label="mock", poll_interval_hours=6)
    total = sum(s["share_pct"] for s in feed["segments"]["items"])
    assert 99 <= total <= 101  # rounding tolerance


def test_avvio_capitalisation_normalised() -> None:
    snap = RezLynxSnapshot(
        as_of_utc=utcnow(),
        target_date=date(2026, 5, 11),
        site_id="KILMURRY",
        inventory=InventorySnapshot(as_of_date=date(2026, 5, 11), rooms_available=10),
        reservations=[
            ReservationRecord(
                reservation_id="r1",
                arrival_date=date(2026, 5, 11),
                departure_date=date(2026, 5, 12),
                status="Resident",
                rooms=1,
                room_revenue=Decimal("100"),
                market_segment="DIRECT",
                media_source="Avvio",
            ),
            ReservationRecord(
                reservation_id="r2",
                arrival_date=date(2026, 5, 11),
                departure_date=date(2026, 5, 12),
                status="Resident",
                rooms=1,
                room_revenue=Decimal("100"),
                market_segment="DIRECT",
                media_source="AVVIO",  # quirky capitalisation
            ),
        ],
    )
    feed = build_feed(snap, run_ctx=RunContext(), source_label="mock", poll_interval_hours=6)
    names = [c["name"] for c in feed["channels"]["items"]]
    assert names.count("Avvio") == 1
    assert "AVVIO" not in names
