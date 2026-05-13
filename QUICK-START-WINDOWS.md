# Kilmurry RezLynx Gateway — Windows Quick Start

This is a one-page guide for Jack's Cowork PC. Full doc is in `docs/handoff-to-desktop.md`.

## Prerequisites (5 mins)

1. **Python 3.11+** — https://www.python.org/downloads/windows/  
   Tick "Add python.exe to PATH" during install.
2. **Git for Windows** — https://git-scm.com/download/win
3. **OneDrive** signed in and syncing the "Kilmurry Shared AI" folder.

## Install (1 command)

Open **PowerShell as Administrator**, then:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
iwr -useb https://raw.githubusercontent.com/Jonnyhimalaya/kilmurry-rezlynx-gateway/main/install-windows.ps1 -OutFile $env:TEMP\install-gateway.ps1
& $env:TEMP\install-gateway.ps1
```

The script will:

1. Verify Python + git
2. Clone repo into `C:\Tools\kilmurry-gateway`
3. Create a Python virtual env
4. Write `config\settings.toml` pointed at your OneDrive folder
5. **Pause and ask you to create `config\secrets.toml`** with the SOAP password
6. Run `gateway doctor`, `gateway soap-probe`, `gateway run`
7. Verify the JSON file appeared in OneDrive
8. Register a Windows Task Scheduler job to run 4x daily

If the OneDrive path on your machine is different from `C:\Users\Claude\OneDrive - kilmurrylodge.com\kilmurry shared AI\Right Revenue Gateway`, **edit the `$OneDriveRoot` line at the top of the script before running**.

## Secrets file format

When the script pauses, create `C:\Tools\kilmurry-gateway\config\secrets.toml`:

```toml
[rezlynx]
password = "<paste SOAP password here>"
api_key = ""
```

Then press ENTER in the PowerShell window.

## Manual re-run

To run the gateway manually any time:

```powershell
cd C:\Tools\kilmurry-gateway
.\.venv\Scripts\gateway.exe run
```

## Check status

```powershell
cd C:\Tools\kilmurry-gateway
.\.venv\Scripts\gateway.exe doctor       # config + paths
Get-ChildItem "C:\Users\Claude\OneDrive - kilmurrylodge.com\kilmurry shared AI\Right Revenue Gateway\feeds" | Sort LastWriteTime -Descending | Select -First 3
```

## If something goes wrong

- Read `C:\Tools\kilmurry-gateway\logs\gateway.jsonl` (last 50 lines)
- Check Task Scheduler → "Kilmurry-RezLynx-Gateway" → History tab
- Re-run `gateway run` interactively to see the error
