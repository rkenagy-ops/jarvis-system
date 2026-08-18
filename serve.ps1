# Lean Daily Driver start. No pip. Loopback only.
$ErrorActionPreference = "SilentlyContinue"
Set-Location $PSScriptRoot
$env:Path = "$env:LOCALAPPDATA\Programs\Ollama;C:\Program Files\Ollama;C:\Program Files\Git\cmd;" + $env:Path

function Test-Port([int]$Port) {
  try {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop
    return [bool]$c
  } catch {
    return $false
  }
}

if (-not (Test-Port 11434)) {
  $ollama = @(
    "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe",
    "C:\Program Files\Ollama\ollama.exe"
  ) | Where-Object { Test-Path $_ } | Select-Object -First 1
  if ($ollama) {
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
  }
}

if (-not (Test-Port 8787)) {
  $py = Join-Path $PSScriptRoot ".venv\Scripts\pythonw.exe"
  if (-not (Test-Path $py)) { $py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe" }
  Start-Process -FilePath $py -ArgumentList "-m","app" -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
}
