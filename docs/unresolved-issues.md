# Unresolved Issues — Phase 1 Live Cutover

Sorted by what blocks live cutover most.

## 🔴 Blockers — must resolve before live cutover

### B1. REST credentials still missing for authoritative revenue

- **What:** `X-API-KEY` and base URL for the Report Data API. Hunter asked Gary on 2026-01-20 but archive shows no confirmation of issuance.
- **Action:** Escalate to gary.hunt@theaccessgroup.com. Confirm:
  - Is the Report Data API live for Kilmurry?
  - What is the base URL?
  - Was a key issued? If so, where is it now?
- **Impact:** Without this, `room_revenue_eur` falls back to per-reservation contract values amortised across stay nights. Numbers will be approximate, confidence drops to `medium`.

### B2. Confirm REST endpoint paths
- **What:** Even with the key, we need confirmed paths/parameter shape for:
  - `booked-revenue` (date range, siteId, groupId)
  - `dashboard-sales` (same)
- **Action:** Ask Gary Hunt for the developer docs or one sample successful request. Hunter's CSV exports prove the data exists; we just need the endpoint.
- **Impact:** Without confirmed paths, the REST adapter will 404 until adjusted.

## ✅ Resolved live-access items

### R1. SOAP password recovered and live-tested
- **Status:** Resolved 2026-05-12. Password stored only in `config/secrets.toml` (gitignored, chmod 600; do not commit or paste).
- **Verified:** `LogIn` succeeds; `pmsbkg_BookingSearch` returns live reservations; `pmsfoh_GetAvailability` returns live per-room-type inventory. A SOAP-only live report was published to `output-live-test/` and validated.
- **Caveat:** `pmsint_GetRooms` is explicitly denied for this API user, so do not rely on that method for room-capacity/OOS data.

## 🟡 High — data semantics to validate with Faye

### F1. 49/96 active bookings have NO `source` field on 2026-03-04
- **Evidence:** 51% of active reservations in the Hunter sample have empty `source`. Their revenue lines exist in Report Data with `media_source` values like `EMAIL`, `PHONE`, `WALK_IN`, `WEBSITE` — but we can't join them because the booking record has no source.
- **Symptom:** channel-revenue cross-check warning fires (we see "Unmapped" channel rooms with €0 revenue, and total channel revenue is 55.7% short of KPI room revenue).
- **Two possible fixes** (Faye walkthrough should pick):
  1. Use the **booking's `extra_fields.system_source`** (e.g. `Roomlynx`, `RoomlynxRest`) as a fallback when `source` is empty.
  2. Build a heuristic that distributes unmatched bookings proportionally across `EMAIL`/`PHONE`/`WEBSITE`/`WALK_IN` based on revenue-line distribution.
- **Phase 1 acceptable behaviour:** publish the cross-check warning and let dashboard surface the gap, rather than silently fudge.

### F2. Channel mapping for direct bookings
- **What:** Avvio is the booking engine for the direct website. Report Data exposes `WEBSITE` (and `EMAIL`/`PHONE`/`WALK_IN`) as separate direct channels. Should they collapse into one "Direct" channel in the dashboard, or surface separately?
- **Action:** Ask Faye.

### F3. Total inventory reconstruction
- **What:** RezLynx `available_rooms` = **rooms remaining after sales**, not total capacity. We reconstruct total = `available + sold`. This produces 145 rooms for Kilmurry on 2026-03-04. Is that the right number? Property is described as ~50 rooms operationally.
- **Likely explanation:** The 145 figure spans the room_type set including apartments (APT1) and contract rooms (CTEMP), plus there may be multi-room reservations. **Faye should validate**: what's the real "rooms available" she expects to see?
- **Code:** see `transform/feed_builder.py` lines around `rooms_capacity = rooms_remaining + rooms_sold`.

### F4. No-show definition spot-check
- **Evidence:** SOAP statuses include `NoShow` (2 in sample); Report Data has `is_no_show=True` flag (6 rows in sample). These are slightly different counts.
- **Action:** Confirm with Faye whether reporting should count:
  - SOAP `NoShow` status reservations, OR
  - Report Data `is_no_show=True` revenue rows.
- **Current behaviour:** SOAP status. This is consistent with `operations.no_shows_today` semantics ("how many bookings became no-shows").

## 🟢 Low — operational

### O1. `rooms_out_of_order` field
- **Status:** Not in any source we've seen. Default 0 in feed. Live test confirmed `pmsint_GetRooms` is denied for the API user, so OOS cannot come from that path without Access granting another method.
- **Action:** Worth asking Gary Hunt if RezLynx exposes OOS rooms through any path (SOAP, REST, LANSync).
- **Impact:** RevPAR slightly inflated if OOS is non-zero. Marginal.

### O2. LANSync, deferred
- **Status:** Engineer was booked for 2026-03-05 install. Contract paused. No LANSync today.
- **Action:** Reconsider for Phase 1.5 if pickup or transaction-level data becomes needed and REST gaps appear.

### O3. Event Archive REST
- **Status:** Hunter requested key 2026-01-20, no confirmation in archive.
- **Action:** Defer to Phase 2 (pickup, real-time bookings).

### O4. Rate plan / room type mix in feed
- **Status:** `rates.active_rate_plans_count` and `rates.room_types_count` only (counts, no per-plan breakdown).
- **Action:** Faye walkthrough — is per-rate-plan or per-room-type revenue breakdown needed in MVP? If yes, the data is available; add a Phase 1.5 feed block.

### O5. Dashboard sales cross-check
- **Status:** Adapter and model support `DashboardSalesLine`, but cross-check is not wired into the composite yet.
- **Action:** Once REST is live, wire `dashboard-sales` ACCOM total into provenance.cross_checks so dashboards can show "our number agrees with PMS dashboard within X%".

### O6. Multi-day backfill
- **Status:** `gateway backfill --from --to` works but each day re-fetches independently. Live SOAP currently calls BookingSearch once per arrival date in the configured window.
- **Action:** Add batching/caching or narrow windows before production backfills; avoid hammering SOAP until rate limits are confirmed.

### O7. Mapping `distribution_channel_id` integers
- **Status:** Captured in raw archive but not used. Gary Hunt explicitly flagged this needs a mapping table.
- **Action:** Phase 1.5. Not needed for Phase 1 because `source` (display name) is sufficient when populated.
