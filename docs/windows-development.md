# Windows development and operations

## Supported environment

This repository is maintained and tested from Windows. Do not install Docker,
WSL, GNU Make, or a local PostgreSQL/Redis stack for the supported workflow.

Install:

1. Git for Windows
2. Python 3.12 from python.org with **Python Launcher for Windows**
3. Node.js 22 LTS
4. PowerShell 7 (recommended; Windows PowerShell 5.1 is also supported)

Verify:

```powershell
git --version
py -3.12 --version
node --version
npm --version
```

## Bootstrap

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\scripts\windows\Initialize-Development.ps1
```

Use `-Force` to recreate the backend virtual environment. The script will not
overwrite existing `.env` files.

## Database URLs

Use two Supabase pooler URLs:

- application URL: transaction pooler, port `6543`
- migration URL: session pooler, port `5432`

The username is project-scoped:

```text
postgresql://postgres.<project-ref>:<encoded-password>@<pooler-host>:6543/postgres?sslmode=require
```

Encode reserved password characters before inserting the password into a URL.
Examples:

| Character | Encoding |
| --- | --- |
| `@` | `%40` |
| `#` | `%23` |
| `%` | `%25` |
| `/` | `%2F` |
| `:` | `%3A` |
| `?` | `%3F` |

Never put database credentials in a `NEXT_PUBLIC_` variable or commit
`backend\.env`.

## Local execution

```powershell
.\scripts\windows\Invoke-Migrations.ps1
.\scripts\windows\Start-Development.ps1
```

The backend uses the hosted/serverless compatibility settings locally:

- Supabase provides Postgres
- SQLAlchemy does not keep a process-wide connection pool
- Celery uses eager execution
- event streaming falls back to in-process memory
- frontend requests proxy to the local API

## Testing

```powershell
.\scripts\windows\Invoke-Tests.ps1
```

The preflight runs migration validation, backend tests, Ruff, `pip-audit`,
frontend tests, lint, build, and `npm audit`. Tests use isolated SQLite
databases unless a test is explicitly marked as PostgreSQL integration.

## CI and deployment

Every repository workflow runs on `windows-latest`:

- backend and frontend CI
- deterministic replay gate
- go-live preflight
- Supabase migrations

Vercel deploys from GitHub after `main` changes. Do not run migrations inside a
Vercel function; use the Windows GitHub Actions migration workflow.

## Troubleshooting

Run:

```powershell
cd backend
.\.venv312\Scripts\python.exe scripts\system_diagnostic.py
```

If PowerShell blocks a script:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

If port 8000 is occupied:

```powershell
Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
Get-Process -Id <PID>
```

If port 3000 is occupied, use the same commands with port `3000`.
