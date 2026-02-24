$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $repoRoot

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Command,
        [string[]]$Arguments = @()
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed ($LASTEXITCODE): $Command $($Arguments -join ' ')"
    }
}

if (Test-Path ".venv") {
    Remove-Item -Recurse -Force ".venv"
}

$pythonCommand = $null
try {
    py -3.12 --version *> $null
    $pythonCommand = @("py", "-3.12")
} catch {
    try {
        py -3.11 --version *> $null
        $pythonCommand = @("py", "-3.11")
    } catch {
        throw "Python 3.11 or 3.12 is required."
    }
}

Invoke-Checked -Command $pythonCommand[0] -Arguments @($pythonCommand[1], "-m", "venv", ".venv")
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked -Command $venvPython -Arguments @("-m", "pip", "install", "-r", "backend/requirements-dev.txt")

Invoke-Checked -Command $venvPython -Arguments @("-m", "ruff", "check", "backend")
Invoke-Checked -Command $venvPython -Arguments @("-m", "pytest", "-q")
Invoke-Checked -Command $venvPython -Arguments @("backend/scripts/validate_production_config.py")

Write-Host "bootstrap_dev_env completed."
