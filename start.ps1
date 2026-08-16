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
  Write-Host "Created .env — add XAI_API_KEY and GITHUB_TOKEN, or paste them in the HUD."
}

Write-Host "Starting Super Jarvis (rkenagy-ops/jarvis-system) on http://127.0.0.1:8787"
& .\.venv\Scripts\python.exe -m app
