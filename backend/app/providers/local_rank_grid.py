from __future__ import annotations

import base64
from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


@dataclass(frozen=True)
class GridTaskRequest:
    point_id: str
    keyword: str
    latitude: float
    longitude: float
    tag: str


class LocalRankGridProvider(Protocol):
    def submit(self, requests: list[GridTaskRequest]) -> list[dict[str, Any]]: ...
    def fetch(self, task_id: str) -> dict[str, Any]: ...


def normalize_domain(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if not candidate:
        return ""
    if "://" not in candidate:
        candidate = f"https://{candidate}"
    parsed = urlparse(candidate)
    host = parsed.netloc or parsed.path
    return host[4:] if host.startswith("www.") else host


class SyntheticLocalRankGridProvider:
    """Deterministic fixture provider; intentionally unavailable outside tests."""

    def submit(self, requests: list[GridTaskRequest]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for item in requests:
            digest = sha256(
                f"{item.keyword}|{item.latitude:.5f}|{item.longitude:.5f}".encode()
            ).digest()
            rank = 1 + int.from_bytes(digest[:2], "big") % 27
            rows.append(
                {
                    "point_id": item.point_id,
                    "task_id": f"fixture-{item.point_id}",
                    "status": "ranked" if rank <= 20 else "not_found",
                    "rank": rank if rank <= 20 else None,
                    "matched_business_name": "Fixture business" if rank <= 20 else None,
                    "matched_business_domain": None,
                    "status_code": 20000,
                    "status_message": "Fixture result ready.",
                    "cost": Decimal("0"),
                }
            )
        return rows

    def fetch(self, task_id: str) -> dict[str, Any]:
        return {
            "task_id": task_id,
            "status": "pending",
            "status_code": 20100,
            "status_message": "Fixture task is still pending.",
            "cost": Decimal("0"),
            "items": [],
        }


class DataForSeoLocalRankGridProvider:
    def __init__(self, *, login: str, password: str, client: httpx.Client | None = None) -> None:
        settings = get_settings()
        self.login = login.strip()
        self.password = password
        self.post_endpoint = settings.local_rank_grid_task_post_endpoint
        self.get_endpoint = settings.local_rank_grid_task_get_endpoint.rstrip("/")
        self.timeout = settings.local_rank_grid_timeout_seconds
        self.language_code = settings.local_rank_grid_language_code
        self.depth = max(10, min(int(settings.local_rank_grid_depth), 100))
        self.zoom = max(3, min(int(settings.local_rank_grid_zoom), 20))
        self._client = client
        if not self.login or not self.password:
            raise ValueError("Search data login and API password are required.")

    def _headers(self) -> dict[str, str]:
        encoded = base64.b64encode(f"{self.login}:{self.password}".encode()).decode()
        return {"Authorization": f"Basic {encoded}", "Content-Type": "application/json"}

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            if self._client is not None:
                response = self._client.request(
                    method, url, headers=self._headers(), timeout=self.timeout, **kwargs
                )
            else:
                with httpx.Client() as client:
                    response = client.request(
                        method, url, headers=self._headers(), timeout=self.timeout, **kwargs
                    )
        except httpx.TimeoutException as exc:
            raise ValueError("The map search check timed out. Try again shortly.") from exc
        except httpx.HTTPError as exc:
            raise ValueError("The map search service could not be reached.") from exc
        if response.status_code in {401, 403}:
            raise ValueError("The saved search data connection was not accepted.")
        if response.status_code == 429:
            raise ValueError("The map search service is busy. Try again shortly.")
        response.raise_for_status()
        body = response.json()
        if not isinstance(body, dict):
            raise ValueError("The map search service returned an invalid response.")
        return body

    def submit(self, requests: list[GridTaskRequest]) -> list[dict[str, Any]]:
        if len(requests) > 100:
            raise ValueError("A map search batch cannot exceed 100 checks.")
        payload = [
            {
                "keyword": item.keyword,
                "location_coordinate": f"{item.latitude:.7f},{item.longitude:.7f},{self.zoom}",
                "language_code": self.language_code,
                "depth": self.depth,
                "priority": 1,
                "tag": item.tag,
            }
            for item in requests
        ]
        body = self._request("POST", self.post_endpoint, json=payload)
        tasks = body.get("tasks") if isinstance(body.get("tasks"), list) else []
        rows: list[dict[str, Any]] = []
        for index, item in enumerate(requests):
            task = tasks[index] if index < len(tasks) and isinstance(tasks[index], dict) else {}
            status_code = int(task.get("status_code") or 0)
            task_id = str(task.get("id") or "").strip()
            rows.append(
                {
                    "point_id": item.point_id,
                    "task_id": task_id or None,
                    "status": "pending" if task_id and status_code < 30000 else "failed",
                    "status_code": status_code or None,
                    "status_message": str(task.get("status_message") or "") or None,
                    "cost": Decimal(str(task.get("cost") or "0")),
                }
            )
        return rows

    def fetch(self, task_id: str) -> dict[str, Any]:
        body = self._request("GET", f"{self.get_endpoint}/{task_id}")
        tasks = body.get("tasks") if isinstance(body.get("tasks"), list) else []
        task = tasks[0] if tasks and isinstance(tasks[0], dict) else {}
        status_code = int(task.get("status_code") or 0)
        results = task.get("result") if isinstance(task.get("result"), list) else []
        result = results[0] if results and isinstance(results[0], dict) else {}
        items = result.get("items") if isinstance(result.get("items"), list) else []
        if not results and status_code < 30000:
            status = "pending"
        elif status_code >= 30000:
            status = "failed"
        else:
            status = "ready"
        return {
            "task_id": task_id,
            "status": status,
            "status_code": status_code or None,
            "status_message": str(task.get("status_message") or "") or None,
            "cost": Decimal(str(task.get("cost") or "0")),
            "items": items,
        }


def build_provider(*, backend: str, credentials: dict[str, Any]) -> LocalRankGridProvider:
    settings = get_settings()
    normalized = (backend or settings.rank_provider_backend).strip().lower()
    if normalized == "synthetic":
        if settings.app_env.strip().lower() != "test":
            raise ValueError("Map rank fixtures are unavailable outside the test runtime.")
        return SyntheticLocalRankGridProvider()
    if normalized == "dataforseo":
        return DataForSeoLocalRankGridProvider(
            login=str(credentials.get("login") or credentials.get("username") or ""),
            password=str(credentials.get("password") or ""),
        )
    raise ValueError("The configured map search provider is not supported.")
