# KilmurryBot Dashboard Refresh Contract — Faye/Kate/Ciara/Jack

Status: active handoff, updated 2026-05-12 after live dashboard rebuild.
Audience: KilmurryBot / server-side updater that refreshes dashboards every 6 hours.

## Non-negotiable rule

KilmurryBot must never present placeholder/manual/demo data as live. Every dashboard section must carry one of these source states:

| State | Meaning | Allowed wording |
|---|---|---|
| `LIVE` | Directly from a current machine feed/API/file, validated this cycle | “live”, “fresh”, “from RezLynx SOAP”, “from hot-dates JSON” |
| `STALE` | Same source, but older than freshness SLA | “stale — last updated …” |
| `DERIVED` | Computed from live/manual inputs, e.g. demand-gap action from Faye pack + hot dates | “derived signal”, “AI recommendation from labelled inputs” |
| `MANUAL` | From Faye/Kate/Ciara supplied pack, workbook, or hand-entered list | “manual/source pack” |
| `DEMO` | Placeholder UI/data scaffold | “demo placeholder — do not use for decisions” |
| `PENDING` | Intended source not wired yet | “pending REST/API/CRM access” |
| `BLOCKED` | Expected live source failed validation or fetch | “blocked — do not refresh this panel” |

If the source is mixed, show the weakest/most cautious state at panel level and expose line-level provenance where possible.

## Production dashboard surfaces

| Person | Purpose | Repo/path on Kilmurry server | Internal port | Public port | Main update target |
|---|---|---|---:|---:|---|
| Faye | Revenue control cockpit | `/home/fayeuser/kilmurry-faye-mission-control` | 3338 | 3339 | Revenue, pace, cancellations, restrictions, OTA/direct, apartments, action queue |
| Kate | Marketing/content cockpit | `/home/kateuser/kilmurry-marketing-mc` | 3336 | 3337 | Campaign opportunities, content calendar, SEO/reputation placeholders, demand signals |
| Ciara | Sales/account cockpit | `/home/ciarauser/kilmurry-ciara-mission-control` | 3340 | 3341 | Corporate pipeline, hot-date sales opportunities, account follow-ups, apartment/long-stay leads |
| Jack/main | Owner/ops/data-health cockpit | `/home/clawuser/mission-control` | 3333 | 3333 | Data health, OpenClaw status, cross-agent/system overview |

Current rebuild commits:
- Faye: `35aea2f`
- Kate: `dd058fc`
- Ciara: `886d9fd` local only; GitHub remote currently returns repository-not-found
- Jack/main: `1d99e41`

## Six-hour refresh loop

Every run:

1. Read source files/API outputs.
2. Validate schemas and freshness.
3. Build one canonical `kilmurry.dashboard_refresh.v1` snapshot.
4. Write a timestamped snapshot + `dashboard-refresh-latest.json`.
5. Fan out into dashboard-specific data modules/APIs.
6. Rebuild or trigger revalidation only if input changed.
7. Run smoke checks against `/`, `/api/status`, and any updated API endpoint.
8. Append a run manifest with source states, warnings, and changed panels.

Do not overwrite a previously-good live panel with failed/empty data. Mark it `STALE` or `BLOCKED` instead.

## Canonical input feeds KilmurryBot should know

### 1. RezLynx revenue feed v1

Preferred latest path from desktop/OneDrive pipeline:

- `feeds/rezlynx-revenue-feed-latest.json`
- Schema: `kilmurry.rezlynx.revenue_feed.v1`

Known server-side shared copies / fixtures as of 12 May:

- `/home/clawuser/shared/kilmurry-shared-ai/right-revenue-daily-2026-05-11.json`
- `/home/clawuser/shared/kilmurry-shared-ai/right-revenue-daily-feed-sample-fixture.json`
- `/home/clawuser/shared/kilmurry-shared-ai/right-revenue-daily-feed-schema-v1.json`

Envelope:

```jsonc
{
  "schema": "kilmurry.rezlynx.revenue_feed.v1",
  "generated_at_utc": "2026-05-12T06:00:00Z",
  "as_of_utc": "2026-05-12T06:00:00Z",
  "source_system": "guestline-rezlynx",
  "source_site": "KILMURRY",
  "confidence": "high|medium|low|blocked",
  "freshness": { "status": "LIVE|STALE|BLOCKED", "age_minutes": 0, "poll_interval_hours": 6 },
  "kpi": {
    "rooms_available": 108,
    "rooms_sold": 80,
    "rooms_out_of_order": 0,
    "room_revenue_eur": null,
    "occupancy_pct": 74.1,
    "adr_eur": null,
    "revpar_eur": null
  },
  "operations": {
    "arrivals_today": 0,
    "departures_today": 0,
    "stayovers_today": 0,
    "in_house_rooms": 0,
    "cancellations_today": 0,
    "no_shows_today": 0
  },
  "segments": { "source": "rezlynx-market-segment", "items": [] },
  "channels": { "source": "rezlynx-media-source", "items": [] },
  "rates": { "active_rate_plans_count": 0, "room_types_count": 0 },
  "provenance": { "gateway_run_id": "...", "sources": {}, "validation_warnings": [] }
}
```

