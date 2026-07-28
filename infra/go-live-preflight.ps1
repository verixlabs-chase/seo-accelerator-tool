param(
    [switch]$SkipDependencyInstall,
    [switch]$SkipSecurityAudit
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
Set-StrictMode -Version Latest

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command
    )

    Write-Host "START: $Name" -ForegroundColor Cyan
    $global:LASTEXITCODE = 0
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
    Write-Host "END: $Name" -ForegroundColor Green
}

function Assert-Command {
    param([Parameter(Mandatory = $true)][string]$Name)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

try {
    $runningOnWindows = $env:OS -eq "Windows_NT"
    if (-not $runningOnWindows) {
        throw "This project uses the Windows-native preflight. Run it from Windows PowerShell 5.1 or PowerShell 7."
    }

    Assert-Command "python"
    Assert-Command "npm"

    $root = Split-Path -Parent $PSScriptRoot
    $backendDir = Join-Path $root "backend"
    $frontendDir = Join-Path $root "frontend"
    $pythonPath = Join-Path $backendDir ".venv312\Scripts\python.exe"

    Write-Host "== SEO Accelerator Windows Go-Live Preflight ==" -ForegroundColor Cyan

    Push-Location $backendDir
    try {
        if (-not $SkipDependencyInstall) {
            Invoke-Step "Backend dependency install" {
                if (-not (Test-Path -LiteralPath $pythonPath)) {
                    python -m venv .venv312
                }
                & $pythonPath -m pip install --upgrade "pip>=25.3"
                & $pythonPath -m pip install --disable-pip-version-check --no-input -r requirements-dev.txt
                if (-not $SkipSecurityAudit) {
                    & $pythonPath -m pip install --disable-pip-version-check --no-input pip-audit
                }
            }
        }
        elseif (-not (Test-Path -LiteralPath $pythonPath)) {
            throw "Backend virtual environment is missing. Run without -SkipDependencyInstall first."
        }

        Invoke-Step "Backend migration validation" {
            & $pythonPath scripts\validate_migrations.py
        }

        Invoke-Step "Backend tests" {
            $env:PYTHONUTF8 = "1"
            & $pythonPath -m pytest -q
        }

        Invoke-Step "Backend lint" {
            & $pythonPath -m ruff check .
        }

        if (-not $SkipSecurityAudit) {
            Invoke-Step "Backend vulnerability scan" {
                & $pythonPath -m pip_audit --timeout 20
            }
        }
    }
    finally {
        Pop-Location
    }

    Push-Location $frontendDir
    try {
        $env:CI = "true"
        $env:NPM_CONFIG_CACHE = Join-Path $frontendDir ".npm-cache"
        $env:NODE_OPTIONS = "--max_old_space_size=4096"

        if (-not $SkipDependencyInstall) {
            Invoke-Step "Frontend dependency install" {
                npm ci --no-audit --no-fund
            }
        }

        Invoke-Step "Frontend tests" {
            npm test
        }

        Invoke-Step "Frontend lint" {
            npm run lint
        }

        Invoke-Step "Frontend build" {
            npm run build
        }

        if (-not $SkipSecurityAudit) {
            Invoke-Step "Frontend vulnerability scan" {
                npm audit --audit-level=high
            }
        }
    }
    finally {
        Pop-Location
    }

    Write-Host "Windows preflight completed successfully." -ForegroundColor Green
    exit 0
}
catch {
    Write-Host "Windows preflight FAILED: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
