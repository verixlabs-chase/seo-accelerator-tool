param(
    [switch]$Force,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if ($env:OS -ne "Windows_NT") {
    throw "This setup script is for Windows."
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"
$venvDir = Join-Path $backendDir ".venv312"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
    throw "Python Launcher for Windows is required. Install Python 3.12 from python.org and enable the py launcher."
}

py -3.12 --version
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 is required."
}

if (-not $SkipFrontend) {
    if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "Node.js 22 and npm are required."
    }
    node --version
    npm --version
}

if ($Force -and (Test-Path -LiteralPath $venvDir)) {
    $resolvedVenv = (Resolve-Path -LiteralPath $venvDir).Path
    if (-not $resolvedVenv.StartsWith($backendDir, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove a virtual environment outside backend."
    }
    Remove-Item -LiteralPath $resolvedVenv -Recurse -Force
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    py -3.12 -m venv $venvDir
}

& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install -r (Join-Path $backendDir "requirements-dev.txt")

$backendEnv = Join-Path $backendDir ".env"
if (-not (Test-Path -LiteralPath $backendEnv)) {
    Copy-Item -LiteralPath (Join-Path $backendDir ".env.windows.example") -Destination $backendEnv
    Write-Host "Created backend\.env. Add the URL-encoded Supabase password before starting the API." -ForegroundColor Yellow
}

if (-not $SkipFrontend) {
    Push-Location $frontendDir
    try {
        npm ci
    }
    finally {
        Pop-Location
    }

    $frontendEnv = Join-Path $frontendDir ".env.local"
    if (-not (Test-Path -LiteralPath $frontendEnv)) {
        Copy-Item -LiteralPath (Join-Path $frontendDir ".env.windows.example") -Destination $frontendEnv
    }
}

Write-Host ""
Write-Host "Windows development setup is ready." -ForegroundColor Green
Write-Host "1. Edit backend\.env and replace [URL-ENCODED-PASSWORD]."
Write-Host "2. Run .\scripts\windows\Invoke-Migrations.ps1"
Write-Host "3. Run .\scripts\windows\Start-Development.ps1"
