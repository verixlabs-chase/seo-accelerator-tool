param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Operational", "Restore", "CredentialRotationDryRun")]
    [string]$Drill,
    [string]$Baseline = ""
)

$ErrorActionPreference = "Stop"
$repositoryRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$backendRoot = Join-Path $repositoryRoot "backend"
$pythonPath = Join-Path $backendRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Backend Python environment not found at $pythonPath"
}

$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$evidenceRoot = Join-Path $backendRoot "artifacts\tr1"
New-Item -ItemType Directory -Path $evidenceRoot -Force | Out-Null

Push-Location $backendRoot
try {
    switch ($Drill) {
        "Operational" {
            $outputPath = Join-Path $evidenceRoot "operational-$timestamp.json"
            & $pythonPath "scripts\capture_tr1_operational_evidence.py" "--output" $outputPath
        }
        "Restore" {
            $outputPath = Join-Path $evidenceRoot "restore-$timestamp.json"
            $arguments = @(
                "scripts\verify_restore_integrity.py",
                "--output",
                $outputPath
            )
            if ($Baseline) {
                $resolvedBaseline = Resolve-Path -LiteralPath $Baseline
                $arguments += @("--baseline", $resolvedBaseline)
            }
            & $pythonPath @arguments
        }
        "CredentialRotationDryRun" {
            $outputPath = Join-Path $evidenceRoot "credential-rotation-$timestamp.json"
            & $pythonPath "scripts\rotate_credential_master_key.py" "--output" $outputPath
        }
    }
    if ($LASTEXITCODE -ne 0) {
        throw "$Drill drill failed with exit code $LASTEXITCODE."
    }
    Write-Host "TR1 evidence saved to $outputPath"
}
finally {
    Pop-Location
}
