from __future__ import annotations

import importlib
import sys


MODULES = [
    "cryptography",
    "prometheus_client",
    "redis",
    "opentelemetry.sdk",
    "opentelemetry.instrumentation.fastapi",
    "opentelemetry.instrumentation.requests",
    "celery",
    "pydantic_settings",
    "sqlalchemy",
    "jwt",
    "requests",
    "pytest",
    "ruff",
]


def main() -> int:
    missing: list[str] = []
    for module_name in MODULES:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(module_name)
    if missing:
        print("MISSING MODULES:")
        for module_name in missing:
            print(f"- {module_name}")
        return 1
    print("DEV ENV OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