Important: `room_revenue_eur`, `adr_eur`, `revpar_eur`, segment revenue and channel revenue are **not authoritative** until Report Data REST is wired. If absent/null/estimated, Faye/Kate/Ciara panels must say `PENDING REST` or `MANUAL`, not `LIVE`.

### 2. Hot dates

Path:

- `/home/clawuser/shared/hot-dates-2026.json`

Use for:

- Faye: demand overlays, rate/restriction warning context
- Kate: content/campaign calendar opportunities
- Ciara: corporate/group sales follow-up windows
- Jack: owner overview / upcoming pressure dates

State: `LIVE` if parsed successfully and file mtime is acceptable; otherwise `STALE`.

### 3. Competitor rate intelligence

Path:

- `/home/clawuser/shared/weekly-rate-intel-latest.json`

Use for:

- Faye: competitor rate matrix and rate opportunity decisions
- Kate: campaign timing when Kilmurry is under/over comp set
- Ciara: group/account urgency when compression is visible

State: `LIVE` only if latest file parses and dates cover the dashboard horizon. Otherwise `STALE` or `BLOCKED`.

### 4. Faye 12 May control-pack reference

Paths:

- Dashboard embedded copy: `/home/fayeuser/kilmurry-faye-mission-control/public/faye-revenue-dashboard-2026-05-12.html`
- Local analysis: `consultancy/clients/kilmurry-faye/faye-dashboard-upload-analysis-2026-05-12.md`

Use as reference layout/spec only. Values from this pack are `MANUAL` unless re-sourced from a current JSON/API file.

## Dashboard-specific schemas

### Faye: `kilmurry.dashboard.faye.v1`

Faye is the primary revenue user. Preserve her 15-section control-pack mental model:

1. Executive next 7 days
2. Monthly forward position
3. Annual overview
4. Channel source breakdown
5. Market segment breakdown
6. Cancellations
7. Competitor rates
8. Hot dates
9. Concert/event pickup
10. MLOS / CTA / CTD restrictions
11. Avvio/direct
12. Booking.com
13. Expedia
14. Commission / net ADR
15. Apartments

Recommended JSON shape:

```jsonc
{
  "schema": "kilmurry.dashboard.faye.v1",
  "generated_at_utc": "...",
  "source_state": { "overall": "LIVE|STALE|MIXED|BLOCKED", "warnings": [] },
  "command_bar": {
    "freshness_status": "LIVE|STALE|BLOCKED",
    "confidence": "high|medium|low|blocked",
    "revenue_confidence": "authoritative|manual|estimated|pending_rest",
    "last_success_utc": "..."
  },
  "action_queue": [
    { "priority": "critical|high|medium|low", "owner": "Faye|Kate|Ciara|Jack", "title": "...", "reason": "...", "source_state": "LIVE|DERIVED|MANUAL|PENDING" }
  ],
  "next_7_days": {
    "source_state": "LIVE|MANUAL|MIXED",
    "totals": { "rooms_sold": 0, "room_revenue_eur": null, "occupancy_pct": 0, "adr_eur": null, "revpar_eur": null },
    "rows": [ { "date": "YYYY-MM-DD", "rooms": 0, "revenue_eur": null, "adr_eur": null, "revpar_eur": null, "occupancy_pct": 0, "ly_spit_eur": null, "source_state": "..." } ]
  },
  "forward_position": { "months": [] },
  "channels": { "items": [] },
  "segments": { "items": [] },
  "cancellations": { "last_7_days": [] },
  "competitor_rates": { "items": [] },
  "hot_dates": { "items": [] },
  "restrictions": { "items": [] },
  "direct_and_ota": { "avvio": {}, "booking_com": {}, "expedia": {}, "commission": {} },
  "apartments": { "items": [] },
  "provenance": { "input_files": [], "api_sources": [], "manual_sources": [] }
}
```

Current live app notes:

- `/api/overview` currently returns `mode: "MANUAL"`; do not treat it as live revenue.
- `/api/status` confirms the app is alive, not that the revenue data is live.
- Rebuilt homepage explicitly labels SOAP as live and revenue as pending REST.

### Kate: `kilmurry.dashboard.kate.v1`

Kate uses revenue data as marketing triggers, not as the source of revenue truth.

```jsonc
{
  "schema": "kilmurry.dashboard.kate.v1",
  "generated_at_utc": "...",
  "source_state": { "overall": "MIXED", "warnings": [] },
  "campaign_opportunities": [
    { "date_range": "...", "trigger": "hot_date|occupancy_gap|competitor_delta|event", "recommended_action": "...", "source_state": "LIVE|DERIVED|MANUAL" }
  ],
  "content_calendar": { "items": [], "source_state": "MANUAL|LIVE" },
  "reputation": { "items": [], "source_state": "DEMO|PENDING" },
  "seo_visibility": { "items": [], "source_state": "DEMO|PENDING" },
  "revenue_signals": {
    "from_faye": [],
    "hot_dates": [],
    "competitor_rates": [],
    "source_state": "DERIVED|MIXED"
  },
  "ai_task_log": { "items": [], "source_state": "MANUAL|LIVE" },
  "provenance": { "input_files": [], "manual_sources": [] }
}
```

