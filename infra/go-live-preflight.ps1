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
    $runningOnWindows = $env:OS -eq "Windows_NT"

    $backendDir = Join-Path $root "backend"
    $frontendDir = Join-Path $root "frontend"

    if ($runningOnWindows) {
        $pythonPath = Join-Path $backendDir ".venv312\Scripts\python.exe"
    } else {
        $pythonPath = Join-Path $backendDir ".venv312/bin/python"
    }

    Write-Host "== LSOS Go-Live Preflight ==" -ForegroundColor Cyan

    # ========================
    # BACKEND
    # ========================

    Push-Location $backendDir
    try {

        Invoke-Step "Backend Dependency Install" {

            if (-not (Test-Path $pythonPath)) {
                if ($runningOnWindows) {
                    py -3.12 -m venv .venv312
                } else {
                    python3 -m venv .venv312
                }
            }

            $cacheDir = Join-Path $PWD ".pip-cache"

            # 🔥 Fix CI pip vulnerability failure
            & $pythonPath -m pip install --upgrade "pip>=25.3"

            # Install project dependencies
            & $pythonPath -m pip install --disable-pip-version-check --no-input --cache-dir $cacheDir -r requirements.txt

            # Install pip-audit
            & $pythonPath -m pip install --disable-pip-version-check --no-input pip-audit
        }

        Invoke-Step "Backend Tests" {
            & $pythonPath -m pytest -vv -s
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
                & $pythonPath -m pip_audit --timeout 20
            }
            finally {
                foreach ($name in $proxyVars) {
                    if ($originalProxyValues.ContainsKey($name)) {
                        [Environment]::SetEnvironmentVariable($name, $originalProxyValues[$name], "Process")
                    }
                    else {
                        [Environment]::SetEnvironmentVariable($name, $null, "Process")
                    }
                }
            }
        }

    }
    finally {
        Pop-Location
    }

    # ========================
    # FRONTEND
    # ========================

    Push-Location $frontendDir
    try {

        $env:CI = "true"
        $env:NPM_CONFIG_CACHE = Join-Path $frontendDir ".npm-cache"
        $env:NODE_OPTIONS = "--max_old_space_size=4096"

        Invoke-Step "Frontend Install" {
            $nodeModulesPath = Join-Path $PWD "node_modules"

            if (Test-Path $nodeModulesPath) {
                Write-Host "node_modules already present; skipping reinstall." -ForegroundColor DarkYellow
            }
            else {
                npm ci --no-audit --no-fund --prefer-offline --ignore-scripts
            }
        }

        Invoke-Step "Frontend Build" {

            if (-not $runningOnWindows) {
                npm run build -- --no-lint
                return
            }

            $process = Start-Process "cmd.exe" `
                -ArgumentList "/c", "npm run build" `
                -NoNewWindow `
                -Wait `
                -PassThru

            if ($process.ExitCode -ne 0) {
                $global:LASTEXITCODE = $process.ExitCode
            }
        }

        Invoke-Step "Frontend Audit" {
            npm audit --audit-level=high --omit=dev
        }

    }
    finally {
        Pop-Location
    }

    Write-Host "Preflight completed successfully." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "Preflight FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
