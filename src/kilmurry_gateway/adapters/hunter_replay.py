"""Hunter Replay Adapter — offline shadow source.

Reads real Kilmurry RezLynx CSV extracts that Hunter produced on
2026-03-04 and replays them through the live transform pipeline.

This is **the** validation tool that lets us prove the gateway works
on real, production-shaped data **before** live credentials land.

CSV files expected (any subset; missing files just yield empty data):

  rezlynx-bookings-{date}.csv          # SOAP `pmsbkg_BookingSearch`
  rezlynx-availability-{date}.csv      # SOAP `pmsavl_AvailAndRateV2`
  rezlynx-booked-revenue-{date}.csv    # Report Data `booked-revenue`
  rezlynx-dashboard-sales-{date}.csv   # Report Data `dashboard-sales`
                                        (used only for cross-check in transform)

Source files live in `samples/hunter-2026-03-04/` by convention.
"""
from __future__ import annotations

import csv
import json
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from ..models import (
    DashboardSalesLine, InventorySnapshot, ReservationRecord,
    RevenueLine, RezLynxSnapshot,
)
from .base import FetchError, RezLynxAdapter

logger = logging.getLogger("kilmurry_gateway.adapters.hunter_replay")


def _parse_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _to_decimal(s: str | None) -> Decimal:
    if s is None or s == "":
        return Decimal("0")
    try:
        return Decimal(str(s))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _parse_bool(s: str | None) -> bool:
    return str(s).strip().lower() in {"true", "1", "yes"}


def _try_path(root: Path, candidates: Iterable[str]) -> Path | None:
    """Return the first candidate path that exists under root."""
    for name in candidates:
        p = root / name
        if p.exists():
            return p
    return None


