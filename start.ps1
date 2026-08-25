$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "Creating virtualenv..."
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
$req = if (Test-Path ".\requirements-core.txt") { ".\requirements-core.txt" } else { ".\requirements.txt" }
& .\.venv\Scripts\python.exe -m pip install -r $req

if (-not (Test-Path ".\.env")) {
  Copy-Item ".\.env.example" ".\.env"
  Write-Host "Created .env - add XAI_API_KEY and GITHUB_TOKEN, or paste them in the HUD."
}

# An instance already on 8787 means the new process binds nothing, exits, and the
# HUD keeps serving the OLD code -- so a pull looks applied but nothing changes.
# Uvicorn's WinError 10048 does not say that, so say it here.
$busy = $null
try {
  $busy = Get-NetTCPConnection -LocalPort 8787 -State Listen -ErrorAction SilentlyContinue
} catch {
  $busy = $null
}
if ($busy) {
  $owner = $busy | Select-Object -First 1 -ExpandProperty OwningProcess
  $proc = Get-Process -Id $owner -ErrorAction SilentlyContinue
  $label = if ($proc) { "$($proc.ProcessName) (PID $owner)" } else { "PID $owner" }
  Write-Host ""
  Write-Host "Port 8787 is already in use by $label." -ForegroundColor Yellow
  Write-Host "That is an older Super Jarvis still running. If it keeps serving, the HUD" -ForegroundColor Yellow
  Write-Host "shows the OLD code and any git pull looks like it did nothing." -ForegroundColor Yellow
  Write-Host ""
  $answer = Read-Host "Stop it and start the updated build? [Y/n]"
  if ($answer -eq "" -or $answer -match "^[Yy]") {
    Stop-Process -Id $owner -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    Write-Host "Stopped $label." -ForegroundColor Green
  } else {
    Write-Host "Leaving it running. The updated code will NOT load." -ForegroundColor Red
    exit 1
  }
}

Write-Host "Starting Super Jarvis (rkenagy-ops/jarvis-system) on http://127.0.0.1:8787"
$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if (-not $ollama) {
  $cand = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "C:\Program Files\Ollama\ollama.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($cand) { $env:Path = (Split-Path $cand) + ";" + $env:Path }
}
if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Write-Host "Ollama on PATH - local brain available if a model is pulled (ollama pull llama3.2)"
} else {
  Write-Host "Ollama not installed. HUD still runs on Grok. Install: winget install Ollama.Ollama"
}
& .\.venv\Scripts\python.exe -m app
