"""Transform a `RezLynxSnapshot` into a `kilmurry.rezlynx.revenue_feed.v1` dict.

Critical correctness rules (per `docs/field-mapping.md`):

1. Statuses use the RezLynx-native vocabulary
   (`PreArrival`, `Resident`, `CheckedOut`, `Cancelled`, `NoShow`).

2. `room_revenue_eur` PREFERS `revenue_lines` from Report Data
   filtered to `revenue_type_long_description == "Accommodation" AND
   cancelled == False AND is_no_show == False`. Falls back to summing
   per-reservation contract values only when revenue_lines is empty,
   and emits a clear warning that confidence is degraded.

3. Segments and channels use the bookings table for counts, but
   join to revenue_lines for room_revenue. If revenue_lines is missing,
   segment/channel revenue is reported as 0 with a warning.

4. The Avvio capitalisation quirk is handled by `mappings.normalise_channel_name`.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any

from .. import SCHEMA_ID
from ..mappings import (
    REPORT_MEDIA_TO_SOAP_SOURCE,
    SOAP_SOURCE_TO_REPORT_MEDIA,
    normalise_channel_name,
    segment_display,
)
from ..models import ACTIVE_STATUSES, RevenueLine, RezLynxSnapshot
from ..run_context import RunContext, iso_utc, utcnow


def _round_money(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.01")))


def _round_pct(x: float) -> float:
    return round(x, 2)


def _freshness_status(age_minutes: float, poll_interval_hours: int) -> str:
    age_hours = age_minutes / 60.0
    if age_hours <= 8:
        return "LIVE"
    if age_hours <= 18:
        return "STALE"
    return "BLOCKED"


def _accommodation_revenue_for_date(lines: list[RevenueLine], target) -> Decimal:
    return sum(
        (
            line.amount_after_tax
            for line in lines
            if line.date == target
            and line.revenue_type == "Accommodation"
            and not line.cancelled
            and not line.is_no_show
        ),
        Decimal("0"),
    )


def build_feed(
    snapshot: RezLynxSnapshot,
    *,
    run_ctx: RunContext,
    source_label: str,
    poll_interval_hours: int = 6,
) -> dict[str, Any]:
    """Build the v1 feed envelope from a snapshot."""

    target = snapshot.target_date
    inv = snapshot.inventory
    active = snapshot.reservations_for_target_day()
    rooms_sold = sum(r.rooms for r in active)
    # RezLynx semantics: inv.rooms_available = rooms remaining (unsold).
    # Reconstruct total inventory = remaining + sold, then subtract OOS.
    rooms_remaining = inv.rooms_available
    rooms_capacity = max(0, rooms_remaining + rooms_sold - inv.rooms_out_of_order)
    # For KPI output, we publish capacity-style rooms_available
    # (what RevPAR/occupancy is computed against).
    rooms_available = rooms_capacity

    has_revenue_lines = bool(snapshot.revenue_lines)
    if has_revenue_lines:
        room_revenue = _accommodation_revenue_for_date(snapshot.revenue_lines, target)
        revenue_source = "report-data.booked-revenue"
    else:
        # Fallback: amortise contract revenue across each reservation's
        # length-of-stay so we credit only the night that is target_date.
        # NOTE: this is a rough fallback. Real revenue should come from
        # Report Data once that adapter is live.
        room_revenue = Decimal("0")
        for r in active:
            nights = max(1, (r.departure_date - r.arrival_date).days)
            room_revenue += r.room_revenue / nights
        revenue_source = "soap.contract_value_fallback"

    cancellations_today = [
        r for r in snapshot.reservations
        if r.status == "Cancelled" and r.arrival_date == target
    ]
    no_shows_today = [
        r for r in snapshot.reservations
        if r.status == "NoShow" and r.arrival_date == target
    ]
    arrivals_today = [
        r for r in snapshot.reservations
        if r.arrival_date == target and r.status in ACTIVE_STATUSES
    ]
    departures_today = [
        r for r in snapshot.reservations
        if r.departure_date == target and r.status in ("Resident", "CheckedOut")
    ]
    stayovers_today = [
        r for r in active
        if r.arrival_date < target < r.departure_date
    ]
    in_house = [r for r in active if r.status == "Resident"]

    occupancy_pct = (rooms_sold / rooms_available * 100.0) if rooms_available else 0.0
    adr = (room_revenue / rooms_sold) if rooms_sold else Decimal("0")
    revpar = (room_revenue / rooms_available) if rooms_available else Decimal("0")

    # ----- segments -----
    seg_rooms: dict[str, int] = defaultdict(int)
    for r in active:
        key = segment_display(r.market_segment)
        seg_rooms[key] += r.rooms

    # Revenue per segment from revenue_lines (preferred) or 0
    seg_rev: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    if has_revenue_lines:
        for line in snapshot.revenue_lines:
            if (
                line.date == target
                and line.revenue_type == "Accommodation"
                and not line.cancelled
                and not line.is_no_show
                and line.market_segment
            ):
                seg_rev[segment_display(line.market_segment)] += line.amount_after_tax

    total_seg_rooms = sum(seg_rooms.values()) or 1
    segments_items = [
        {
            "name": name,
            "rooms": seg_rooms[name],
            "room_revenue_eur": _round_money(seg_rev.get(name, Decimal("0"))),
            "share_pct": _round_pct(seg_rooms[name] / total_seg_rooms * 100.0),
        }
        for name in sorted(seg_rooms, key=lambda k: -seg_rooms[k])
    ]

    # ----- channels (rooms from bookings.source, revenue from revenue_lines.media_source) -----
    ch_rooms: dict[str, int] = defaultdict(int)
    for r in active:
        key = normalise_channel_name(r.media_source)
        ch_rooms[key] += r.rooms

    ch_rev: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    if has_revenue_lines:
        for line in snapshot.revenue_lines:
            if not (
                line.date == target
                and line.revenue_type == "Accommodation"
                and not line.cancelled
                and not line.is_no_show
                and line.media_source
            ):
                continue
            # Report Data uses BOOKING_COM, EXPEDIA, etc. Map back to display name.
            display = REPORT_MEDIA_TO_SOAP_SOURCE.get(
                line.media_source, normalise_channel_name(line.media_source.title())
            )
            ch_rev[display] += line.amount_after_tax

    total_ch_rooms = sum(ch_rooms.values()) or 1
    channels_items = [
        {
            "name": name,
            "rooms": ch_rooms[name],
            "room_revenue_eur": _round_money(ch_rev.get(name, Decimal("0"))),
            "share_pct": _round_pct(ch_rooms[name] / total_ch_rooms * 100.0),
        }
        for name in sorted(ch_rooms, key=lambda k: -ch_rooms[k])
    ]

    rate_plans_seen = {r.rate_plan for r in active if r.rate_plan}
    room_types_seen = {r.room_type for r in active if r.room_type}

    now = utcnow()
    age_minutes = max(0.0, (now - snapshot.as_of_utc).total_seconds() / 60.0)
    freshness_status = _freshness_status(age_minutes, poll_interval_hours)

    warnings: list[str] = []
    if not segments_items:
        warnings.append("no market_segment data on any active reservation")
    if not channels_items:
        warnings.append("no media_source data on any active reservation")
    if not rooms_available:
        warnings.append("inventory.rooms_available is zero")
    if not has_revenue_lines:
        warnings.append(
            "no revenue_lines from Report Data — room_revenue uses contract-value fallback"
        )
    if has_revenue_lines and not any(
        l.date == target and l.revenue_type == "Accommodation" for l in snapshot.revenue_lines
    ):
        warnings.append(f"no Accommodation revenue rows for target_date {target}")

    # Cross-check: channel revenue should sum to KPI room_revenue within a
    # small tolerance. A large gap usually means bookings without a
    # `source` field couldn't be joined to their revenue rows.
    channel_rev_total = sum(
        Decimal(str(c["room_revenue_eur"])) for c in channels_items
    )
    if room_revenue > 0:
        gap_pct = float(abs(room_revenue - channel_rev_total) / room_revenue) * 100.0
        if gap_pct > 5.0:
            warnings.append(
                f"channel revenue (€{channel_rev_total}) vs total room revenue "
                f"(€{room_revenue}) differ by {gap_pct:.1f}% — likely bookings "
                f"without 'source' field"
            )

    if not warnings:
        confidence = "high"
    elif len(warnings) == 1:
        confidence = "medium"
    else:
        confidence = "low"
    # If neither rooms_available nor any reservations, the dashboard is meaningless.
    if not rooms_available and not active:
        confidence = "blocked"

    feed: dict[str, Any] = {
        "schema": SCHEMA_ID,
        "generated_at_utc": iso_utc(now),
        "as_of_utc": iso_utc(snapshot.as_of_utc),
        "source_system": source_label,
        "source_site": snapshot.site_id,
        "confidence": confidence,
        "freshness": {
            "status": freshness_status,
            "age_minutes": round(age_minutes, 2),
            "poll_interval_hours": poll_interval_hours,
        },
        "kpi": {
            "occupancy_pct": _round_pct(occupancy_pct),
            "adr_eur": _round_money(adr),
            "revpar_eur": _round_money(revpar),
            "room_revenue_eur": _round_money(room_revenue),
            "rooms_sold": rooms_sold,
            "rooms_available": rooms_available,
            "rooms_out_of_order": inv.rooms_out_of_order,
        },
        "operations": {
            "arrivals_today": len(arrivals_today),
            "departures_today": len(departures_today),
            "stayovers_today": len(stayovers_today),
            "in_house_rooms": len(in_house),
            "cancellations_today": len(cancellations_today),
            "no_shows_today": len(no_shows_today),
        },
        "segments": {
            "source": "rezlynx-market-segment",
            "items": segments_items,
        },
        "channels": {
            "source": "rezlynx-media-source",
            "items": channels_items,
        },
        "rates": {
            "active_rate_plans_count": len(rate_plans_seen),
            "room_types_count": len(room_types_seen),
        },
        "provenance": {
            "gateway_run_id": run_ctx.run_id,
            "gateway_hostname": run_ctx.hostname,
            "source_snapshot_from": iso_utc(snapshot.as_of_utc),
            "source_snapshot_to": iso_utc(snapshot.as_of_utc),
            "target_date": target.isoformat(),
            "revenue_source": revenue_source,
            "record_counts": {
                "reservations_total": len(snapshot.reservations),
                "reservations_active_on_target": len(active),
                "revenue_rows_total": len(snapshot.revenue_lines),
                "cancellations": len(cancellations_today),
                "no_shows": len(no_shows_today),
            },
            "validation_warnings": warnings,
        },
        "_notes": list(snapshot.notes),
    }
    return feed
