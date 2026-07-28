$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$initializer = Join-Path $repoRoot "scripts\windows\Initialize-Development.ps1"
& $initializer -Force @args
exit $LASTEXITCODE
