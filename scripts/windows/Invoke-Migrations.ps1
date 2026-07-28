param(
    [string]$EnvironmentFile
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $backendDir ".venv312\Scripts\python.exe"

if (-not $EnvironmentFile) {
    $EnvironmentFile = Join-Path $backendDir ".env"
}

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend environment is missing. Run .\scripts\windows\Initialize-Development.ps1 first."
}

if (-not $env:DATABASE_URL) {
    if (-not (Test-Path -LiteralPath $EnvironmentFile)) {
        throw "DATABASE_URL is not set and environment file was not found: $EnvironmentFile"
    }
    $databaseLine = Get-Content -LiteralPath $EnvironmentFile |
        Where-Object { $_ -match '^\s*DATABASE_URL=' } |
        Select-Object -First 1
    if (-not $databaseLine) {
        throw "DATABASE_URL was not found in $EnvironmentFile"
    }
    $env:DATABASE_URL = ($databaseLine -split '=', 2)[1].Trim().Trim('"').Trim("'")
}

if ($env:DATABASE_URL -match '\[URL-ENCODED-PASSWORD\]') {
    throw "Replace [URL-ENCODED-PASSWORD] in backend\.env before running migrations."
}

Push-Location $backendDir
try {
    & $pythonPath -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic migration failed with exit code $LASTEXITCODE."
    }
    & $pythonPath -m alembic current
}
finally {
    Pop-Location
}
