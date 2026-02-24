$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Write-Host "Resetting process and user proxy/pip environment..."
$vars = @("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "PIP_NO_INDEX")
foreach ($name in $vars) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
    [Environment]::SetEnvironmentVariable($name, $null, "User")
}

Write-Host "Clearing pip cache..."
try {
    python -m pip cache purge | Out-Host
} catch {
    Write-Warning "pip cache purge failed: $($_.Exception.Message)"
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPath = Join-Path $repoRoot ".venv"
if (Test-Path $venvPath) {
    Write-Host "Removing existing .venv..."
    Remove-Item -Recurse -Force $venvPath
}

try {
    $pythonVersion = (python --version).Trim()
    Write-Host "Detected Python: $pythonVersion"
    if ($pythonVersion -notmatch "^Python 3\.(11|12)\.") {
        Write-Warning "Unsupported Python version detected. Install Python 3.11.x or 3.12.x before bootstrapping."
    }
} catch {
    Write-Warning "Unable to detect python executable in PATH."
}

Write-Host "Testing PyPI connectivity with curl..."
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri "https://pypi.org/simple" -Method Head -TimeoutSec 15
    Write-Host "PyPI connectivity status: $($response.StatusCode)"
} catch {
    Write-Error "PyPI connectivity check failed: $($_.Exception.Message)"
    exit 1
}

Write-Host "Running minimal pip install test (requests)..."
try {
    python -m pip install --no-cache-dir --index-url https://pypi.org/simple requests | Out-Host
} catch {
    Write-Error "Minimal pip install test failed: $($_.Exception.Message)"
    exit 1
}

Write-Host "reset_dev_env completed."
