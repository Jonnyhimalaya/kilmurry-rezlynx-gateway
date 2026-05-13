"""Deterministic mock adapter — generates a believable Kilmurry-shaped snapshot.

Useful for:
  - running the entire pipeline before RezLynx credentials are issued
  - tests
  - showing Faye a credible HTML summary for design feedback

Numbers are loosely calibrated to a 50-room property like Kilmurry Lodge.
"""
from __future__ import annotations

import random
from datetime import date, timedelta
from decimal import Decimal
from typing import Final

from ..models import (
    InventorySnapshot,
    ReservationRecord,
    RezLynxSnapshot,
)
from ..run_context import utcnow
from .base import RezLynxAdapter

KILMURRY_ROOMS_AVAILABLE: Final[int] = 50

# Real Kilmurry-shape vocabulary (per Hunter 2026-03-04 sample).
SEGMENTS: Final[list[str]] = ["CORPORATE", "DIRECT", "OTA", "COMP", "GDS", "LNR"]
SOURCES: Final[list[str]] = [
    "Booking.com", "Expedia", "Avvio", "HotelBeds", "SynXis",
]
RATE_PLANS: Final[list[str]] = ["BAR", "BB", "DBB", "BK_RO", "CORP"]
ROOM_TYPES: Final[list[str]] = ["EXEC", "SDB", "SDS", "SUITE", "STU", "INTR", "SUPDS"]


class MockRezLynxAdapter(RezLynxAdapter):
    """Generates a realistic snapshot. Deterministic per (target_date, seed)."""

    def __init__(self, site_id: str = "KILMURRY", seed: int = 42) -> None:
        self._site_id = site_id
        self._seed = seed

    @property
    def source_label(self) -> str:
        return "mock-rezlynx"

    def fetch(self, target_date: date) -> RezLynxSnapshot:
        rng = random.Random(f"{self._seed}-{target_date.isoformat()}")
        # 78% occupancy +/- 12pp depending on day-of-week
        dow_modifier = {
            0: -2, 1: -2, 2: 0, 3: 2, 4: 6, 5: 8, 6: 4,
        }[target_date.weekday()]
        target_occ_pct = max(35, min(98, 78 + dow_modifier + rng.randint(-6, 6)))
        rooms_sold = round(KILMURRY_ROOMS_AVAILABLE * target_occ_pct / 100)

        reservations: list[ReservationRecord] = []
        for i in range(rooms_sold):
            arrival = target_date - timedelta(days=rng.randint(0, 2))
            length_of_stay = rng.choices([1, 2, 3, 4], weights=[55, 25, 12, 8])[0]
            departure = arrival + timedelta(days=length_of_stay)
            # Make sure this reservation is "active" on target_date.
            if not (arrival <= target_date < departure):
                arrival = target_date
                departure = target_date + timedelta(days=length_of_stay)
            nightly_rate = Decimal(rng.choice([120, 135, 145, 159, 175, 189, 199, 219]))
            status = "Resident" if arrival <= target_date else "PreArrival"
            reservations.append(
                ReservationRecord(
                    reservation_id=f"R{target_date.strftime('%Y%m%d')}-{i:04d}",
                    arrival_date=arrival,
                    departure_date=departure,
                    status=status,
                    rooms=1,
                    room_revenue=nightly_rate,
                    market_segment=rng.choice(SEGMENTS),
                    media_source=rng.choice(SOURCES),
                    rate_plan=rng.choice(RATE_PLANS),
                    room_type=rng.choice(ROOM_TYPES),
                )
            )

        # A handful of cancellations and no-shows attributed to target_date.
        for i in range(rng.randint(0, 3)):
            reservations.append(
                ReservationRecord(
                    reservation_id=f"C{target_date.strftime('%Y%m%d')}-{i:03d}",
                    arrival_date=target_date,
                    departure_date=target_date + timedelta(days=rng.choice([1, 2])),
                    status="Cancelled",
                    rooms=1,
                    room_revenue=Decimal("0"),
                    market_segment=rng.choice(SEGMENTS),
                    media_source=rng.choice(SOURCES),
                    cancellation_reason=rng.choice([
                        "Guest cancellation", "Plans changed", "Found cheaper", "Weather",
                    ]),
                )
            )
        for i in range(rng.randint(0, 2)):
            reservations.append(
                ReservationRecord(
                    reservation_id=f"N{target_date.strftime('%Y%m%d')}-{i:03d}",
                    arrival_date=target_date,
                    departure_date=target_date + timedelta(days=1),
                    status="NoShow",
                    rooms=1,
                    room_revenue=Decimal("0"),
                    market_segment=rng.choice(SEGMENTS),
                    media_source=rng.choice(SOURCES),
                )
            )

        inventory = InventorySnapshot(
            as_of_date=target_date,
            rooms_available=KILMURRY_ROOMS_AVAILABLE,
            rooms_out_of_order=rng.choice([0, 0, 0, 1, 2]),
        )

        return RezLynxSnapshot(
            as_of_utc=utcnow(),
            target_date=target_date,
            site_id=self._site_id,
            reservations=reservations,
            inventory=inventory,
            notes=[
                "snapshot generated by MockRezLynxAdapter — not real PMS data",
                f"seed={self._seed}",
            ],
        )
