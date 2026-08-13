from __future__ import annotations

import base64
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache
from hashlib import sha256
from typing import Any, Protocol

import httpx

from app.core.config import get_settings


class AuthorityProvider(Protocol):
    def fetch_backlinks(self, campaign_id: str) -> list[dict]: ...

    def refresh_citation_status(
        self, campaign_id: str, directory_name: str, current_status: str
    ) -> dict: ...


class DataForSeoAuthorityProvider:
    """Bounded production boundary for live referring-page evidence."""

    BASE_URL = "https://api.dataforseo.com/v3"

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
            raise ValueError("Link research login and API password are required.")

    def page_intersection(
        self,
        *,
        targets: list[str],
        exclude_target: str,
        limit: int,
    ) -> dict[str, Any]:
        clean_targets = [str(value or "").strip() for value in targets if str(value or "").strip()]
        if not clean_targets:
            return {"items": [], "cost": Decimal("0")}
        target_map = {str(index): target for index, target in enumerate(clean_targets, start=1)}
        body = self._post(
            "/backlinks/page_intersection/live",
            [
                {
                    "targets": target_map,
                    "exclude_targets": [exclude_target],
                    "backlinks_status_type": "live",
                    "include_subdomains": True,
                    "include_indirect_links": False,
                    "exclude_internal_backlinks": True,
                    "intersection_mode": "all",
                    "limit": max(1, min(int(limit), 1000)),
                    "order_by": ["1.domain_from_rank,desc", "1.page_from_rank,desc"],
                    "rank_scale": "one_hundred",
                }
            ],
        )
        return {
            "items": _extract_intersection_items(body),
            "cost": _task_cost(body),
        }

    def backlink_changes(self, *, target: str, limit_per_state: int) -> dict[str, Any]:
        """Return exact recently found and explicitly lost owner backlinks."""

        clean_target = str(target or "").strip()
        if not clean_target:
            return {"new_items": [], "lost_items": [], "cost": Decimal("0")}
        limit = max(1, min(int(limit_per_state), 500))
        common = {
            "target": clean_target,
            "mode": "one_per_domain",
            "include_subdomains": True,
            "exclude_internal_backlinks": True,
            "limit": limit,
            "rank_scale": "one_hundred",
        }
        new_body = self._post(
            "/backlinks/backlinks/live",
            [
                {
                    **common,
                    "backlinks_status_type": "live",
                    "filters": ["is_new", "=", True],
                    "order_by": ["first_seen,desc", "last_seen,desc"],
                }
            ],
        )
        lost_body = self._post(
            "/backlinks/backlinks/live",
            [
                {
                    **common,
                    "backlinks_status_type": "lost",
                    "order_by": ["last_seen,desc", "first_seen,desc"],
                }
            ],
        )
        return {
            "new_items": _extract_backlink_items(new_body),
            "lost_items": _extract_backlink_items(lost_body),
            "cost": _task_cost(new_body) + _task_cost(lost_body),
        }

    def authority_inventory(
        self,
        *,
        target: str,
        business_name: str,
        link_limit: int,
        mention_limit: int,
    ) -> dict[str, Any]:
        """Return bounded owner links and exact-name mention candidates with a same-run link check."""

        clean_target = str(target or "").strip()
        clean_name = " ".join(str(business_name or "").split()).strip()
        if not clean_target or not clean_name:
            return {
                "link_items": [],
                "mention_items": [],
                "mention_link_items": [],
                "cost": Decimal("0"),
            }
        bounded_link_limit = max(1, min(int(link_limit), 1000))
        bounded_mention_limit = max(1, min(int(mention_limit), 100))
        link_body = self._post(
            "/backlinks/backlinks/live",
            [
                {
                    "target": clean_target,
                    "mode": "one_per_domain",
                    "backlinks_status_type": "live",
                    "include_subdomains": True,
                    "exclude_internal_backlinks": True,
                    "limit": bounded_link_limit,
                    "order_by": ["domain_from_rank,desc", "page_from_rank,desc"],
                    "rank_scale": "one_hundred",
                }
            ],
        )
        mention_body = self._post(
            "/content_analysis/search/live",
            [
                {
                    "keyword": f'"{clean_name}"',
                    "search_mode": "one_per_domain",
                    "limit": bounded_mention_limit,
                    "filters": ["main_domain", "<>", clean_target],
                }
            ],
        )
        mention_items = _extract_content_analysis_items(mention_body)
        candidate_urls = list(
            dict.fromkeys(
                str(item.get("url") or item.get("url_normalized") or "").strip()
                for item in mention_items
                if str(item.get("url") or item.get("url_normalized") or "").strip()
            )
        )
        mention_link_body: dict[str, Any] = {"tasks": []}
        if candidate_urls:
            mention_link_body = self._post(
                "/backlinks/backlinks/live",
                [
                    {
                        "target": clean_target,
                        "mode": "as_is",
                        "backlinks_status_type": "live",
                        "include_subdomains": True,
                        "exclude_internal_backlinks": True,
                        "filters": ["url_from", "in", candidate_urls],
                        "limit": min(len(candidate_urls) * 10, 1000),
                        "rank_scale": "one_hundred",
                    }
                ],
            )
        return {
            "link_items": _extract_backlink_items(link_body),
            "mention_items": mention_items,
            "mention_link_items": _extract_backlink_items(mention_link_body),
            "cost": (
                _task_cost(link_body)
                + _task_cost(mention_body)
                + _task_cost(mention_link_body)
            ),
        }

    def _post(self, path: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
        credential = base64.b64encode(f"{self.login}:{self.password}".encode("utf-8")).decode(
            "ascii"
        )
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
            raise ValueError("Link research timed out. Try again in a moment.") from exc
        except httpx.HTTPError as exc:
            raise ValueError("Link research could not be reached.") from exc
        if response.status_code in {401, 403}:
            raise ValueError("Link research credentials were not accepted.")
        if response.status_code == 429:
            raise ValueError("Link research is busy. Try again shortly.")
        if response.status_code >= 400:
            raise ValueError("Link research could not complete this comparison.")
        try:
            body = response.json()
        except ValueError as exc:
            raise ValueError("Link research returned an unreadable response.") from exc
        if not isinstance(body, dict):
            raise ValueError("Link research returned an unexpected response.")
        tasks = _tasks(body)
        if not tasks or any(int(task.get("status_code", 0) or 0) >= 40000 for task in tasks):
            raise ValueError("Link research could not complete this comparison.")
        return body


class SyntheticAuthorityProvider:
    @staticmethod
    def _stable_float(seed: str, minimum: float, maximum: float, decimals: int = 2) -> float:
        digest = sha256(seed.encode("utf-8")).digest()
        scaled = int.from_bytes(digest[:8], "big") / float(2**64)
        return round(minimum + ((maximum - minimum) * scaled), decimals)

    def fetch_backlinks(self, campaign_id: str) -> list[dict]:
        return [
            {
                "source_url": "https://example-partner.com/local-seo-resource",
                "target_url": f"https://{campaign_id}.example.com/",
                "quality_score": self._stable_float(f"{campaign_id}:backlink", 0.5, 0.95),
                "status": "live",
            }
        ]

    def refresh_citation_status(
        self, campaign_id: str, directory_name: str, current_status: str
    ) -> dict:  # noqa: ARG002
        if current_status != "submitted":
            return {
                "submission_status": current_status,
                "listing_url": None,
                "updated_at": datetime.now(UTC),
            }
        return {
            "submission_status": "verified",
            "listing_url": f"https://directory.example/{directory_name.lower().replace(' ', '-')}",
            "updated_at": datetime.now(UTC),
        }


@lru_cache
def get_authority_provider() -> AuthorityProvider:
    settings = get_settings()
    backend = getattr(settings, "authority_provider_backend", "synthetic").strip().lower()
    if backend == "synthetic":
        if getattr(settings, "app_env", "").strip().lower() != "test":
            raise ValueError(
                "authority_provider_unavailable: synthetic backend is allowed only in test fixture mode."
            )
        return SyntheticAuthorityProvider()
    raise ValueError(f"Unsupported authority provider backend: {backend}")


def _tasks(body: dict[str, Any]) -> list[dict[str, Any]]:
    rows = body.get("tasks", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _task_cost(body: dict[str, Any]) -> Decimal:
    return sum(
        (Decimal(str(task.get("cost", 0) or 0)) for task in _tasks(body)),
        Decimal("0"),
    )


def _extract_intersection_items(body: dict[str, Any]) -> list[dict[str, Any]]:
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


def _extract_backlink_items(body: dict[str, Any]) -> list[dict[str, Any]]:
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


def _extract_content_analysis_items(body: dict[str, Any]) -> list[dict[str, Any]]:
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
