# Kilmurry Desktop Data Gateway

**Phase 1 MVP — Right Revenue Replacement.**
Live-cutover-ready first implementation cut.

The gateway is the **only component allowed to talk to the live PMS**.
It pulls data from Guestline RezLynx (SOAP + Report Data REST), normalises
it to a stable contract, and writes JSON + HTML + manifest artifacts into
a OneDrive-synced folder. OpenClaw then consumes the OneDrive output
downstream. Per the agreed architecture, OpenClaw never holds PMS
credentials and never calls the PMS directly.

```
Guestline RezLynx (SOAP + REST) ─► Desktop Data Gateway ─► OneDrive ─► OpenClaw ─► RR-style dashboards
                                   (this repo)                          (consumer)
```

See `docs/` for the full set of design and operational notes:

- `live-access-decision-note.md` — which RezLynx mechanisms we use and why
- `source-inventory-matrix.md` — SOAP / REPORT-DATA / DASHBOARD / EVENT / LANSync assessment
- `field-mapping.md` — every MVP output field → live source + transform rule
- `architecture-notes.md` — implementation architecture
- `assumptions.md` — baked-in assumptions
- `unresolved-issues.md` — what blocks live cutover (priority-ordered)
- `shadow-readiness.md` — current shadow-mode readiness recommendation
- `how-to-run.md` — run/test/deploy instructions
- `handoff-to-desktop.md` — porting to Jack's Cowork PC

---

## Adapter modes

| Mode | What it does | Use case |
|---|---|---|
| `mock` | Synthetic deterministic data | Unit tests, quick visual review |
| `hunter_replay` | Real Kilmurry RezLynx CSVs (2026-03-04 snapshot) | **Offline shadow mode** — proves transform handles real data without needing live credentials |
| `live` | SOAP `pmsbkg_BookingSearch` + `pmsavl_AvailAndRateV2` + Report Data `booked-revenue` REST | Production — needs `REZLYNX_PASSWORD` and `REZLYNX_REPORT_DATA_API_KEY` |

## Quick start

```bash
cd gateway
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run synthetic mock
gateway sample

# Run REAL Kilmurry data offline replay (proves the whole pipeline)
gateway hunter-replay

# Look at what came out (shipped sample artifacts)
ls samples/hunter-replay-out/feeds/
ls samples/hunter-replay-out/summaries/

# Smoke tests (18 pass)
pytest
```

## Status

| Capability | Status |
|---|---|
| Project scaffold, packaging, CLI | ✅ |
| `kilmurry.rezlynx.revenue_feed.v1` schema + validator | ✅ |
| Mock adapter (deterministic) | ✅ |
| **Hunter Replay adapter (real CSVs)** | ✅ **18/18 tests pass, real numbers credible** |
| SOAP adapter (skeleton, validated envelope shape) | ✅ shaped, awaiting password |
| Report Data REST adapter (skeleton) | ✅ shaped, awaiting API key |
| Composite live adapter (SOAP + REST fusion) | ✅ |
| Atomic writes, latest-pointer, manifest | ✅ |
| Backfill / dry-run / watch / hunter-replay / soap-probe CLI | ✅ |
| Channel revenue cross-check warning | ✅ |
| Avvio + status casing normalisation | ✅ |
| **Live cutover** | ⏳ blocked on SOAP password + REST API key (see `docs/unresolved-issues.md`) |

## What's verified against real Kilmurry data

Running `gateway hunter-replay` against the 2026-03-04 production
snapshot produces:

```
Occupancy:   66.2%
ADR:         €80.67
RevPAR:      €53.41
Room Rev:    €7,744.00
Rooms sold:  96 / 145 available
Operations:  34 arrivals, 75 departures, 62 stayovers,
             80 in-house, 2 cancellations, 0 no-shows
Segments:    DIRECT 55% / CORPORATE 16% / OTA 16% / GDS 13%
Channels:    49 unmapped + Avvio 18 / SynXis 13 / B.com 9 / Expedia 7
```

The unmapped channel cluster is a **real data finding** (49 bookings
have no `source` field) and is surfaced via a validation warning rather
than silently fudged. See `docs/unresolved-issues.md#F1`.
