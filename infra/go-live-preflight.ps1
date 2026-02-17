$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

function Invoke-Step {
  param (
    [string]$Name,
    [scriptblock]$Command
  )

  Write-Host "START: $Name" -ForegroundColor Cyan
  & $Command
  if ($LASTEXITCODE -ne 0) {
    throw "$Name failed with exit code $LASTEXITCODE"
  }
  Write-Host "END: $Name" -ForegroundColor Green
}

try {
  $root = Split-Path -Parent $PSScriptRoot
  Write-Host "== LSOS Go-Live Preflight ==" -ForegroundColor Cyan

  Push-Location "$root\backend"
  try {

    Invoke-Step "Backend Dependency Install" {
      if (-not (Test-Path ".\.venv312\Scripts\python.exe")) {
        py -3.12 -m venv .venv312
      }

      .\.venv312\Scripts\python.exe -m pip install --disable-pip-version-check --no-input --cache-dir .\.pip-cache -r requirements.txt
      .\.venv312\Scripts\python.exe -m pip install --disable-pip-version-check --no-input pip-audit
    }

    Invoke-Step "Backend Tests" {
      .\.venv312\Scripts\python.exe -m pytest -vv -s
    }

    Invoke-Step "Backend Vulnerability Scan" {
      .\.venv312\Scripts\python.exe -m pip_audit --timeout 20
    }

  } finally {
    Pop-Location
  }

  Push-Location "$root\frontend"
  try {

    $env:CI="true"

    Invoke-Step "Frontend Install" {
      npm ci --no-audit --no-fund --prefer-offline
    }

    $env:NODE_OPTIONS="--max_old_space_size=4096"

    Invoke-Step "Frontend Build" {
      npm run build -- --no-lint
    }

    Invoke-Step "Frontend Audit" {
      npm audit --audit-level=high --omit=dev
    }

  } finally {
    Pop-Location
  }

  Write-Host "Preflight completed successfully."
  exit 0

} catch {
  Write-Host "Preflight FAILED: $($_.Exception.Message)" -ForegroundColor Red
  exit 1
}