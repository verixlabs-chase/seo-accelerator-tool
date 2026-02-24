from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_system_diagnostic_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "system_diagnostic.py"
    spec = importlib.util.spec_from_file_location("system_diagnostic_module", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_system_diagnostic_exits_zero_in_clean_environment(monkeypatch):
    module = _load_system_diagnostic_module()

    for env_name in module.PROXY_ENV_VARS + module.PIP_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)

    def _fake_run(command: list[str], capture_output: bool, text: bool):
        _ = capture_output, text
        if command[-2:] == ["pip", "--version"]:
            return SimpleNamespace(returncode=0, stdout="pip 25.0 (python 3.12)", stderr="")
        if command[-3:] == ["pip", "config", "list"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if command == ["docker", "--version"]:
            return SimpleNamespace(returncode=0, stdout="Docker version 27.0.0, build test", stderr="")
        if command == ["docker", "info"]:
            return SimpleNamespace(returncode=0, stdout="Server: Docker", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", _fake_run)
    monkeypatch.setattr(module, "check_pypi_connectivity", lambda: (True, "PyPI reachable GET=200 HEAD=200"))
    assert module.main() == 0