Current live app notes:

- `/api/revenue` returns `demo: true`; KilmurryBot must preserve/propagate that label.
- The rebuilt homepage says marketing modules are scaffolds unless tagged live.

### Ciara: `kilmurry.dashboard.ciara.v1`

Ciara needs account and pipeline actions, with demand signals from Faye/Kate.

```jsonc
{
  "schema": "kilmurry.dashboard.ciara.v1",
  "generated_at_utc": "...",
  "source_state": { "overall": "MIXED", "warnings": [] },
  "corporate_pipeline": { "items": [], "source_state": "MANUAL|LIVE|PENDING_CRM" },
  "hot_date_sales_opportunities": [
    { "date": "YYYY-MM-DD", "event": "...", "gap_or_compression": "...", "action": "...", "source_state": "DERIVED" }
  ],
  "followups_today": { "items": [], "source_state": "MANUAL|LIVE" },
  "apartments_long_stay": { "items": [], "source_state": "MANUAL" },
  "handoffs": [
    { "from": "Faye|Kate|Jack", "to": "Ciara", "message": "...", "source_state": "LIVE|DERIVED|MANUAL" }
  ],
  "provenance": { "input_files": [], "manual_sources": [] }
}
```

Current live app notes:

- Ciara currently shares several Faye-style API routes returning manual data; do not treat as live CRM.
- Rebuilt homepage labels corporate pipeline/manual and hot-date opportunities/derived.

### Jack/main: `kilmurry.dashboard.owner_ops.v1`

Jack/main is the control layer.

```jsonc
{
  "schema": "kilmurry.dashboard.owner_ops.v1",
  "generated_at_utc": "...",
  "data_health": {
    "rezlynx_soap": "LIVE|STALE|BLOCKED",
    "report_data_rest": "LIVE|PENDING|BLOCKED",
    "hot_dates": "LIVE|STALE|BLOCKED",
    "competitor_rates": "LIVE|STALE|BLOCKED",
    "kate_marketing_sources": "LIVE|DEMO|PENDING",
    "ciara_sales_sources": "LIVE|MANUAL|PENDING_CRM"
  },
  "services": [ { "name": "faye-mc", "port": 3338, "status": "active|down", "last_check_utc": "..." } ],
  "alerts": [ { "severity": "critical|warning|info", "message": "...", "owner": "..." } ],
  "recent_refreshes": [ { "dashboard": "faye|kate|ciara|jack", "result": "ok|warning|failed", "changed_panels": [] } ]
}
```

## Refresh output files to create

KilmurryBot should write these server-side files on every six-hour cycle:

```text
/home/clawuser/shared/dashboard-refresh/
  dashboard-refresh-latest.json
  dashboard-refresh-YYYY-MM-DDTHHMMSSZ.json
  dashboard-refresh-manifest-YYYY-MM-DDTHHMMSSZ.json
  faye-dashboard-latest.json
  kate-dashboard-latest.json
  ciara-dashboard-latest.json
  owner-ops-dashboard-latest.json
```

Every file must include:

- `schema`
- `generated_at_utc`
- `source_state` or `freshness`
- `provenance.input_files`
- `provenance.validation_warnings`

## Smoke checks after each refresh

Run:

```bash
curl -fsS http://127.0.0.1:3338/api/status
curl -fsS http://127.0.0.1:3336/api/status
curl -fsS http://127.0.0.1:3340/api/status
curl -fsS http://127.0.0.1:3333/api/status
curl -fsS http://127.0.0.1:3338/ | grep -q "Faye Revenue Intelligence Dashboard"
curl -fsS http://127.0.0.1:3336/ | grep -q "Live vs dummy data map"
curl -fsS http://127.0.0.1:3340/ | grep -q "Ciara Mission Control"
curl -fsS http://127.0.0.1:3333/ | grep -q "Kilmurry dashboard data health"
```

If any check fails, mark that dashboard refresh `failed`, keep previous-good data in place, and alert Jack/Jonny.

## Current blockers KilmurryBot should surface

1. Report Data REST credentials/endpoints are still needed for authoritative revenue, ADR, RevPAR, channel revenue and segment revenue.
2. CRM/pipeline source for Ciara is not wired; current sales queue is manual/derived.
3. Kate reputation/social/SEO APIs are not all live; homepage must keep demo/manual labels until wired.
4. Ciara GitHub remote is wrong/inaccessible: `Jonnyhimalaya/kilmurry-ciara-mission-control` returns repository-not-found.
5. Do not ingest raw guest PII into dashboard snapshots. Aggregate only.
