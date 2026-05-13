# KilmurryBot Server Handoff — Desktop Gateway → OneDrive → Dashboards

Status: draft, updated 2026-05-12.

## Boundary

The desktop gateway is the GDPR-compliant data house. It stays LLM-free and deterministic:

1. Fetch live PMS data from RezLynx SOAP / Report Data REST.
2. Normalise into a minimised JSON contract.
3. Write JSON + human summary + manifest to a local OneDrive-synced folder.
4. KilmurryBot/server-side consumers read the JSON and populate dashboards for Faye, Kate, Ciara, and Jack.

No raw PMS payloads, guest names, emails, addresses, or profile records are published to OneDrive by default.

## Current live access

| Source | Status | Use |
|---|---|---|
| RezLynx SOAP `LogIn` | live-tested | Session auth |
| RezLynx SOAP `pmsbkg_BookingSearch` | live-tested | reservations, arrivals, departures, stayovers, cancellations/no-shows, segment/channel room counts |
| RezLynx SOAP `pmsfoh_GetAvailability` | live-tested | per-room-type remaining inventory |
| RezLynx SOAP `pmsint_GetRooms` | denied | do not use for OOS/capacity unless Access grants it |
| Report Data REST `booked-revenue` | pending | authoritative accommodation revenue, ADR/RevPAR, segment/channel revenue |
| Report Data REST `dashboard-sales` | pending | dashboard cross-check |
| Event Archive REST | deferred | pickup/near-real-time Phase 2 |

## OneDrive output contract

Routine consumer path should use latest pointers:

- `feeds/rezlynx-revenue-feed-latest.json`
- `summaries/rezlynx-summary-latest.html`
- `manifests/rezlynx-manifest-*.json` for audit/debug

Timestamped immutable files are retained for history.

## Consumer rule for KilmurryBot

KilmurryBot should treat the JSON as the source of truth and never scrape the HTML summary.

Recommended server-side flow:

1. Poll or filesystem-watch the OneDrive folder.
2. Read `rezlynx-revenue-feed-latest.json`.
3. Validate:
   - `schema == "kilmurry.rezlynx.revenue_feed.v1"`
   - `freshness.status in ["LIVE", "STALE"]`
   - reject/flag `BLOCKED`
   - inspect `confidence` and `_notes`
4. Persist a copy/server snapshot for dashboard history.
5. Fan out into dashboard-specific modules:
   - Faye: revenue, occupancy, pickup/risk, competitor-rate context, hot dates.
   - Kate: content/event opportunities, demand signals, campaign timing.
   - Ciara: sales/account opportunities, dates with compression or gaps, corporate segment signals.
   - Jack: operational overview, data health, PMS/API status, alert queue.

## Faye dashboard target after reviewing 12 May upload

Faye's uploaded dashboard is a full weekly commercial control pack, not a simple live PMS widget. It has 15 sections: executive next-7-days, monthly forward position, annual overview, channel mix, segment mix, cancellations, competitor rates, hot dates, concert pickup, restrictions, Avvio, Booking.com, Expedia, commission analysis, and apartments.

Reference analysis lives at:
`consultancy/clients/kilmurry-faye/faye-dashboard-upload-analysis-2026-05-12.md`

Recommended additions / changes:

- **Data confidence strip:** LIVE/STALE/BLOCKED, last run time, source mix, warnings.
- **Trust ladder banner:** SOAP-live now; Report Data REST pending for authoritative revenue.
- **Revenue caveat tile:** if `Report Data source disabled`, mark ADR/RevPAR as estimated/contract-value based or hide them.
- **Action queue above Section 1:** sortable critical actions extracted from revenue gaps, cancellation spikes, rate anomalies, apartment vacancies, and channel issues.
- **Source labels per section:** LIVE / MANUAL / DERIVED / PENDING REST.
- **Pace / pickup trend:** built from retained snapshots; Event Archive REST later if available.
- **Rate opportunity matrix:** date × occupancy × comp-rate delta × hot-date flag.
- **Channel leakage warning:** show unmapped/direct channel gaps rather than hiding them.
- **Hot dates overlay:** combine events/hot dates with occupancy, remaining inventory, restrictions, and competitor pricing.
- **Cross-role nudges:** “Send to Kate”, “Send to Ciara”, “Ask Jack” actions so the same dashboard drives the commercial triangle.
- **Net ADR focus:** direct/OTA gross rate is less important than post-commission net ADR.
- **Audit/provenance footer:** exactly which files/API snapshots drove each section.

## Dashboard refresh contract

After the 2026-05-12 Faye/Kate/Ciara/Jack dashboard rebuild, KilmurryBot should use the detailed dashboard updater contract in:

`projects/right-revenue/gateway/docs/kilmurrybot-dashboard-refresh-contract.md`

This file defines the six-hour refresh loop, source-state vocabulary, production dashboard paths/ports, Faye/Kate/Ciara/Jack dashboard schemas, output snapshot filenames, and smoke checks. The critical rule is: never present dummy/manual/demo data as live.

## Known little fixes to track

- Wire production config cleanly: `adapter_mode="live"`, `live_sources=["soap"]` until REST credentials arrive.
- Confirm exact OneDrive folder path on Jack's desktop.
- Add a KilmurryBot ingestion validator for `v1` JSON before dashboard fan-out.
- Decide whether SOAP contract-value revenue should be hidden, labelled as estimate, or excluded until Report Data lands.
- Add OOS-room source only if Access grants a method or Faye can supply a reliable alternative.
- Optimise SOAP booking fetch window before production backfills; current live adapter calls BookingSearch per arrival date.
- Add dashboard regression checks so Faye/Kate/Ciara/Jack pages don't break when JSON schema changes.
