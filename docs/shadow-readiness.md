# Shadow-Mode Readiness Recommendation

## TL;DR

**OFFLINE shadow mode: ✅ READY NOW.**
**LIVE shadow mode (real Kilmurry production): ❌ NOT YET READY.**

## Offline shadow mode — what it proves

Running `gateway hunter-replay` produces a fully-valid
`kilmurry.rezlynx.revenue_feed.v1` artifact from real Kilmurry RezLynx
data captured by Hunter on 2026-03-04. Verified numbers:

- Occupancy 66.2%
- ADR €80.67
- RevPAR €53.41
- Room Revenue €7,744.00
- Rooms sold 96 / available 145
- Operations: 34 arrivals, 75 departures, 62 stayovers, 80 in-house, 2 cancellations, 0 no-shows
- 4 market segments populated (DIRECT 55%, CORPORATE 16%, OTA 16%, GDS 13%)
- 4 channels with revenue + 1 "Unmapped" cluster (49 bookings without source field)
- 1 validation warning correctly flagging the channel-revenue gap

This proves:
- ✅ Schema contract validates against real-shaped data
- ✅ Transform handles real statuses (`PreArrival`, `Resident`, etc.) correctly
- ✅ Revenue isolation (`Accommodation` only, ex-cancelled, ex-no-show) works
- ✅ Avvio/AVVIO normalisation works
- ✅ Channel revenue mapping works (BOOKING_COM → Booking.com, WEBSITE → Avvio, etc.)
- ✅ Cross-check warnings fire when real data quality gaps exist (channel rev vs total rev gap)
- ✅ OneDrive write path works (files in correct subfolders, latest pointer updated atomically)
- ✅ HTML summary renders cleanly with real numbers

## Why live shadow mode is NOT yet ready

Blocked on:

1. **SOAP password not in our possession** (sent privately to Hunter only).
2. **REST API keys for Report Data not confirmed issued.**
3. **REST base URL + endpoint paths not confirmed.**

Without these we literally cannot make a live request. The skeleton
adapter (`adapters/rezlynx_soap.py`) raises a clear `FetchError` rather
than silently producing garbage.

## Path to live shadow mode

Once Stephen has the credentials in hand:

1. **Drop into `config/secrets.toml`:**
   ```toml
   [rezlynx]
   password = "<from gary hunt>"
   report_data_api_key = "<from gary hunt>"
   ```
2. **Flip `adapter_mode = "live"` in `config/settings.toml`.**
3. **Set `rezlynx.base_url` if Guestline gives a non-default endpoint.**
4. **Run `gateway soap-probe`** to confirm SOAP connectivity.
   - First run may reveal that XML envelope namespaces or response
     field names differ from my assumptions. The adapter is designed
     to be debuggable: enable `--log-level=DEBUG` and look at the raw
     SOAP envelope/response in `logs/gateway.jsonl`.
5. **Run `gateway run --target-date=2026-03-04 --dry-run`** and compare
   the output KPI block against the Hunter replay output. They should
   match within rounding (Hunter pulled at a fixed moment; today's
   pull may differ if bookings were edited since 2026-03-04). Confirm
   the structure matches first; numeric drift is normal.
6. **Run shadow mode for 5 days.** Each day at the configured 6h
   schedule. Capture all artifacts but do NOT yet wire any dashboard
   consumer to them. Inspect manually each morning.

## What to look for during live shadow

| Check | Expected | What to do if not |
|---|---|---|
| Pipeline completes without `FetchError` every run | ✅ | Inspect `logs/gateway.jsonl` for the failing endpoint; usually a SOAP fault or 4xx |
| `confidence: high` or `medium` | ✅ | If `low` or `blocked`, fix the warning before promoting to operational |
| `freshness.status == "LIVE"` | ✅ | If `STALE`, the snapshot is older than the scheduler interval — schedule misfire |
| KPI numbers within ±5% day-on-day | ✅ | Big jumps usually mean status mapping bugs or revenue filter regressions |
| Channel rev vs total rev gap < 5% | ⚠️ likely > 5% in early runs | Driven by bookings without `source` (issue F1 in `unresolved-issues.md`) — surface in dashboard, don't fudge |
| Faye agrees occupancy/ADR feel right | ✅ | If she disagrees, that's a real semantic bug we need to find |

## Recommendation

**Approve building a "trust ladder":**

| Stage | Trigger | What it unlocks |
|---|---|---|
| 1. Offline shadow (now) | This delivery | Stephen + Faye review of the *shape* of the output |
| 2. Live shadow (~1 week away pending creds) | SOAP password + REST key recovered/re-issued | 5-day live capture, daily Faye check-in |
| 3. Operational MVP | Faye approves at least 3 of 5 shadow days | Dashboard reads the feed |
| 4. Full Phase 1 cutover | Operational MVP runs stable 2 weeks | Decommission Right Revenue dependency for Tier 1 KPIs |

This sequence is the cheapest way to get to a trustworthy production
state. Each gate is verifiable.
