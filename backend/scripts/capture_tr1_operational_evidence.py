from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests  # type: ignore[import-untyped]


def _endpoint(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}{path}" if base_url else path


def capture_tr1_operational_evidence(
    client,
    *,  # noqa: ANN001
    base_url: str,
    email: str,
    password: str,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    steps: list[dict[str, Any]] = []

    def record(name: str, response, expected_status: int) -> bool:  # noqa: ANN001
        passed = int(response.status_code) == expected_status
        steps.append(
            {
                "name": name,
                "status_code": int(response.status_code),
                "expected_status": expected_status,
                "passed": passed,
            }
        )
        return passed

    login = client.post(
        _endpoint(base_url, "/api/v1/auth/login"),
        json={"email": email, "password": password},
        timeout=timeout_seconds,
    )
    if not record("login", login, 200):
        return {
            "passed": False,
            "captured_at": datetime.now(UTC).isoformat(),
            "target_host": urlparse(base_url).netloc,
            "steps": steps,
            "durable_jobs": None,
            "secrets_logged": False,
        }
    login_payload = login.json()["data"]
    old_access_token = str(login_payload["access_token"])
    old_refresh_token = str(login_payload["refresh_token"])

    me = client.get(
        _endpoint(base_url, "/api/v1/auth/me"),
        headers={"Authorization": f"Bearer {old_access_token}"},
        timeout=timeout_seconds,
    )
    record("authenticated_identity", me, 200)

    sessions = client.get(
        _endpoint(base_url, "/api/v1/auth/sessions"),
        headers={"Authorization": f"Bearer {old_access_token}"},
        timeout=timeout_seconds,
    )
    record("session_inventory", sessions, 200)

    refresh = client.post(
        _endpoint(base_url, "/api/v1/auth/refresh"),
        json={"refresh_token": old_refresh_token},
        timeout=timeout_seconds,
    )
    refresh_passed = record("refresh_rotation", refresh, 200)
    if not refresh_passed:
        return {
            "passed": False,
            "captured_at": datetime.now(UTC).isoformat(),
            "target_host": urlparse(base_url).netloc,
            "steps": steps,
            "durable_jobs": None,
            "secrets_logged": False,
        }
    refresh_payload = refresh.json()["data"]
    new_access_token = str(refresh_payload["access_token"])
    new_refresh_token = str(refresh_payload["refresh_token"])

    replay = client.post(
        _endpoint(base_url, "/api/v1/auth/refresh"),
        json={"refresh_token": old_refresh_token},
        timeout=timeout_seconds,
    )
    record("old_refresh_replay_blocked", replay, 401)

    health = client.get(
        _endpoint(base_url, "/api/v1/system/operational-health"),
        headers={"Authorization": f"Bearer {new_access_token}"},
        timeout=timeout_seconds,
    )
    health_passed = record("operational_health", health, 200)
    durable_jobs = None
    if health_passed:
        durable_jobs = health.json()["data"]["operational_health"].get("durable_jobs")

    logout = client.post(
        _endpoint(base_url, "/api/v1/auth/logout"),
        headers={"Authorization": f"Bearer {new_access_token}"},
        timeout=timeout_seconds,
    )
    record("logout_revocation", logout, 200)

    old_access = client.get(
        _endpoint(base_url, "/api/v1/auth/me"),
        headers={"Authorization": f"Bearer {old_access_token}"},
        timeout=timeout_seconds,
    )
    record("old_access_after_logout_blocked", old_access, 401)

    current_refresh = client.post(
        _endpoint(base_url, "/api/v1/auth/refresh"),
        json={"refresh_token": new_refresh_token},
        timeout=timeout_seconds,
    )
    record("current_refresh_after_logout_blocked", current_refresh, 401)

    return {
        "passed": all(step["passed"] for step in steps),
        "captured_at": datetime.now(UTC).isoformat(),
        "target_host": urlparse(base_url).netloc,
        "steps": steps,
        "durable_jobs": durable_jobs,
        "secrets_logged": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Capture TR1 production session-rotation and durable-job evidence "
            "without writing credentials or tokens to output."
        )
    )
    parser.add_argument(
        "--output",
        default="artifacts/tr1/operational-evidence.json",
    )
    args = parser.parse_args()

    base_url = os.getenv("TR1_API_BASE_URL", "").strip()
    email = os.getenv("TR1_PLATFORM_EMAIL", "").strip()
    password = os.getenv("TR1_PLATFORM_PASSWORD", "")
    if not base_url or not email or not password:
        raise SystemExit(
            "TR1_API_BASE_URL, TR1_PLATFORM_EMAIL, and TR1_PLATFORM_PASSWORD are required."
        )

    with requests.Session() as client:
        result = capture_tr1_operational_evidence(
            client,
            base_url=base_url,
            email=email,
            password=password,
        )
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
