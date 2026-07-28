$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$backendScript = Join-Path $repoRoot "scripts\windows\Start-Backend.ps1"
$frontendScript = Join-Path $repoRoot "scripts\windows\Start-Frontend.ps1"
$shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh.exe" } else { "powershell.exe" }

function ConvertTo-EncodedPowerShellCommand {
    param([Parameter(Mandatory)][string]$ScriptPath)

    $escapedPath = $ScriptPath.Replace("'", "''")
    $command = "& '$escapedPath'"
    return [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
}

$backendCommand = ConvertTo-EncodedPowerShellCommand -ScriptPath $backendScript
$frontendCommand = ConvertTo-EncodedPowerShellCommand -ScriptPath $frontendScript
$commonArgs = @("-NoExit", "-ExecutionPolicy", "Bypass", "-EncodedCommand")

Start-Process -FilePath $shell -ArgumentList ($commonArgs + @($backendCommand))
Start-Process -FilePath $shell -ArgumentList ($commonArgs + @($frontendCommand))

Write-Host "Backend and frontend started in separate Windows PowerShell windows." -ForegroundColor Green
Write-Host "Frontend: http://localhost:3000"
Write-Host "Backend:  http://localhost:8000/api/v1/health"