class HunterReplayAdapter(RezLynxAdapter):
    """Replays Hunter's CSV extracts as a live snapshot.

    Args:
        samples_dir: directory containing the rezlynx-*.csv files
        snapshot_date: the date stamped in Hunter's filenames (default 2026-03-04)
        site_id: source_site for the feed
    """

    def __init__(
        self,
        samples_dir: Path,
        snapshot_date: date = date(2026, 3, 4),
        site_id: str = "KILMURRY",
    ) -> None:
        self._dir = Path(samples_dir).resolve()
        if not self._dir.exists():
            raise FetchError(
                f"hunter samples dir not found: {self._dir}",
                endpoint=str(self._dir),
            )
        self._snapshot_date = snapshot_date
        self._site_id = site_id

    @property
    def source_label(self) -> str:
        return "hunter-replay-rezlynx"

    def _path(self, stem: str) -> Path | None:
        return _try_path(
            self._dir,
            [
                f"rezlynx-{stem}-{self._snapshot_date.isoformat()}.csv",
                f"rezlynx-{stem}.csv",
            ],
        )

    def _load_bookings(self) -> list[ReservationRecord]:
        path = self._path("bookings")
        if not path:
            logger.warning("hunter_replay.no_bookings_csv", extra={"dir": str(self._dir)})
            return []
        out: list[ReservationRecord] = []
        with path.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    extras_raw = row.get("extra_fields", "") or ""
                    extras = json.loads(extras_raw) if extras_raw else {}
                except json.JSONDecodeError:
                    extras = {}
                try:
                    arrival = _parse_date(row["arrival_date"])
                    departure = _parse_date(row["departure_date"])
                except (KeyError, ValueError):
                    continue
                # total_cost_gross is the contract value for the whole stay.
                # We store it for fallback but the transform prefers Report
                # Data revenue rows. We do not amortise it across nights here
                # to avoid double-counting against a revenue source.
                contract_revenue = _to_decimal(str(extras.get("total_cost_gross", "0")))
                dci = extras.get("distribution_channel_id")
                try:
                    dci_int = int(dci) if dci is not None and dci != "" else None
                except (TypeError, ValueError):
                    dci_int = None
                out.append(
                    ReservationRecord(
                        reservation_id=f"{row.get('booking_ref','?')}_{row.get('room_pick_id','?')}",
                        arrival_date=arrival,
                        departure_date=departure,
                        status=row.get("booking_status", "Unknown") or "Unknown",  # type: ignore[arg-type]
                        rooms=1,
                        room_revenue=contract_revenue,
                        market_segment=extras.get("market_segment"),
                        media_source=row.get("source") or None,
                        rate_plan=row.get("rate_code") or None,
                        room_type=row.get("room_type_code") or None,
                        distribution_channel_id=dci_int,
                    )
                )
        logger.info("hunter_replay.loaded_bookings", extra={"path": str(path), "rows": len(out)})
        return out

    def _load_availability(self, target_date: date) -> InventorySnapshot:
        """Sum available_rooms per room_type for target_date.

        IMPORTANT: the Hunter CSV contains DUPLICATE rows per (date,
        room_type_code) because the snapshot includes overlapping API
        windows. We dedupe on `id` taking the FIRST occurrence. The
        `available_rooms` value represents rooms remaining (after
        bookings) — the transform layer reconstructs total inventory
        by adding rooms_sold back. Don't double-fix that here.
        """
        path = self._path("availability")
        if not path:
            logger.warning("hunter_replay.no_availability_csv", extra={"dir": str(self._dir)})
            return InventorySnapshot(as_of_date=target_date, rooms_available=0)
        seen: set[str] = set()
        total = 0
        with path.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    if _parse_date(row["date"]) != target_date:
                        continue
                except (KeyError, ValueError):
                    continue
                row_id = row.get("id") or f"{row.get('date')}_{row.get('room_type_code')}"
                if row_id in seen:
                    continue
                seen.add(row_id)
                try:
                    total += int(row.get("available_rooms", "0") or 0)
                except ValueError:
                    continue
        logger.info(
            "hunter_replay.loaded_availability",
            extra={"path": str(path), "target_date": target_date.isoformat(), "rooms_available_after_dedupe": total, "rows": len(seen)},
        )
        return InventorySnapshot(as_of_date=target_date, rooms_available=total)

    def _load_revenue(self) -> list[RevenueLine]:
        path = self._path("booked-revenue")
        if not path:
            logger.warning("hunter_replay.no_revenue_csv", extra={"dir": str(self._dir)})
            return []
        out: list[RevenueLine] = []
        # This CSV uses ';' as separator (Hunter sample evidence).
        with path.open("r", encoding="utf-8") as f:
            for row in csv.DictReader(f, delimiter=";"):
                try:
                    d = _parse_date(row["date"])
                except (KeyError, ValueError):
                    continue
                out.append(
                    RevenueLine(
                        date=d,
                        revenue_type=row.get("revenue_type_long_description", "") or "",
                        revenue_type_group=row.get("revenue_type_group", "") or "",
                        market_segment=row.get("market_segment") or None,
                        media_source=row.get("media_source") or None,
                        rate_plan_code=row.get("rate_plan_code") or None,
                        room_type_code=row.get("room_type_code") or None,
                        cancelled=_parse_bool(row.get("cancelled", "False")),
                        is_no_show=_parse_bool(row.get("is_no_show", "False")),
                        amount_before_tax=_to_decimal(row.get("amount_before_tax")),
                        amount_after_tax=_to_decimal(row.get("amount_after_tax")),
                    )
                )
        logger.info("hunter_replay.loaded_revenue", extra={"path": str(path), "rows": len(out)})
        return out

    def fetch(self, target_date: date) -> RezLynxSnapshot:
        reservations = self._load_bookings()
        inventory = self._load_availability(target_date)
        revenue_lines = self._load_revenue()

        # Build snapshot timestamp from snapshot_date midday UTC for reproducibility.
        as_of = datetime.combine(self._snapshot_date, datetime.min.time(), tzinfo=timezone.utc)

        return RezLynxSnapshot(
            as_of_utc=as_of,
            target_date=target_date,
            site_id=self._site_id,
            reservations=reservations,
            inventory=inventory,
            revenue_lines=revenue_lines,
            notes=[
                f"replayed from Hunter snapshot {self._snapshot_date.isoformat()}",
                f"bookings={len(reservations)} revenue_rows={len(revenue_lines)} "
                f"rooms_available_target_date={inventory.rooms_available}",
            ],
        )
