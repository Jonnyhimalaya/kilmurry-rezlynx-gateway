# Golden Field Mapping — MVP Output → Live Source

Every field in `kilmurry.rezlynx.revenue_feed.v1` mapped to its live
source, extraction mechanism, and transform rule. This is the contract
between the live adapters and the transform layer.

Reference snapshot for examples: Hunter 2026-03-04 KILMURRY.

## Top-level envelope

| Output field | Source | Mechanism | Notes |
|---|---|---|---|
| `schema` | constant | — | `"kilmurry.rezlynx.revenue_feed.v1"` |
| `generated_at_utc` | gateway clock | — | run_started_at, UTC ISO8601 |
| `as_of_utc` | latest source `snapshot_date` | composite | min of bookings.snapshot_date and revenue source freshness |
| `source_system` | constant per adapter | — | `"guestline-rezlynx"` for live, `"hunter-replay-rezlynx"` for offline |
| `source_site` | config | — | `"KILMURRY"` |
| `confidence` | derived | — | `high` if no validation warnings, `medium` for 1, `low` for 2+, `blocked` if missing required block |
| `freshness.status` | derived | — | `LIVE` ≤ 8h, `STALE` ≤ 18h, `BLOCKED` otherwise |
| `freshness.age_minutes` | computed | — | now - as_of_utc |
| `freshness.poll_interval_hours` | config | — | `6` |

## KPI block

| Output field | Source | Mechanism | Raw column(s) | Transform |
|---|---|---|---|---|
| `kpi.rooms_available` | SOAP availability | `pmsavl_AvailAndRateV2` | `available_rooms` summed across `room_type_code` where `date == target_date` | `sum(available_rooms for r in availability if r.date == target_date)` |
| `kpi.rooms_sold` | SOAP bookings | `pmsbkg_BookingSearch` | row count where active on target_date | active = `arrival_date <= target_date < departure_date AND status in ("PreArrival","Resident")` |
| `kpi.rooms_out_of_order` | — | — | — | **Phase 1: not in feed** — neither SOAP nor REST exposes OOS in Hunter sample. Add when source identified. Default 0. |
| `kpi.room_revenue_eur` | REST Report Data | `booked-revenue` | sum of `amount_after_tax` where `revenue_type_long_description == "Accommodation" AND cancelled == False AND is_no_show == False AND date == target_date` | Authoritative Accommodation revenue |
| `kpi.occupancy_pct` | derived | — | — | `rooms_sold / rooms_available * 100` |
| `kpi.adr_eur` | derived | — | — | `room_revenue_eur / rooms_sold` |
| `kpi.revpar_eur` | derived | — | — | `room_revenue_eur / rooms_available` |

## Operations block

All sourced from SOAP `pmsbkg_BookingSearch` rows, filtered to `target_date`.

| Output field | Filter |
|---|---|
| `operations.arrivals_today` | `arrival_date == target_date AND status in ("PreArrival","Resident")` |
| `operations.departures_today` | `departure_date == target_date AND status in ("Resident","CheckedOut")` |
| `operations.stayovers_today` | `arrival_date < target_date < departure_date AND status in ("PreArrival","Resident")` |
| `operations.in_house_rooms` | `status == "Resident" AND arrival_date <= target_date < departure_date` |
| `operations.cancellations_today` | `status == "Cancelled" AND arrival_date == target_date` |
| `operations.no_shows_today` | `status == "NoShow" AND arrival_date == target_date` |

## Segments block

Source: SOAP bookings, segment lives in `extra_fields` JSON.

| Output | Source field | Transform |
|---|---|---|
| `segments.source` | constant | `"rezlynx-market-segment"` |
| `segments.items[*].name` | `extra_fields.market_segment` | one of `CORPORATE`, `DIRECT`, `OTA`, `COMP`, `GDS`, `LNR`. Default to `"Unmapped"` if absent. |
| `segments.items[*].rooms` | count of bookings | count of active reservations in segment for target_date |
| `segments.items[*].room_revenue_eur` | join to Report Data | sum of Report Data Accommodation rows where `market_segment` matches AND `date == target_date` AND not cancelled/no-show |
| `segments.items[*].share_pct` | derived | `rooms / sum(all segments.rooms) * 100` |

