$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$frontendDir = Join-Path $repoRoot "frontend"

if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    throw "Frontend dependencies are missing. Run .\scripts\windows\Initialize-Development.ps1 first."
}

Push-Location $frontendDir
try {
    npm run dev
}
finally {
    Pop-Location
}
