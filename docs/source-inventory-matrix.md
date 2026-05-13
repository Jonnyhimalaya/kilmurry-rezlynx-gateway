# RezLynx Source Inventory Matrix

For each candidate live data source, evidence-based assessment.

Legend: ✅ proven, 🟡 likely, ⛔ blocked, — n/a

| Mechanism | Kilmurry-proven? | Auth | Reservations | Availability | Room revenue | Cancellations | No-shows | Segment | Channel/Source | Phase 1 use |
|---|---|---|---|---|---|---|---|---|---|---|
| **SOAP `pmsbkg_BookingSearch`** | ✅ (443 rows in Hunter 2026-03-04) | Interface ID + Operator Code + Password (basic creds) | ✅ direct | — | 🟡 via `total_cost_*` (NOT recommended for realised revenue) | ✅ status=`Cancelled` | ✅ status=`NoShow` | ✅ in `extra_fields.market_segment` | ✅ in `source` (human) + `extra_fields.distribution_channel_id` (int) | **PRIMARY for ops** |
| **SOAP `pmsfoh_GetAvailability`** | ✅ live-tested 2026-05-12 | same | — | ✅ per-date per-room-type | — | — | — | — | — | **PRIMARY for live inventory** |
| **SOAP `pmsavl_AvailAndRateV2`** | ✅ (1200 rows in Hunter 2026-03-04), but live probe returned no package rows | same | — | 🟡 available/rate package search | — | — | — | — | — | **Defer**: use `pmsfoh_GetAvailability` for live inventory |
| **SOAP `pmsbkg_GetReservationTransactions`** | 🟡 (granted in sandbox, not in Hunter sample) | same | — | — | 🟡 transaction-level | — | — | — | — | **Defer**: Report Data is cleaner |
| **SOAP `pmsprf_GetProfileSummaryV4`** | 🟡 | same | — | — | — | — | — | — | — | **Defer**: GDPR-sensitive, no Phase 1 need |
| **REST Report Data `booked-revenue`** | ✅ (792 rows in Hunter 2026-03-04) | X-API-KEY | — | — | ✅ authoritative, `revenue_type_long_description` split, `cancelled` + `is_no_show` flags | ✅ via flag | ✅ via flag | ✅ short codes | ✅ short codes | **PRIMARY for revenue** |
| **REST Report Data `dashboard-sales`** | ✅ (188 rows in Hunter 2026-03-04) | X-API-KEY | — | — | ✅ totals by `analysis_code` (ACCOM, F&B, etc.) | — | — | — | — | **Cross-check only** (validate Accommodation total = sum of `booked-revenue` Accommodation) |
| **REST Event Archive** | ⛔ (Hunter requested key 2026-01-20, no confirmation in archive) | X-API-KEY | 🟡 event stream | — | — | — | — | — | — | **Phase 2+**: pickup, near-real-time |
| **LANSync (local SQL)** | ⛔ scheduled 2026-03-05, never installed (contract paused) | Windows service + local SQL | 🟡 full | 🟡 full | 🟡 transactional | 🟡 | 🟡 | 🟡 | 🟡 | **Phase 1.5+** if API gaps emerge |

## Notes

- "Kilmurry-proven" means: we have an actual extract from Kilmurry that came from this mechanism.
- 2026-05-12 live probe confirmed `LogIn`, `pmsbkg_BookingSearch`, and `pmsfoh_GetAvailability` work with the `KILMURRY_API` password. `pmsint_GetRooms` was explicitly denied (`Access to this web method is not permitted`).
- SOAP method list confirmed by Gary Hunt at Access in his 2026-01-20 email; password was sent separately and is not in the email archive.
- The 5 `source` channel names in the Hunter bookings sample (Avvio / Booking.com / Expedia / HotelBeds / SynXis) are stored as human strings — *no integer mapping table needed for Phase 1*. The integer `distribution_channel_id` is captured in raw archive for future use.
- Hunter's 2026-03-04 snapshot pre-dates LANSync installation by 1 day. So everything Hunter exported came from SOAP + REST. This is the proven path.
- All sample fields, distinct value counts, and field semantics are documented in `field-mapping.md`.
