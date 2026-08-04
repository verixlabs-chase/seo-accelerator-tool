from __future__ import annotations

import base64
import logging
from decimal import Decimal
from typing import Any

import httpx


logger = logging.getLogger("lsos.keyword_research")


class DataForSeoKeywordResearchProvider:
    """Small, typed boundary around the DataForSEO endpoints used by discovery."""

    BASE_URL = "https://api.dataforseo.com/v3"

    def __init__(
        self,
        *,
        login: str,
        password: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.login = login.strip()
        self.password = password
        self.timeout_seconds = timeout_seconds
        self._client = client
        if not self.login or not self.password:
            raise ValueError("Search data login and API password are required.")

    def ranked_keywords(
        self,
        *,
        target: str,
        location_name: str,
        language_code: str,
        limit: int,
    ) -> dict[str, Any]:
        body = self._post(
            "/dataforseo_labs/google/ranked_keywords/live",
            [
                {
                    "target": target,
                    "location_name": _normalize_location_name(location_name),
                    "language_code": language_code,
                    "limit": max(1, min(limit, 1000)),
                    "order_by": ["keyword_data.keyword_info.search_volume,desc"],
                }
            ],
        )
        return {
            "items": _extract_labs_items(body),
            "cost": _task_cost(body),
        }

    def keyword_ideas(
        self,
        *,
        keywords: list[str],
        location_name: str,
        language_code: str,
        limit: int,
    ) -> dict[str, Any]:
        clean_keywords = [value.strip() for value in keywords if value.strip()][:200]
        if not clean_keywords:
            return {"items": [], "cost": Decimal("0")}
        body = self._post(
            "/dataforseo_labs/google/keyword_ideas/live",
            [
                {
                    "keywords": clean_keywords,
                    "location_name": _normalize_location_name(location_name),
                    "language_code": language_code,
                    "limit": max(1, min(limit, 1000)),
                    "order_by": ["keyword_info.search_volume,desc"],
                }
            ],
        )
        return {
            "items": _extract_labs_items(body),
            "cost": _task_cost(body),
        }

    def search_volume(
        self,
        *,
        keywords: list[str],
        location_name: str,
        language_code: str,
    ) -> dict[str, Any]:
        clean_keywords = [value.strip() for value in keywords if value.strip()][:1000]
        if not clean_keywords:
            return {"items": [], "cost": Decimal("0")}
        body = self._post(
            "/keywords_data/google/search_volume/live",
            [
                {
                    "keywords": clean_keywords,
                    "location_name": _normalize_location_name(location_name),
                    "language_code": language_code,
                }
            ],
        )
        return {
            "items": _extract_search_volume_items(body),
            "cost": _task_cost(body),
        }

    def _post(self, path: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        credential = base64.b64encode(
            f"{self.login}:{self.password}".encode("utf-8")
        ).decode("ascii")
        headers = {
            "Authorization": f"Basic {credential}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is not None:
                response = self._client.post(
                    f"{self.BASE_URL}{path}",
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client() as client:
                    response = client.post(
                        f"{self.BASE_URL}{path}",
                        json=payload,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise ValueError("Keyword data provider timed out. Try again in a moment.") from exc
        except httpx.HTTPError as exc:
            raise ValueError("Keyword data provider could not be reached.") from exc

        if response.status_code in {401, 403}:
            raise ValueError("Search data credentials were not accepted.")
        if response.status_code == 429:
            raise ValueError("The search data service is busy. Try again shortly.")
        if response.status_code >= 400:
            raise ValueError(f"Search data request failed with status {response.status_code}.")
        try:
            body = response.json()
        except ValueError as exc:
            raise ValueError("The search data service returned an unreadable response.") from exc
        if not isinstance(body, dict):
            raise ValueError("The search data service returned an unexpected response.")
        _raise_task_error(body)
        return body


def _tasks(body: dict[str, Any]) -> list[dict[str, Any]]:
    rows = body.get("tasks", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _normalize_location_name(value: str) -> str:
    """Match the provider's canonical City,Region,Country location format."""
    parts = [part.strip() for part in str(value or "").split(",") if part.strip()]
    return ",".join(parts) if parts else str(value or "").strip()


def _raise_task_error(body: dict[str, Any]) -> None:
    tasks = _tasks(body)
    if not tasks:
        logger.warning(
            "keyword_provider_missing_tasks status_code=%s status_message=%s",
            body.get("status_code"),
            body.get("status_message"),
        )
        raise ValueError("The search data service returned no task result.")
    failures = [task for task in tasks if int(task.get("status_code", 0) or 0) >= 40000]
    if failures:
        message = str(failures[0].get("status_message", "Provider task failed."))
        logger.warning(
            "keyword_provider_task_failed status_code=%s status_message=%s",
            failures[0].get("status_code"),
            message,
        )
        raise ValueError(f"The search data service could not complete keyword discovery: {message}")


def _task_cost(body: dict[str, Any]) -> Decimal:
    return sum(
        (Decimal(str(task.get("cost", 0) or 0)) for task in _tasks(body)),
        Decimal("0"),
    )


def _extract_labs_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for task in _tasks(body):
        results = task.get("result", [])
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            rows = result.get("items", [])
            if isinstance(rows, list):
                items.extend(row for row in rows if isinstance(row, dict))
    return items


def _extract_search_volume_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for task in _tasks(body):
        results = task.get("result", [])
        if isinstance(results, list):
            items.extend(row for row in results if isinstance(row, dict))
    return items
