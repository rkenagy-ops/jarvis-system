$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$env:Path = "C:\Program Files\Git\cmd;C:\Program Files\GitHub CLI;" + $env:Path

Write-Host "=== Super Jarvis setup ==="

if (-not (Test-Path ".\.venv\Scripts\python.exe")) {
  Write-Host "Creating project venv..."
  python -m venv .venv
}

& .\.venv\Scripts\python.exe -m pip install --upgrade pip
& .\.venv\Scripts\python.exe -m pip install -r requirements-core.txt

if (-not (Test-Path ".\.env")) {
  Copy-Item ".\.env.example" ".\.env"
}

$gh = Get-Command gh -ErrorAction SilentlyContinue
if ($gh) {
  try {
    $token = (& gh auth token 2>$null)
    if ($token) {
      $env:GH_TOKEN = $token
      & .\.venv\Scripts\python.exe -c @"
from app import config
import os
updates = {}
tok = os.environ.get('GH_TOKEN','').strip()
if tok:
    updates['GITHUB_TOKEN'] = tok
    updates['GITHUB_USERNAME'] = 'rkenagy-ops'
if updates:
    config.save_env(updates)
    print('github-token-saved')
"@
    }
  } catch {
    Write-Host "gh token not copied (login later with gh auth login)"
  }
}

New-Item -ItemType Directory -Force -Path ".\workspace\inbox", ".\workspace\images", ".\data" | Out-Null

& .\.venv\Scripts\python.exe -c @"
from app import memory, markets, obsidian, rag
memory.init()
markets.init()
print('vault', obsidian.init_vault())
print('rag', rag.reindex_vault())
print('setup-ok')
"@

Write-Host ""
Write-Host "Open HUD:  http://127.0.0.1:8787"
Write-Host "Open vault in Obsidian: File -> Open folder as vault -> $PSScriptRoot\vault"
Write-Host "Then: .\start.ps1"
