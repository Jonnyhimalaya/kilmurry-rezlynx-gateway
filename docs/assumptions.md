# Assumptions — Phase 1 First Cut

These are the assumptions baked into the code. If any of these is wrong,
the corresponding module is the place to update.

## PMS / Auth

1. **Kilmurry's active PMS is Guestline RezLynx (cloud).** HotSoft is legacy
   and may still be reachable on `api.kilmurrylodge.com:8600` but is not the
   build target.
2. **Phase 1 SOAP auth uses the dedicated `KILMURRY_API` service account.**
   Known values: Interface ID `727`, Site ID `KILMURRY`, Operator Code
   `KILMURRY_API`, plus the password re-issued/tested by Gary Hunt.
3. **Report Data REST auth is separate and still pending.** The revenue side
   requires the Report Data base URL, endpoint paths, and `X-API-KEY`; the
   SOAP password alone does not unlock authoritative revenue.
4. **Read-only access for Phase 1.** No writes back to RezLynx. Live probe on
   2026-05-12 confirmed `LogIn`, `pmsbkg_BookingSearch`, and
   `pmsfoh_GetAvailability` work. `pmsint_GetRooms` is explicitly denied for
   this user. No create/amend/cancel PMS method is used by the gateway.

## Data shape

5. **A reservation is "active on target_date" if `arrival_date <= target_date <
   departure_date` AND status is `BOOKED` or `IN_HOUSE`.** All KPI math
   (occupancy, ADR, RevPAR, segment/channel mix) uses this set.
6. **`rooms_available` for KPI purposes is inventory minus out-of-order rooms.**
   This matches typical RR-style definitions but Faye should validate.
7. **`adr_eur = room_revenue / rooms_sold`** at the snapshot level. If RezLynx
   exposes ADR directly we should prefer that and keep this as fallback.
8. **`revpar_eur = room_revenue / rooms_available`** similarly.
9. **Cancellations and no-shows count toward "today" if their arrival_date
   equals target_date.** Not necessarily when they were cancelled.
10. **Each `ReservationRecord.rooms = 1`** — i.e. each row is one room-night.
    Group bookings that span multiple rooms must be expanded by the adapter.
11. **All currency is EUR.** No multi-currency handling in v1.
12. **All datetimes are UTC.** Local-time conversion is the dashboard's job.

## OneDrive / desktop

13. **OneDrive sync is already configured on Jack's Cowork PC** and points
    at a folder reachable as a normal local path. The gateway writes to
    that local path; OneDrive does the cloud upload.
14. **The published OneDrive folder is the agreed
    `Right Revenue Gateway/` subfolder.** Path is configurable in
    `settings.toml`.
15. **The OpenClaw consumer reads `*-latest.json`** for routine refresh,
    and falls back to scanning the timestamped feed list when it needs
    historical context.

## Operations

16. **Schedule = every 6 hours**, at 00:00 / 06:00 / 12:00 / 18:00 UTC. The
    desktop runs `gateway run` via Windows Task Scheduler. The gateway
    itself does not have to be running as a daemon.
17. **A failed fetch is treated as "no new data"**, not "blocked
    dashboards". The previous feed remains in place and ages into STALE
    / BLOCKED naturally.
18. **Logs live alongside the code in `./logs/`.** Stephen and Jack can
    inspect them on the PC. They are NOT published to OneDrive.

## Data minimisation

19. **No guest PII is ever written to OneDrive** in Phase 1. We publish
    aggregates, counts, operational state, and reservation IDs only. The
    feed `provenance.record_counts` exposes counts but no names / emails
    / addresses.
20. **Raw PMS payloads stay on the desktop side.** If we ever need them
    on OneDrive we add an opt-in flag, not a default.
21. **The desktop-side fetch/report workflow is LLM-free.** The desktop is the
    GDPR-compliant data house. No LLM calls are made while fetching, parsing,
    transforming, validating, logging, or publishing PMS-derived reports.
    Future LLM usage, if any, must sit downstream of the minimised aggregate
    feed and must not receive raw PMS records by default.
