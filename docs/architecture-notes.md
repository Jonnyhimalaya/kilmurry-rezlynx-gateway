# Architecture Notes — First Implementation Cut

Stephen / 11 May 2026.

## Shape

```
src/kilmurry_gateway/
  __init__.py             # SCHEMA_ID = "kilmurry.rezlynx.revenue_feed.v1"
  cli.py                  # Click CLI: run / fetch / validate / publish / backfill / watch / sample / doctor
  __main__.py             # python -m kilmurry_gateway
  config.py               # TOML + env config loader (settings.toml + secrets.toml)
  logging_setup.py        # human stderr + JSONL file logging
  run_context.py          # per-run id, timestamps, hostname
  models.py               # ReservationRecord / InventorySnapshot / RezLynxSnapshot
  validate.py             # contract validator (light, structural)
  pipeline.py             # orchestrates fetch -> transform -> validate -> publish
  adapters/
    base.py               # RezLynxAdapter ABC + FetchError
    mock.py               # MockRezLynxAdapter (deterministic, seed-driven)
    guestline_rest.py     # SKELETON — TODOs marked, raises until wired
  transform/
    feed_builder.py       # snapshot -> v1 feed dict
    summary_builder.py    # feed -> HTML summary (Jinja2)
  publish/
    writer.py             # atomic write of JSON / HTML / manifest, latest pointer
  templates/
    summary.html.j2       # human-readable summary template
config/
  settings.toml           # non-secret (committable)
  settings.toml.example
  secrets.toml.example    # gitignored, exports values as env vars at load
tests/
  test_pipeline.py        # smoke through full pipeline
  test_transform.py       # KPI math, segment/channel logic, Avvio normalisation
  test_validate.py        # contract validator
```

## Key architectural choices

### 1. Adapter pattern for PMS access
The rest of the pipeline depends only on `RezLynxAdapter` (in `adapters/base.py`).
A `MockRezLynxAdapter` produces realistic-looking data deterministically. A
`GuestlineRestAdapter` skeleton sits next to it, ready to wire once credentials
+ endpoint docs are available.

**Why:** the brief explicitly flags PMS API access as the biggest unknown.
This isolates that unknown from everything else. Today, the whole pipeline
(JSON shape, HTML, OneDrive write, scheduler, validator) is testable
end-to-end without a single live PMS call.

### 2. Desktop-side, LLM-free data house
The fetch/transform/report pipeline is deliberately **LLM-free**. It runs as
ordinary deterministic code on the desktop: SOAP/REST fetches, parsing,
validation, KPI transforms, JSON/HTML writes, and local logs.

**Why:** the desktop side is the GDPR-compliant data house. PMS payloads and
raw operational data stay there. Any future LLM layer must consume only the
minimised published aggregates/briefing feed, never sit inside the PMS fetch
workflow or receive raw PMS records by default.

### 3. OneDrive is "just a local path"
We do NOT use the Microsoft Graph API. We write to a local folder that
OneDrive sync is already watching. OneDrive does the cloud upload.

**Why:** simpler, fewer creds, no Graph API consent flow, matches the way
Jack's PC is already set up. Add Graph API later only if reliability demands it.

### 4. Atomic writes
Every artifact is written to `name.ext.tmp` and renamed into place. OneDrive
sync never sees a half-written file. Important: a half-uploaded feed
would either silently corrupt the dashboard or be flagged stale incorrectly.

### 5. JSON + HTML + manifest, every run
- **JSON** is the dashboard contract (`kilmurry.rezlynx.revenue_feed.v1`).
- **HTML** is for Jack / Faye / Stephen to manually inspect during MVP.
- **Manifest** is a tiny sidecar JSON with run id, hostname, timing, file
  sizes, warnings. Cheap insurance for debugging.

### 6. "Latest" pointer files
Optional but on by default: each run also writes
`rezlynx-revenue-feed-latest.json` and `rezlynx-summary-latest.html`.

**Why:** the OpenClaw consumer can read `*-latest.json` without having to
scan timestamps. Timestamped immutable files are still the source of truth
and kept indefinitely.

### 7. Freshness & confidence
- `LIVE` if feed is <=8h old, `STALE` <=18h, `BLOCKED` otherwise (per
  `phase-1-data-contract.md`).
- `confidence` derived from validation warnings:
  - `high` = no warnings
  - `medium` = 1 warning (missing optional block)
  - `low` = 2+ warnings
- Validation warnings are emitted by the transform layer when expected
  fields are absent (no `market_segment`, zero `rooms_available`, etc).

### 8. Failure behaviour
On `FetchError`, the pipeline returns `status: "fetch_failed"` and writes
no feed JSON. Per the spec: "do not publish a false-success JSON on
fetch failure." OpenClaw's consumer can detect this either by:
- absence of a new timestamped file, or
- by reading the local JSONL log, or
- (future) by an explicit failure-summary HTML that does not overwrite
  the latest valid feed.

### 9. Schema is versioned from day one
`schema: "kilmurry.rezlynx.revenue_feed.v1"` is mandatory and validated.
The next breaking change becomes `v2`. OpenClaw's consumer can pin a
required version.

### 10. Determinism in mock mode
Mock adapter is seeded by (date, seed). Same date → same KPI block.
Useful for tests and for showing Faye a stable HTML preview during
design conversations.

### 11. Avvio capitalisation quirk handled
Per discovery notes (`reslynx-hotsoft-api-intelligence.md`), Avvio
sometimes appears as "AVVIO" in PMS data and sometimes as "Avvio".
The transform layer normalises both to "Avvio". A test asserts this.

## What I deliberately did NOT build

- A real JSON Schema file. The validator is a hand-written light-touch
  check. Easy to upgrade to `jsonschema` later (`samples/feed.schema.json`).
- Graph API / OneDrive client. Local-folder write only.
- Persistent state (last-good feed history, sqlite, etc). The filesystem
  is the audit trail; manifest files are the per-run record.
- The Guestline REST client wiring. Skeleton only.
- Windows-specific scheduling code. We use Task Scheduler (documented).
- Rate-limit/retry logic. Not relevant for mock; trivial to add to the
  real adapter once we know rate limits.
- Email or alerting on failure. Out of scope for first cut.

## File contract summary

| Output | Filename pattern | Purpose |
|---|---|---|
| JSON feed | `feeds/rezlynx-revenue-feed-{date}-{ts}.json` | Dashboard input |
| Latest feed | `feeds/rezlynx-revenue-feed-latest.json` | Consumer convenience |
| Summary | `summaries/rezlynx-summary-{date}-{ts}.html` | Human inspection |
| Latest summary | `summaries/rezlynx-summary-latest.html` | Open in browser |
| Manifest | `manifests/rezlynx-manifest-{date}-{ts}.json` | Run metadata |

`{date}` = `YYYY-MM-DD`, `{ts}` = `YYYY-MM-DDTHHMMSSZ`.
