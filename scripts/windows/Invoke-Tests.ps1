param(
    [switch]$SkipDependencyInstall,
    [switch]$SkipSecurityAudit
)

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$preflight = Join-Path $repoRoot "infra\go-live-preflight.ps1"
& $preflight -SkipDependencyInstall:$SkipDependencyInstall -SkipSecurityAudit:$SkipSecurityAudit
exit $LASTEXITCODE
