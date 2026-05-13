"""Internal PMS-shaped models used between adapter -> transform.

These are intentionally simple and stable so we can drop in a real RezLynx
adapter later without changing the transform/publish layer.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# RezLynx production statuses (evidence: Hunter 2026-03-04 sample).
# We use the RezLynx-native vocabulary as our internal status to avoid
# mapping bugs at the boundary.
ReservationStatus = Literal[
    "PreArrival",    # confirmed, not yet arrived (was "BOOKED")
    "Resident",      # currently in-house (was "IN_HOUSE")
    "CheckedOut",    # departed
    "Cancelled",
    "NoShow",
    "Waitlist",
    "Unknown",
]

# Statuses that count toward "active on target_date" math.
ACTIVE_STATUSES = ("PreArrival", "Resident")


class ReservationRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    reservation_id: str
    arrival_date: date
    departure_date: date
    status: ReservationStatus = "Unknown"
    rooms: int = 1
    # NOTE: room_revenue is the contract value from SOAP `total_cost_*`.
    # It is NOT authoritative for realised period revenue. The transform
    # layer prefers RevenueLine rows from Report Data for room_revenue_eur.
    # Kept here only as a fallback when revenue source is unavailable.
    room_revenue: Decimal = Field(default=Decimal("0"))
    market_segment: Optional[str] = None
    media_source: Optional[str] = None  # human, e.g. "Booking.com"
    rate_plan: Optional[str] = None
    room_type: Optional[str] = None
    distribution_channel_id: Optional[int] = None  # integer code, capture for future mapping
    cancellation_reason: Optional[str] = None


class InventorySnapshot(BaseModel):
    """Inventory state from RezLynx.

    IMPORTANT: `rooms_available` represents **rooms remaining after sales**
    — i.e. unsold inventory, NOT total capacity. To get total capacity:
      total_capacity = rooms_available + rooms_sold
    The transform layer handles this reconstruction.
    """
    as_of_date: date
    rooms_available: int      # rooms remaining (unsold) per RezLynx semantics
    rooms_out_of_order: int = 0


class RezLynxSnapshot(BaseModel):
    """Everything one fetch returns from the PMS, in a normalised shape."""

    model_config = ConfigDict(extra="ignore")

    as_of_utc: datetime
    target_date: date
    site_id: str
    reservations: list[ReservationRecord] = Field(default_factory=list)
    inventory: InventorySnapshot
    notes: list[str] = Field(default_factory=list)

    # Optional realised revenue rows from Report Data REST. When present,
    # the transform layer prefers these over per-reservation contract values.
    revenue_lines: list["RevenueLine"] = Field(default_factory=list)

    def reservations_for_target_day(self) -> list[ReservationRecord]:
        """Reservations active on target_date (PreArrival or Resident)."""
        return [
            r for r in self.reservations
            if r.arrival_date <= self.target_date < r.departure_date
            and r.status in ACTIVE_STATUSES
        ]


class RevenueLine(BaseModel):
    """One row from Report Data `booked-revenue`.

    Used to compute authoritative room revenue per target_date,
    filterable by `revenue_type_long_description` and `is_no_show`/`cancelled`.
    """

    model_config = ConfigDict(extra="ignore")

    date: date
    revenue_type: str           # e.g. "Accommodation", "Food", "Other"
    revenue_type_group: str     # e.g. "Accommodation", "FoodAndDrink", "Other"
    market_segment: Optional[str] = None
    media_source: Optional[str] = None
    rate_plan_code: Optional[str] = None
    room_type_code: Optional[str] = None
    cancelled: bool = False
    is_no_show: bool = False
    amount_before_tax: Decimal = Field(default=Decimal("0"))
    amount_after_tax: Decimal = Field(default=Decimal("0"))


class DashboardSalesLine(BaseModel):
    """One row from Report Data `dashboard-sales`. Used for cross-check only."""

    model_config = ConfigDict(extra="ignore")

    date: date
    analysis_code: str          # e.g. "ACCOM", "BAR_DRINK"
    amount_before_tax: Decimal = Field(default=Decimal("0"))
    amount_after_tax: Decimal = Field(default=Decimal("0"))
