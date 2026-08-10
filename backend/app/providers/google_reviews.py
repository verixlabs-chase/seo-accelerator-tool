from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

import httpx


_PARENT_PATTERN = re.compile(r"^accounts/[^/]+/locations/[^/]+$")
_STAR_RATINGS = {
    "ONE": 1.0,
    "TWO": 2.0,
    "THREE": 3.0,
    "FOUR": 4.0,
    "FIVE": 5.0,
}


class GoogleBusinessProfileReviewsProvider:
    """Read-only boundary for reviews from an authorized owned business profile."""

    BASE_URL = "https://mybusiness.googleapis.com/v4"

    def __init__(
        self,
        *,
        access_token: str,
        timeout_seconds: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.access_token = access_token.strip()
        self.timeout_seconds = timeout_seconds
        self._client = client
        if not self.access_token:
            raise ValueError("Google business access is not connected.")

    def list_reviews(
        self,
        *,
        parent: str,
        page_size: int = 50,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        clean_parent = parent.strip().strip("/")
        if not _PARENT_PATTERN.fullmatch(clean_parent):
            raise ValueError("The connected business listing is invalid.")
        params: dict[str, str | int] = {
            "pageSize": max(1, min(int(page_size), 50)),
            "orderBy": "updateTime desc",
        }
        if page_token:
            params["pageToken"] = page_token
        body = self._get(f"{self.BASE_URL}/{clean_parent}/reviews", params=params)
        rows = body.get("reviews")
        return {
            "items": [
                _normalize_review(item)
                for item in rows
                if isinstance(item, dict)
            ]
            if isinstance(rows, list)
            else [],
            "average_rating": _float_or_none(body.get("averageRating")),
            "total_review_count": _int_or_none(body.get("totalReviewCount")),
            "next_page_token": str(body.get("nextPageToken") or "") or None,
        }

    def _get(self, url: str, *, params: dict[str, str | int]) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.access_token}", "Accept": "application/json"}
        try:
            if self._client is not None:
                response = self._client.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.timeout_seconds,
                )
            else:
                with httpx.Client() as client:
                    response = client.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.timeout_seconds,
                    )
        except httpx.TimeoutException as exc:
            raise ValueError("The review connection timed out. Try again shortly.") from exc
        except httpx.HTTPError as exc:
            raise ValueError("Reviews could not be reached.") from exc
        if response.status_code in {401, 403}:
            raise ValueError("Google business access needs attention before reviews can update.")
        if response.status_code == 429:
            raise ValueError("Review updates are busy. Try again shortly.")
        if response.status_code >= 400:
            raise ValueError("Reviews could not be refreshed.")
        try:
            body = response.json()
        except ValueError as exc:
            raise ValueError("The review connection returned an unreadable response.") from exc
        if not isinstance(body, dict):
            raise ValueError("The review connection returned an unexpected response.")
        return body


def _normalize_review(item: dict[str, Any]) -> dict[str, Any]:
    resource_name = str(item.get("name") or "").strip()
    external_id = str(item.get("reviewId") or resource_name.rsplit("/", 1)[-1]).strip()
    reviewer = item.get("reviewer") if isinstance(item.get("reviewer"), dict) else {}
    reply = item.get("reviewReply") if isinstance(item.get("reviewReply"), dict) else {}
    response_text = str(reply.get("comment") or "").strip() or None
    reviewed_at = _timestamp(item.get("createTime")) or _timestamp(item.get("updateTime"))
    if reviewed_at is None:
        reviewed_at = datetime.now(UTC)
    return {
        "source_key": "google_business_profile",
        "source_name": "Google Business Profile",
        "source_type": "owned_profile",
        "provider_name": "google",
        "external_review_id": external_id,
        "external_resource_name": resource_name or None,
        "review_url": None,
        "rating": _rating(item.get("starRating")),
        "body": str(item.get("comment") or "").strip() or None,
        "author_name": str(reviewer.get("displayName") or "").strip() or None,
        "author_is_anonymous": bool(reviewer.get("isAnonymous")),
        "response_status": "responded" if response_text else "unanswered",
        "response_text": response_text,
        "response_updated_at": _timestamp(reply.get("updateTime")),
        "reviewed_at": reviewed_at,
        "provider_updated_at": _timestamp(item.get("updateTime")),
    }


def _rating(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(1.0, min(float(value), 5.0))
    return _STAR_RATINGS.get(str(value or "").strip().upper(), 1.0)


def _timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
