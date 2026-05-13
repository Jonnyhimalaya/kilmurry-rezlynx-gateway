# Kilmurry RezLynx Gateway — Windows install + setup
# Run from elevated PowerShell on Jack's Cowork PC
# Usage:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; .\install-windows.ps1

$ErrorActionPreference = 'Stop'

# --- Config you may want to tweak ---
$InstallDir   = "C:\Tools\kilmurry-gateway"
$RepoUrl      = "https://github.com/Jonnyhimalaya/kilmurry-rezlynx-gateway.git"
$OneDriveRoot = "C:\Users\Claude\OneDrive - kilmurrylodge.com\kilmurry shared AI\Right Revenue Gateway"
# ------------------------------------

function Step($msg) { Write-Host "`n>>> $msg" -ForegroundColor Cyan }

Step "1. Finding Python 3.11+"
$PyExe = $null
$candidates = @(
    "C:\Program Files\Python311\python.exe",
    "C:\Program Files (x86)\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
)
foreach ($c in $candidates) {
    if (Test-Path $c) { $PyExe = $c; break }
}
if (-not $PyExe) {
    try {
        $cmd = Get-Command python -ErrorAction Stop
        $ver = & $cmd.Source --version 2>&1
        if ($ver -match "Python 3\.(11|12|13)") { $PyExe = $cmd.Source }
    } catch {}
}
if (-not $PyExe) {
    try {
        $cmd = Get-Command py -ErrorAction Stop
        $PyExe = $cmd.Source
    } catch {}
}
if (-not $PyExe) {
    throw "Python 3.11+ not found. Install from python.org and re-run."
}
$verOut = & $PyExe --version
Write-Host "  Found: $verOut at $PyExe"

Step "2. Checking git"
$gitOk = $false
try {
    git --version | Out-Null
    if ($LASTEXITCODE -eq 0) { $gitOk = $true }
} catch {}
if (-not $gitOk) { throw "git not installed. Install Git for Windows first: https://git-scm.com/download/win" }

Step "3. Clone or update repo into $InstallDir"
if (Test-Path "$InstallDir\.git") {
    Write-Host "  Repo already exists, pulling latest"
    Push-Location $InstallDir
    git fetch --all
    git reset --hard origin/main
    Pop-Location
} else {
    if (Test-Path $InstallDir) { Remove-Item -Recurse -Force $InstallDir }
    New-Item -ItemType Directory -Path (Split-Path $InstallDir) -Force | Out-Null
    git clone $RepoUrl $InstallDir
}

Step "4. Create Python venv"
Push-Location $InstallDir
if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
    & $PyExe -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip wheel setuptools | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e . 2>&1 | Select-Object -Last 6
Pop-Location

Step "5. Configure settings.toml for live SOAP"
$settingsPath = "$InstallDir\config\settings.toml"
$oneDriveEscaped = $OneDriveRoot -replace '\\','/'
$settings = @"
# Live config for Jack's Cowork PC.
[gateway]
site_label = "Kilmurry Lodge"
site_id = "KILMURRY"
poll_interval_hours = 6
timezone = "UTC"
adapter_mode = "live"
log_dir = "./logs"
log_level = "INFO"

[rezlynx]
base_url = ""
site_id = "KILMURRY"
auth_mode = "soap"
timeout_seconds = 60
verify_ssl = true
live_sources = ["soap"]

[publish]
onedrive_root = "$oneDriveEscaped"
feeds_dir = "feeds"
summaries_dir = "summaries"
manifests_dir = "manifests"
write_latest_pointer = true
"@
$settings | Out-File -Encoding utf8 $settingsPath

Step "6. Check secrets.toml"
$secretsPath = "$InstallDir\config\secrets.toml"
if (-not (Test-Path $secretsPath)) {
    Write-Host "  secrets.toml NOT FOUND." -ForegroundColor Yellow
    Write-Host "  Open Notepad now and create this file with the SOAP password:"
    Write-Host "    $secretsPath"
    Write-Host ""
    Write-Host "  File contents should be:"
    Write-Host '    [rezlynx]'
    Write-Host '    password = "<PASTE THE SOAP PASSWORD>"'
    Write-Host '    api_key = ""'
    Read-Host "  Press ENTER once secrets.toml exists"
}
if (-not (Test-Path $secretsPath)) { throw "secrets.toml still missing." }

Step "7. Ensure OneDrive folder exists"
if (-not (Test-Path $OneDriveRoot)) {
    New-Item -ItemType Directory -Path $OneDriveRoot -Force | Out-Null
    Write-Host "  Created $OneDriveRoot"
}

Step "8. Smoke test: gateway doctor"
Push-Location $InstallDir
& .\.venv\Scripts\gateway.exe doctor
Pop-Location

Step "9. Live SOAP probe (proves credentials work end-to-end)"
Push-Location $InstallDir
& .\.venv\Scripts\gateway.exe soap-probe
Pop-Location

Step "10. First live publish run (writes to OneDrive)"
Push-Location $InstallDir
& .\.venv\Scripts\gateway.exe run
Pop-Location

Step "11. Verify file landed in OneDrive"
$latest = Join-Path $OneDriveRoot "feeds\rezlynx-revenue-feed-latest.json"
if (Test-Path $latest) {
    $stamp = (Get-Item $latest).LastWriteTimeUtc.ToString("o")
    Write-Host "  SUCCESS - $latest" -ForegroundColor Green
    Write-Host "  Last write UTC: $stamp" -ForegroundColor Green
} else {
    throw "Gateway ran but output file not found at $latest"
}

Step "12. Register Task Scheduler job (4x daily)"
$taskName = "Kilmurry-RezLynx-Gateway"
$action = New-ScheduledTaskAction `
    -Execute "$InstallDir\.venv\Scripts\gateway.exe" `
    -Argument "run" `
    -WorkingDirectory $InstallDir
$triggers = @(
    New-ScheduledTaskTrigger -Daily -At 00:05
    New-ScheduledTaskTrigger -Daily -At 06:05
    New-ScheduledTaskTrigger -Daily -At 12:05
    New-ScheduledTaskTrigger -Daily -At 18:05
)
$settingsScheduler = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -WakeToRun
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Limited

if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $triggers `
    -Settings $settingsScheduler `
    -Principal $principal `
    -Description "Kilmurry Lodge RezLynx SOAP -> OneDrive 4x daily"

Write-Host "`nALL DONE." -ForegroundColor Green
Write-Host "Task '$taskName' will run at 00:05, 06:05, 12:05, 18:05 daily."
Write-Host "Check the task in Task Scheduler under Task Scheduler Library."
