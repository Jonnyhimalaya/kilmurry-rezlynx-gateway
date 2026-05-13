# Live Access Decision Note — RezLynx Phase 1 Cutover

**Author:** Stephen King (via OpenClaw)
**Date:** 11 May 2026
**Status:** Recommendation, awaiting credential recovery to flip live

---

## TL;DR

Use a **hybrid two-source live ingestion** for the Phase 1 MVP:

- **Source A — RezLynx SOAP** → reservations + availability + room-type inventory
- **Source B — Guestline Report Data REST** → authoritative room revenue (Accommodation only, ex-cancellations, ex-no-shows)

**Defer** LANSync indefinitely for MVP. It was scheduled but never installed (Hunter paused contract on 2026-03-05 before the 2026-03-05 engineer slot).

**Defer** Event Archive REST for MVP. Useful later for near-real-time pickup, not required for v1 contract.

**Defer** Dashboard sales REST as a *validation cross-check only* (compare `ACCOM` analysis_code totals against summed Report Data Accommodation revenue, surface as warnings).

## Evidence

This is not a hypothesis. The Hunter sample CSVs in
`context/hunter-samples/` are real production extracts from KILMURRY dated
**2026-03-04**:

| File | Rows | Confirmed source |
|---|---|---|
| `rezlynx-bookings-2026-03-04.csv` | 443 | SOAP `pmsbkg_BookingSearch` |
| `rezlynx-availability-2026-03-04.csv` | 1,200 | SOAP `pmsavl_AvailAndRateV2` |
| `rezlynx-booked-revenue-2026-03-04.csv` | 792 | Report Data REST `booked-revenue` |
| `rezlynx-dashboard-sales-2026-03-04.csv` | 188 | Report Data REST `dashboard-sales` |

LANSync was scheduled to be installed **2026-03-05**, one day after the
snapshot timestamp. Hunter then paused the contract on 2026-03-05. So the
Hunter CSVs were produced **without LANSync**. The hybrid SOAP + REST
path is proven, in production, on this exact site.

## The three semantic traps (per runbook §7), resolved from evidence

### Trap 1 — Room revenue definition: RESOLVED

Use **Report Data `booked-revenue`** filtered to:

- `revenue_type_long_description == "Accommodation"` (516 rows of 792 in sample)
- `cancelled == False` (drops 117 cancelled-revenue rows)
- `is_no_show == False` (drops 6 no-show rows)

Sum `amount_after_tax` for gross / `amount_before_tax` for nett.

Cross-check against Dashboard `ACCOM` analysis_code total. Tolerance: ±2% (small differences expected due to refunds / late adjustments).

Do **not** sum the SOAP bookings `total_cost_gross`/`total_cost_nett` —
those are *contract* values per reservation, not realised period revenue.
They include cancelled bookings unless filtered, span the whole stay
(not the target date), and don't match Faye's daily reporting.

### Trap 2 — No-show definition: RESOLVED

Two sources:

1. **SOAP bookings**: `booking_status == "NoShow"` — distinct status (2 in sample).
2. **Report Data**: `is_no_show == True` rows are revenue lines tagged as no-show.

Phase 1 rule: `no_shows_today = count of SOAP bookings where
booking_status == "NoShow" AND arrival_date == target_date`.

### Trap 3 — Source/channel/segment mapping: RESOLVED

- **`source`** field in SOAP bookings is **human-readable** (`Avvio`, `Booking.com`, `Expedia`, `HotelBeds`, `SynXis`). No mapping needed for the channel display.
- **`market_segment`** lives inside the `extra_fields` JSON blob on each booking and is short-coded (`CORPORATE`, `DIRECT`, `OTA`, `COMP`, `GDS`, `LNR`). No mapping required for display; we may pretty-print later (`OTA` → "OTA").
- **`distribution_channel_id`** (integer, also in `extra_fields`) is the underlying ID Gary Hunt flagged as needing a mapping table. Phase 1 does **not** need this — `source` (human string) is sufficient for the channels block. Capture `distribution_channel_id` in raw archive for future use.

