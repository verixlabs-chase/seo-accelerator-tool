import os
from pathlib import Path
import subprocess
import sys

from app.main import app


def test_app_boot_and_routes_load() -> None:
    assert app is not None
    assert len(app.routes) > 0


def test_app_boots_in_a_fresh_python_process() -> None:
    """Catch import cycles hidden by pytest's shared module import order."""

    backend_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env["APP_ENV"] = "test"
    env["STANDARDS_SOURCE_MONITORING_ENABLED"] = "false"

    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
