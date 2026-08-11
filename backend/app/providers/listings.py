from __future__ import annotations

import base64
from decimal import Decimal
from hashlib import sha256
from typing import Any

import httpx


class DataForSeoBusinessListingsProvider:
    """Read-only boundary for public business records used by listing discovery."""

    ENDPOINT = "https://api.dataforseo.com/v3/business_data/business_listings/search/live"

    def __init__(
        self,
        *,
        login: str,
        password: str,
        timeout_seconds: float = 45.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.login = login.strip()
        self.password = password
        self.timeout_seconds = timeout_seconds
        self._client = client
        if not self.login or not self.password:
            raise ValueError("Search data login and API password are required.")

    def search(
        self,
        *,
        business_name: str,
        latitude: float,
        longitude: float,
        radius_km: float = 25,
        limit: int = 20,
    ) -> dict[str, Any]:
        payload = [
            {
                "title": business_name.strip()[:200],
                "location_coordinate": (
                    f"{float(latitude):.7f},{float(longitude):.7f},"
                    f"{max(1.0, min(float(radius_km), 100000.0)):.2f}"
                ),
                "limit": max(1, min(int(limit), 100)),
                "order_by": ["rating.votes_count,desc"],
            }
        ]
        body = self._post(payload)
        return {
            "items": [_normalize_item(item) for item in _items(body)],
            "cost": _task_cost(body),
        }

    def _post(self, payload: list[dict[str, Any]]) -> dict[str, Any]:
        credential = base64.b64encode(f"{self.login}:{self.password}".encode("utf-8")).decode("ascii")
        headers = {"Authorization": f"Basic {credential}", "Content-Type": "application/json"}
        try:
            if self._client is not None:
                response = self._client.post(
                    self.ENDPOINT,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client() as client:
                    response = client.post(
                        self.ENDPOINT,
                        json=payload,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise ValueError("The directory search timed out. Try again shortly.") from exc
        except httpx.HTTPError as exc:
            raise ValueError("Directory information could not be reached.") from exc
        if response.status_code in {401, 403}:
            raise ValueError("The saved search-data connection was not accepted.")
        if response.status_code == 429:
            raise ValueError("Directory information is busy. Try again shortly.")
        if response.status_code >= 400:
            raise ValueError("Directory information could not be refreshed.")
        try:
            body = response.json()
        except ValueError as exc:
            raise ValueError("Directory information returned an unreadable response.") from exc
        if not isinstance(body, dict):
            raise ValueError("Directory information returned an unexpected response.")
        tasks = _tasks(body)
        if not tasks:
            raise ValueError("Directory information returned no result.")
        failed = next((task for task in tasks if int(task.get("status_code") or 0) >= 40000), None)
        if failed is not None:
            raise ValueError("Directory information could not complete this search.")
        return body


def _tasks(body: dict[str, Any]) -> list[dict[str, Any]]:
    tasks = body.get("tasks")
    return [item for item in tasks if isinstance(item, dict)] if isinstance(tasks, list) else []


def _items(body: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in _tasks(body):
        results = task.get("result")
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, dict):
                continue
            items = result.get("items")
            if isinstance(items, list):
                rows.extend(item for item in items if isinstance(item, dict))
    return rows


def _task_cost(body: dict[str, Any]) -> Decimal:
    return sum((Decimal(str(task.get("cost") or 0)) for task in _tasks(body)), Decimal("0"))


def _normalize_item(item: dict[str, Any]) -> dict[str, Any]:
    address = item.get("address_info") if isinstance(item.get("address_info"), dict) else {}
    external_id = str(item.get("place_id") or item.get("cid") or item.get("feature_id") or "").strip()
    if not external_id:
        identity = "|".join(
            str(item.get(key) or "").strip().casefold()
            for key in ("title", "address", "phone", "domain")
        )
        external_id = sha256(identity.encode("utf-8")).hexdigest()
    return {
        "source_key": "google_maps",
        "source_name": "Google Maps",
        "provider_name": "dataforseo",
        "external_id": external_id,
        "listing_url": item.get("check_url"),
        "status": "verified" if item.get("is_claimed") is True else "live",
        "business_name": item.get("title"),
        "address_line1": address.get("address") or item.get("address"),
        "city": address.get("city"),
        "region": address.get("region"),
        "postal_code": address.get("zip"),
        "country_code": address.get("country_code"),
        "phone": item.get("phone"),
        "website_url": item.get("url"),
        "primary_category": item.get("category"),
        "directory_importance": "essential",
        "confidence": 1.0 if external_id else 0.75,
    }
