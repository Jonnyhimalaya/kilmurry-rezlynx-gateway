# Handoff to Jack's Cowork PC

This document covers porting the gateway from Stephen's dev server to
the desktop / Cowork PC.

## Prerequisites on the PC

1. **Python 3.11+** — install from python.org (or use the existing
   Claude Cowork Python if it's 3.11+).
2. **OneDrive** — already installed and signed in. Confirm the local
   sync folder is reachable in Explorer.
3. **Network egress** to `*.guestline.com` / `*.guestline.io` on 443.
4. **Local admin** to register a Task Scheduler job (or use a per-user task).

## Copy the project

The gateway has no native binaries. Just copy the folder.

Recommended target: `C:\Tools\kilmurry-gateway\`

Easiest options:
- USB / direct copy
- ZIP from this repo and extract on the PC
- Clone from the repo when we add it

After copy, **do not** copy `.venv/` from a Linux machine. Recreate it
on Windows:

```powershell
cd C:\Tools\kilmurry-gateway\
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e .
```

## Configure for the PC

Edit `config\settings.toml`:

```toml
[gateway]
mock_mode = true            # keep true until live adapter is wired

[publish]
# Replace with the real OneDrive-synced local path
onedrive_root = "C:/Users/jack/OneDrive - Kilmurry/Kilmurry Shared AI/Right Revenue Gateway"
```

Forward-slashes work in TOML on Windows. Keep them — easier to read.

If/when credentials are issued, also create `config\secrets.toml` (NOT
committed) with the real client_secret. See `secrets.toml.example`.

## Smoke test on the PC

```powershell
.\.venv\Scripts\gateway.exe doctor       # prints resolved config
.\.venv\Scripts\gateway.exe sample       # writes to .\samples\
.\.venv\Scripts\gateway.exe run --dry-run
.\.venv\Scripts\gateway.exe run          # writes to OneDrive folder
```

Confirm the OneDrive client picks up the new files (icon goes from
"local-only" to "cloud-synced").

## Schedule it (Task Scheduler)

Open Task Scheduler → Create Task → set up four triggers at 00:00,
06:00, 12:00, 18:00. Action:

- Program: `C:\Tools\kilmurry-gateway\.venv\Scripts\gateway.exe`
- Arguments: `run`
- Start in: `C:\Tools\kilmurry-gateway\`

Settings:
- Run whether user is logged on or not
- Run with highest privileges = NO (not needed)
- If the task fails, restart every 10 minutes, up to 3 times

The four-trigger pattern is more reliable than a single "every 6 hours"
trigger because it avoids drift if the PC has been asleep.

## Alternative: `gateway watch`

If Jack prefers a single always-on process instead of Task Scheduler,
run `gateway watch` from a shortcut at startup (Task Scheduler "At
log on" works for this too). It loops and sleeps internally.

Downside: a crash leaves nothing running until next login.

## Where to put logs

Logs live next to the code (`C:\Tools\kilmurry-gateway\logs\gateway.jsonl`).
They rotate at 2 MB / 5 backups.

**Do not** put logs inside the OneDrive folder. Logs may contain
endpoint strings and we want them local-only.

## When credentials arrive

1. Edit `config\settings.toml`:
   - `mock_mode = false`
   - `rezlynx.auth_mode = "oauth2"` (or whatever Guestline gives us)
   - `rezlynx.base_url = "https://api.guestline.io/..."` (confirmed)
   - `rezlynx.client_id = "<provided>"`
2. Edit `config\secrets.toml`:
   - `client_secret = "<provided>"`
3. Run once manually: `gateway run --dry-run` then `gateway run`.
4. Check OneDrive for the new file.
5. Check `logs\gateway.jsonl` for confirmation.

## What we share back with OpenClaw

OpenClaw's consumer needs only the OneDrive path. Jack should make
sure the same Shared AI folder is accessible by both:
- Jack's Cowork PC (write side)
- The OpenClaw server (read side, via the existing Microsoft account
  that the OpenClaw OneDrive sync uses)

Per the agreed boundary: OpenClaw never gets PMS credentials.

## Rollback

If a gateway run breaks something visible to the dashboard:

1. Inspect `logs\gateway.jsonl` for the failing run id.
2. If a bad feed file got written: copy the previous `feeds/rezlynx-revenue-feed-{date}-{ts}.json`
   over the `*-latest.json` pointer and overwrite the broken summary similarly.
3. The OpenClaw consumer will pick up the restored latest on its next poll.

Feeds are immutable per-timestamp, so rollback is always "promote an
older valid file to latest". No data loss is possible from the
consumer's perspective.