## Channels block

Source: SOAP bookings, `source` field (human name) and (for raw archive) `extra_fields.distribution_channel_id`.

| Output | Source field | Transform |
|---|---|---|
| `channels.source` | constant | `"rezlynx-media-source"` |
| `channels.items[*].name` | `source` | normalised (e.g. `"AVVIO" -> "Avvio"`). 5 known channels in production sample: Avvio, Booking.com, Expedia, HotelBeds, SynXis. |
| `channels.items[*].rooms` | count of bookings | count of active reservations on channel for target_date |
| `channels.items[*].room_revenue_eur` | join to Report Data | sum of Report Data Accommodation rows where `media_source` matches the booking `source` mapping AND `date == target_date` AND not cancelled/no-show |
| `channels.items[*].share_pct` | derived | as for segments |

### Media-source mapping (live SOAP → Report Data)

Report Data uses UPPER_SNAKE codes (`BOOKING_COM`, `EXPEDIA`, etc.).
SOAP uses display names. The mapping needs confirmation against
production, but the sample gives:

| SOAP `source` | Report Data `media_source` (inferred from sample) |
|---|---|
| `Booking.com` | `BOOKING_COM` |
| `Expedia` | `EXPEDIA` |
| `Avvio` | `AVVIO` |
| `HotelBeds` | `HOTELBEDS` |
| `SynXis` | `SYNXIS` |

Mapping table lives in `kilmurry_gateway/mappings.py`. Open question
flagged for Faye walkthrough.

## Rates block

| Output | Source | Notes |
|---|---|---|
| `rates.active_rate_plans_count` | SOAP bookings | distinct `rate_code` among active reservations |
| `rates.room_types_count` | SOAP availability | distinct `room_type_code` with `available_rooms > 0` for target_date |

## Provenance block

Gateway-generated. Captures source contract for trust:

```jsonc
{
  "gateway_run_id": "gw-...",
  "gateway_hostname": "stephen-pc",
  "sources": {
    "bookings": {"mechanism": "soap", "method": "pmsbkg_BookingSearch", "snapshot_date": "2026-05-11", "row_count": 443},
    "availability": {"mechanism": "soap", "method": "pmsavl_AvailAndRateV2", "snapshot_date": "2026-05-11", "row_count": 1200},
    "revenue": {"mechanism": "rest", "endpoint": "booked-revenue", "snapshot_date": "2026-05-11", "row_count": 792}
  },
  "target_date": "2026-05-11",
  "record_counts": { ... },
  "cross_checks": [
    {"name": "accom_total_vs_dashboard", "report_data_total": 5928.0, "dashboard_total": 5901.0, "delta_pct": 0.46, "status": "ok"}
  ],
  "validation_warnings": []
}
```

## What we deliberately do NOT include in v1

- Guest names, emails, phone, address — captured in SOAP but never published.
- Per-reservation transaction breakdowns — overkill for Phase 1.
- Per-room-number assignments — captured in raw archive only.
- Loyalty IDs, GDS refs — captured in raw archive only.
- Pickup metrics (24h/7d/30d) — Phase 2, needs Event Archive.
- Forecasting numbers — Phase 2.

## Worked example from Hunter 2026-03-04

For target_date = 2026-03-04 from the Hunter sample:

- Bookings file: 443 rows. Of these, active on 2026-03-04 = rows where `arrival_date <= 2026-03-04 < departure_date AND status in (PreArrival, Resident)`.
- Availability file: rows where `date == 2026-03-04` → sum `available_rooms` across all room_types.
- Booked revenue file: rows where `date == 2026-03-04 AND revenue_type_long_description == "Accommodation" AND cancelled == False AND is_no_show == False` → sum `amount_after_tax` = room_revenue_eur.
- Dashboard sales file: row where `date == 2026-03-04 AND analysis_code == "ACCOM"` → cross-check against above. Delta should be < 2%.

The `HunterReplay` adapter performs exactly this in code and produces a
valid `kilmurry.rezlynx.revenue_feed.v1` artifact. See
`samples/feeds/rezlynx-revenue-feed-latest.json` after `gateway hunter-replay`.
