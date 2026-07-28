# Development workflow

The authoritative development environment is Windows. WSL, Linux, Docker,
Compose, and GNU Make are not part of the supported workflow.

Use:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Initialize-Development.ps1
.\scripts\windows\Invoke-Migrations.ps1
.\scripts\windows\Start-Development.ps1
```

Run the release-quality validation with:

```powershell
.\scripts\windows\Invoke-Tests.ps1
```

See [`docs/windows-development.md`](../windows-development.md) for prerequisites,
database URL rules, CI behavior, and troubleshooting.
