from __future__ import annotations

from functools import lru_cache
from random import randint, uniform
from typing import Protocol
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings


class RankProvider(Protocol):
    def collect_keyword_snapshot(self, keyword: str, location_code: str, target_domain: str | None = None) -> dict:
        ...


class SyntheticRankProvider:
    def collect_keyword_snapshot(self, keyword: str, location_code: str, target_domain: str | None = None) -> dict:  # noqa: ARG002
        return {
            "position": randint(1, 100),
            "confidence": round(uniform(0.6, 0.99), 2),
        }


class HttpJsonRankProvider:
    def __init__(
        self,
        *,
        endpoint: str,
        timeout_seconds: float = 15.0,
        auth_header: str = "",
        auth_token: str = "",
        keyword_field: str = "keyword",
        location_field: str = "location_code",
    ) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.auth_header = auth_header
        self.auth_token = auth_token
        self.keyword_field = keyword_field
        self.location_field = location_field

    def collect_keyword_snapshot(self, keyword: str, location_code: str, target_domain: str | None = None) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.auth_header and self.auth_token:
            headers[self.auth_header] = self.auth_token
        payload = {
            self.keyword_field: keyword,
            self.location_field: location_code,
        }
        if target_domain:
            payload["target_domain"] = target_domain
        with httpx.Client() as client:
            response = client.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout_seconds,
            )
        response.raise_for_status()
        body = response.json()
        row = body.get("data") if isinstance(body, dict) and isinstance(body.get("data"), dict) else body
        if not isinstance(row, dict):
            raise ValueError("Rank provider response must be a JSON object.")
        if "position" not in row:
            raise ValueError("Rank provider response is missing 'position'.")
        position = int(row["position"])
        confidence = float(row.get("confidence", 0.75))
        if position < 1:
            position = 1
        return {"position": position, "confidence": round(max(0.0, min(confidence, 1.0)), 2)}


class SerpApiRankProvider:
    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://serpapi.com/search.json",
        timeout_seconds: float = 15.0,
        engine: str = "google",
        default_gl: str = "us",
        default_hl: str = "en",
    ) -> None:
        self.api_key = api_key
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.engine = engine
        self.default_gl = default_gl
        self.default_hl = default_hl

    @staticmethod
    def _normalize_domain(value: str | None) -> str:
        if not value:
            return ""
        candidate = value.strip().lower()
        if not candidate:
            return ""
        if "://" not in candidate:
            candidate = f"https://{candidate}"
        parsed = urlparse(candidate)
        host = parsed.netloc or parsed.path
        if host.startswith("www."):
            host = host[4:]
        return host

    def collect_keyword_snapshot(self, keyword: str, location_code: str, target_domain: str | None = None) -> dict:
        target_host = self._normalize_domain(target_domain)
        if not target_host:
            raise ValueError("SerpAPI rank provider requires target_domain.")
        gl = (location_code or self.default_gl).strip().lower() or self.default_gl
        params = {
            "engine": self.engine,
            "q": keyword,
            "api_key": self.api_key,
            "gl": gl,
            "hl": self.default_hl,
            "num": 100,
        }
        with httpx.Client() as client:
            response = client.get(self.endpoint, params=params, timeout=self.timeout_seconds)
        response.raise_for_status()
        body = response.json()
        organic = body.get("organic_results", []) if isinstance(body, dict) else []
        if not isinstance(organic, list):
            raise ValueError("SerpAPI response missing organic_results list.")
        for item in organic:
            if not isinstance(item, dict):
                continue
            row_link = item.get("link") or item.get("displayed_link") or ""
            row_host = self._normalize_domain(str(row_link))
            if row_host and (row_host == target_host or row_host.endswith(f".{target_host}") or target_host.endswith(f".{row_host}")):
                pos = int(item.get("position", 100))
                return {"position": max(1, pos), "confidence": 0.9}
        return {"position": 100, "confidence": 0.65}


@lru_cache
def get_rank_provider() -> RankProvider:
    settings = get_settings()
    backend = getattr(settings, "rank_provider_backend", "synthetic").strip().lower()
    if backend == "synthetic":
        return SyntheticRankProvider()
    if backend == "http_json":
        endpoint = getattr(settings, "rank_provider_http_endpoint", "").strip()
        if not endpoint:
            raise ValueError("rank_provider_http_endpoint is required for rank_provider_backend=http_json.")
        return HttpJsonRankProvider(
            endpoint=endpoint,
            timeout_seconds=float(getattr(settings, "rank_provider_http_timeout_seconds", 15.0)),
            auth_header=getattr(settings, "rank_provider_http_auth_header", "").strip(),
            auth_token=getattr(settings, "rank_provider_http_auth_token", "").strip(),
            keyword_field=getattr(settings, "rank_provider_http_keyword_field", "keyword").strip(),
            location_field=getattr(settings, "rank_provider_http_location_field", "location_code").strip(),
        )
    if backend == "serpapi":
        api_key = getattr(settings, "rank_provider_serpapi_api_key", "").strip()
        if not api_key:
            raise ValueError("rank_provider_serpapi_api_key is required for rank_provider_backend=serpapi.")
        return SerpApiRankProvider(
            api_key=api_key,
            endpoint=getattr(settings, "rank_provider_serpapi_endpoint", "https://serpapi.com/search.json").strip(),
            timeout_seconds=float(getattr(settings, "rank_provider_serpapi_timeout_seconds", 15.0)),
            engine=getattr(settings, "rank_provider_serpapi_engine", "google").strip(),
            default_gl=getattr(settings, "rank_provider_serpapi_default_gl", "us").strip(),
            default_hl=getattr(settings, "rank_provider_serpapi_default_hl", "en").strip(),
        )
    raise ValueError(f"Unsupported rank provider backend: {backend}")