## Why not LANSync

- Engineer install was scheduled 2026-03-05; contract paused that same day.
- Requires Windows host with local-admin scheduled appointment to install.
- Adds operational surface area (Windows service, SQL Server local).
- Provides nothing we can't already get from SOAP + Report Data for v1.
- Re-evaluate for Phase 1.5 if richer historical / transaction-level data is needed.

## Why not (yet) Event Archive REST

- Hunter requested X-API-KEYs on 2026-01-20; archive shows no confirmation they were issued.
- Event-driven shape is great for *near-real-time pickup*, which is Phase 2+ scope.
- Phase 1 6-hourly polling does not need an event stream.
- Add later when forecast/pickup features land.

## What's needed to flip from skeleton → live

| Item | Status | Action |
|---|---|---|
| SOAP endpoint | ✅ known: `https://pmsws.eu.guestline.net/RLXSoapRouter/rlxsoap.asmx` | hard-coded fallback in config |
| SOAP Interface ID | ✅ known: `727` | in config |
| SOAP Site ID | ✅ known: `KILMURRY` | in config |
| SOAP Operator Code | ✅ known: `KILMURRY_API` | in config |
| **SOAP Password** | ⛔ **NOT in archive — was sent in a separate email to Hunter only** | Stephen / Jack to recover from Hunter, OR request a re-issue from Gary Hunt at Access (gary.hunt@theaccessgroup.com) |
| Report Data REST base URL | ⛔ not in archive | Stephen to ask Gary Hunt — likely `https://api.guestline.io/...` |
| Report Data X-API-KEY | ⛔ not confirmed issued | follow up on Hunter's 2026-01-20 request to Gary Hunt |
| GroupID / SiteID for REST | ⛔ partially: SiteID=KILMURRY assumed; GroupID unknown | ask Gary Hunt |

## Shadow-mode readiness

**NOT YET READY** for live shadow mode against Kilmurry production.

However, **OFFLINE SHADOW MODE IS READY NOW** via the new `HunterReplay`
adapter (see `adapters/hunter_replay.py`). This adapter loads the real
2026-03-04 Kilmurry exports and feeds them through the live transform.
That proves:

- the live transform handles real PMS-shaped data
- the field mapping is correct
- the contract validates against real numbers
- the HTML summary makes operational sense on a known day

Once SOAP password + REST keys land, swap `HunterReplay` for
`RezLynxSoap + RezLynxReportData` adapters. Same transform, same
contract, same output shape.

## Recommended sequencing for Stephen

1. **Today** — Inspect `samples/feeds/rezlynx-revenue-feed-latest.json` from a `gateway sample --hunter` run. Verify the numbers from Hunter's 2026-03-04 data look credible to Faye.
2. **This week** — Recover or re-issue:
   - SOAP password (from Hunter directly, or escalate to Gary Hunt).
   - Report Data REST credentials (escalate to Gary Hunt).
3. **Next week** — Drop the live credentials into `config/secrets.toml`. Flip `mock_mode = false`, `live_sources = ["soap", "report_data"]`. Run `gateway run` and compare its 2026-03-04 dry-run against the Hunter replay (numbers should match).
4. **Following week** — Shadow mode for 5 days against 2026-05-XX target dates, validate against Faye's spot-check days, then enable the 6-hourly Task Scheduler.

## What this avoids

- Building a wrong adapter against guessed field names.
- Building forecasting/pricing logic without proven Tier 1.
- Forcing one source mechanism to do everything.
- Treating SOAP `total_cost_*` as realised revenue.
- Treating booking record counts as room-night counts (each row IS one room-night via `room_pick_id`; verified in sample).
- Re-discovering the integer DistributionChannelID mapping in production.
