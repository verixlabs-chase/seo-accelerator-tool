$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $repoRoot "backend\.venv312\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend environment is missing. Run .\scripts\windows\Initialize-Development.ps1 first."
}

& $pythonPath (Join-Path $repoRoot "backend\scripts\backfill_campaign_daily_metrics.py") @args
exit $LASTEXITCODE
