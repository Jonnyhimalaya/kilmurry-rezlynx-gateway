# How to Run & Test

## Linux / macOS (dev)

```bash
cd gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp config/settings.toml.example config/settings.toml
# (optional, only when wiring real Guestline:)
cp config/secrets.toml.example config/secrets.toml

# Smoke
pytest

# End-to-end with mock data, into a sample folder
gateway sample
# -> writes ./samples/{feeds,summaries,manifests}/...

# Resolved config (no secrets)
gateway doctor

# Run once, write to configured onedrive_root
gateway run

# Run dry (no files written)
gateway run --dry-run

# Validate an existing feed
gateway validate samples/feeds/rezlynx-revenue-feed-latest.json

# Backfill 7 days
gateway backfill --from 2026-05-01 --to 2026-05-07

# Daemon mode (loops every poll_interval_hours)
gateway watch

# Run-once mode (for Task Scheduler / cron)
gateway watch --once
```

## Windows (Jack's Cowork PC)

> Same Python package, different scheduling. See also `handoff-to-desktop.md`.

```powershell
# 1. Install Python 3.11+ from python.org if not already present
# 2. Copy this folder to e.g. C:\Tools\kilmurry-gateway\
cd C:\Tools\kilmurry-gateway\

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .

Copy-Item config\settings.toml.example config\settings.toml
# Edit settings.toml: set publish.onedrive_root to your OneDrive-synced path
# e.g. "C:/Users/jack/OneDrive - Kilmurry/Kilmurry Shared AI/Right Revenue Gateway"

# Smoke
.\.venv\Scripts\gateway.exe sample

# Wire scheduler — see handoff-to-desktop.md for the .xml task definition
```

## Switching from mock to live

When Stephen has Guestline credentials + endpoint:

1. Edit `src/kilmurry_gateway/adapters/guestline_rest.py` — fill in the TODOs.
2. Edit `src/kilmurry_gateway/pipeline.py::select_adapter` — uncomment the
   `GuestlineRestAdapter` branch.
3. Set `mock_mode = false` in `config/settings.toml`.
4. Set `rezlynx.auth_mode = "oauth2"` (or whatever is correct).
5. Set `rezlynx.base_url` and `rezlynx.client_id` in settings.toml.
6. Set `client_secret` in `config/secrets.toml` (gitignored).
7. `gateway run --dry-run` to confirm fetch succeeds, then `gateway run`.

## Where do outputs go?

| What | Path (relative to `onedrive_root`) |
|---|---|
| Timestamped feeds | `feeds/rezlynx-revenue-feed-{date}-{ts}.json` |
| Latest feed pointer | `feeds/rezlynx-revenue-feed-latest.json` |
| Timestamped HTML | `summaries/rezlynx-summary-{date}-{ts}.html` |
| Latest HTML | `summaries/rezlynx-summary-latest.html` |
| Run manifest | `manifests/rezlynx-manifest-{date}-{ts}.json` |
| Gateway logs | `logs/gateway.jsonl` (NOT in OneDrive — local to desktop) |

## Logs

Each run writes structured JSONL to `./logs/gateway.jsonl`. Tail it:

```bash
tail -f logs/gateway.jsonl | jq .
```
