from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_alembic(backend_dir: Path, env: dict[str, str], *args: str) -> None:
    subprocess.run(
        [sys.executable, '-m', 'alembic', *args],
        cwd=str(backend_dir),
        env=env,
        check=True,
    )


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    temp_dir = Path(tempfile.mkdtemp(prefix='migration-validate-'))
    try:
        db_path = temp_dir / 'test_migration.db'
        dsn = f'sqlite:///{db_path.as_posix()}'

        env = os.environ.copy()
        env['DATABASE_URL'] = dsn
        env['POSTGRES_DSN'] = dsn
        env.setdefault('APP_ENV', 'test')
        env.setdefault('PUBLIC_BASE_URL', 'http://testserver')
        env.setdefault('JWT_SECRET', 'test-secret-key')
        env.setdefault('PLATFORM_MASTER_KEY', 'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=')

        print(f'[migration-validate] DATABASE_URL={dsn}')
        _run_alembic(backend_dir, env, 'upgrade', 'head')
        _run_alembic(backend_dir, env, 'downgrade', 'base')
        _run_alembic(backend_dir, env, 'upgrade', 'head')
        print('[migration-validate] upgrade/downgrade/upgrade passed')
        return 0
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    raise SystemExit(main())
