$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$pythonPath = Join-Path $backendDir ".venv312\Scripts\python.exe"
$envPath = Join-Path $backendDir ".env"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend environment is missing. Run .\scripts\windows\Initialize-Development.ps1 first."
}
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "backend\.env is missing. Run .\scripts\windows\Initialize-Development.ps1 first."
}

Push-Location $backendDir
try {
    $env:PYTHONUTF8 = "1"
    & $pythonPath -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
}
finally {
    Pop-Location
}
