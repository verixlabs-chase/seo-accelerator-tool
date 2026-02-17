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
      $proxyVars = @("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")
      $originalProxyValues = @{}

      foreach ($name in $proxyVars) {
        $existing = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($null -ne $existing) {
          $originalProxyValues[$name] = $existing
        }
        [Environment]::SetEnvironmentVariable($name, $null, "Process")
      }

      try {
        .\.venv312\Scripts\python.exe -m pip_audit --timeout 20
      } finally {
        foreach ($name in $proxyVars) {
          if ($originalProxyValues.ContainsKey($name)) {
            [Environment]::SetEnvironmentVariable($name, $originalProxyValues[$name], "Process")
          } else {
            [Environment]::SetEnvironmentVariable($name, $null, "Process")
          }
        }
      }
    }

  } finally {
    Pop-Location
  }

  Push-Location "$root\frontend"
  try {

    $isWindows = $env:OS -eq "Windows_NT"
    $env:CI="true"
    $env:NPM_CONFIG_CACHE = "$root\frontend\.npm-cache"

    Invoke-Step "Frontend Install" {
      if (Test-Path ".\node_modules") {
        Write-Host "node_modules already present; skipping reinstall to avoid Windows EPERM postinstall lock." -ForegroundColor DarkYellow
      } else {
        npm ci --no-audit --no-fund --prefer-offline --ignore-scripts
      }
    }

    $env:NODE_OPTIONS="--max_old_space_size=4096"

    Invoke-Step "Frontend Build" {
      if (-not $isWindows) {
        npm run build -- --no-lint
        return
      }

      $buildCommand = "npm run build"
      $process = Start-Process "cmd.exe" `
        -ArgumentList "/c", $buildCommand `
        -NoNewWindow `
        -Wait `
        -PassThru

      $finalExitCode = $process.ExitCode
      if ($finalExitCode -ne 0) {
        $global:LASTEXITCODE = $finalExitCode
      }
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
