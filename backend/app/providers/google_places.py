from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.providers.base import ProviderBase
from app.providers.errors import (
    ProviderAuthError,
    ProviderBadRequestError,
    ProviderConnectionError,
    ProviderDependencyError,
    ProviderQuotaExceededError,
    ProviderRateLimitError,
    ProviderResponseFormatError,
    ProviderTimeoutError,
)
from app.providers.execution_types import ProviderExecutionRequest
from app.services.provider_credentials_service import resolve_provider_credentials


@dataclass(frozen=True)
class PlaceDetails:
    place_id: str
    name: str
    formatted_address: str
    website_uri: str
    national_phone_number: str
    business_status: str


class GooglePlacesProviderAdapter(ProviderBase):
    provider_version = "google-places-v1"
    capability = "place_details_lookup"

    def __init__(
        self,
        *,
        db: Session,
        timeout_seconds: float | None = None,
        retry_policy=None,
        circuit_breaker=None,
    ) -> None:
        super().__init__(retry_policy=retry_policy, circuit_breaker=circuit_breaker)
        self._db = db
        settings = get_settings()
        self._timeout_seconds = float(timeout_seconds or settings.google_oauth_http_timeout_seconds)
        self._endpoint_base = "https://places.googleapis.com/v1"

    def _execute_impl(self, request: ProviderExecutionRequest) -> dict:
        payload = request.payload
        organization_id = str(payload.get("organization_id", "")).strip()
        place_id = str(payload.get("place_id", "")).strip()
        if not organization_id or not place_id:
            raise ProviderBadRequestError("organization_id and place_id are required for Places details lookups.")

        credentials = resolve_provider_credentials(self._db, organization_id, "google")
        access_token = str(credentials.get("access_token", "")).strip()
        if not access_token:
            raise ProviderAuthError("Google OAuth access token missing for Places provider.")

        timeout_seconds = _resolve_timeout_seconds(payload, self._timeout_seconds)
        endpoint = f"{self._endpoint_base}/places/{place_id}"
        field_mask = str(
            payload.get(
                "field_mask",
                "id,displayName,formattedAddress,websiteUri,nationalPhoneNumber,businessStatus",
            )
        ).strip()
        if not field_mask:
            raise ProviderBadRequestError("field_mask cannot be empty.")

        try:
            with httpx.Client() as client:
                response = client.get(
                    endpoint,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "X-Goog-FieldMask": field_mask,
                    },
                    timeout=timeout_seconds,
                )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Google Places request timed out.") from exc
        except httpx.ConnectError as exc:
            raise ProviderConnectionError("Google Places connection failed.") from exc
        except httpx.HTTPError as exc:
            raise ProviderDependencyError("Google Places dependency call failed.") from exc

        if response.status_code >= 400:
            _raise_for_google_error(response, service_name="Places")

        try:
            body = response.json()
        except ValueError as exc:
            raise ProviderResponseFormatError("Google Places response is not valid JSON.") from exc
        if not isinstance(body, dict):
            raise ProviderResponseFormatError("Google Places response must be a JSON object.")

        display_name = body.get("displayName", {})
        name = ""
        if isinstance(display_name, dict):
            name = str(display_name.get("text", ""))

        details = PlaceDetails(
            place_id=str(body.get("id", "")),
            name=name,
            formatted_address=str(body.get("formattedAddress", "")),
            website_uri=str(body.get("websiteUri", "")),
            national_phone_number=str(body.get("nationalPhoneNumber", "")),
            business_status=str(body.get("businessStatus", "")),
        )
        return {"dataset": "place_details", "details": asdict(details)}


def _resolve_timeout_seconds(payload: dict[str, Any], default_timeout_seconds: float) -> float:
    timeout_budget_ms = payload.get("timeout_budget_ms")
    if timeout_budget_ms is None:
        return default_timeout_seconds
    try:
        timeout_budget_seconds = float(timeout_budget_ms) / 1000.0
    except (TypeError, ValueError) as exc:
        raise ProviderBadRequestError("timeout_budget_ms must be numeric.") from exc
    if timeout_budget_seconds <= 0:
        raise ProviderBadRequestError("timeout_budget_ms must be greater than 0.")
    return min(default_timeout_seconds, timeout_budget_seconds)


def _raise_for_google_error(response: httpx.Response, *, service_name: str) -> None:
    status = response.status_code
    body = _safe_json(response)
    reason = _extract_google_reason(body)
    message = f"Google {service_name} request failed with status {status}."
    if status in {401, 403}:
        if "quota" in reason:
            raise ProviderQuotaExceededError(message, upstream_payload=body)
        raise ProviderAuthError(message, upstream_payload=body)
    if status == 429:
        raise ProviderRateLimitError(message, upstream_payload=body)
    if status in {408, 504}:
        raise ProviderTimeoutError(message, upstream_payload=body)
    if 400 <= status < 500:
        raise ProviderBadRequestError(message, upstream_payload=body)
    if status >= 500:
        raise ProviderDependencyError(message, upstream_payload=body)
    raise ProviderDependencyError(message, upstream_payload=body)


def _safe_json(response: httpx.Response) -> dict[str, Any] | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _extract_google_reason(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    error = payload.get("error")
    if isinstance(error, dict):
        details = error.get("errors")
        if isinstance(details, list) and details:
            first = details[0]
            if isinstance(first, dict):
                return str(first.get("reason", "")).lower()
        status_text = error.get("status")
        if isinstance(status_text, str):
            return status_text.lower()
    return ""
