from __future__ import annotations

import os
import subprocess
import sys
from typing import Tuple

import requests


PROXY_ENV_VARS = ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]
PIP_ENV_VARS = ["PIP_NO_INDEX", "PIP_INDEX_URL", "PIP_EXTRA_INDEX_URL"]


def _run_command(command: list[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(command, capture_output=True, text=True)
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def check_pypi_connectivity() -> tuple[bool, str]:
    url = "https://pypi.org/simple"
    try:
        get_response = requests.get(url, timeout=10)
        head_response = requests.head(url, timeout=10)
    except requests.RequestException as exc:
        return False, f"PyPI connectivity error: {exc}"
    if get_response.status_code >= 400 or head_response.status_code >= 400:
        return False, f"PyPI status codes GET={get_response.status_code} HEAD={head_response.status_code}"
    return True, f"PyPI reachable GET={get_response.status_code} HEAD={head_response.status_code}"


def check_docker() -> tuple[str, bool, str]:
    code, out, err = _run_command(["docker", "--version"])
    if code != 0:
        return f"unavailable ({err or out})", False, "docker CLI not available"
    docker_cli = out or "docker version output unavailable"
    info_code, info_out, info_err = _run_command(["docker", "info"])
    if info_code != 0:
        return docker_cli, False, (info_err or info_out or "docker info failed")
    return docker_cli, True, "docker daemon reachable"


def main() -> int:
    failures: list[str] = []
    print(f"Python version: {sys.version}")
    code, pip_version, pip_err = _run_command([sys.executable, "-m", "pip", "--version"])
    print(f"pip version: {pip_version if pip_version else pip_err}")
    code, pip_config, pip_cfg_err = _run_command([sys.executable, "-m", "pip", "config", "list"])
    print("pip config list:")
    print(pip_config if pip_config else "(empty)")
    if pip_cfg_err:
        print(f"pip config stderr: {pip_cfg_err}")
    for env_name in PROXY_ENV_VARS + PIP_ENV_VARS:
        print(f"{env_name}={os.getenv(env_name, '')}")

    pip_no_index = (os.getenv("PIP_NO_INDEX") or "").strip().lower()
    if pip_no_index in {"1", "true", "yes", "on"}:
        failures.append("PIP_NO_INDEX is enabled")

    if any((os.getenv(name) or "").strip() for name in PROXY_ENV_VARS):
        failures.append("Proxy environment variables are set")

    pypi_ok, pypi_message = check_pypi_connectivity()
    print(pypi_message)
    if not pypi_ok:
        failures.append("PyPI unreachable")

    docker_cli, docker_ok, docker_message = check_docker()
    print(f"Docker CLI version: {docker_cli}")
    print(f"Docker daemon check: {docker_message}")
    if not docker_ok:
        failures.append("Docker daemon unreachable")

    if failures:
        print("DIAGNOSTIC FAILURES:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("SYSTEM DIAGNOSTIC OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
