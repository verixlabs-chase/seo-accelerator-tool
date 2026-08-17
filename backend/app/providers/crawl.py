from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import httpx

logger = logging.getLogger("lsos.providers.crawl")


@dataclass(frozen=True)
class CrawlFetchResult:
    requested_url: str
    final_url: str
    status_code: int | None
    html: str
    redirect_chain: list[dict[str, object]]
    content_type: str | None = None


class CrawlAdapter(Protocol):
    def fetch_url(
        self,
        url: str,
        timeout_seconds: float,
        use_playwright: bool,
    ) -> CrawlFetchResult:
        ...


class DefaultCrawlAdapter:
    def __init__(self, *, retry_attempts: int = 3, circuit_breaker_threshold: int = 5, circuit_breaker_cooldown_seconds: int = 60) -> None:
        self.retry_attempts = retry_attempts
        self.circuit_breaker_threshold = circuit_breaker_threshold
        self.circuit_breaker_cooldown_seconds = circuit_breaker_cooldown_seconds
        self._failure_count = 0
        self._open_until = 0.0

    def _circuit_open(self) -> bool:
        return time.time() < self._open_until

    def _record_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self.circuit_breaker_threshold:
            self._open_until = time.time() + self.circuit_breaker_cooldown_seconds
            self._failure_count = 0

    def _record_success(self) -> None:
        self._failure_count = 0
        self._open_until = 0.0

    def fetch_url(
        self,
        url: str,
        timeout_seconds: float,
        use_playwright: bool,
    ) -> CrawlFetchResult:
        if self._circuit_open():
            return CrawlFetchResult(url, url, None, "", [])

        attempt = 0
        while attempt < self.retry_attempts:
            attempt += 1
            try:
                if use_playwright:
                    try:
                        from playwright.sync_api import sync_playwright

                        with sync_playwright() as p:
                            browser = p.chromium.launch(headless=True)
                            page = browser.new_page()
                            response = page.goto(url, wait_until="networkidle", timeout=int(timeout_seconds * 1000))
                            html = page.content()
                            status_code = response.status if response is not None else None
                            final_url = page.url or url
                            browser.close()
                            self._record_success()
                            return CrawlFetchResult(
                                requested_url=url,
                                final_url=final_url,
                                status_code=status_code,
                                html=html,
                                redirect_chain=(
                                    [
                                        {
                                            "url": url,
                                            "status_code": status_code,
                                            "location": final_url,
                                        }
                                    ]
                                    if final_url != url
                                    else []
                                ),
                                content_type="text/html",
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Playwright crawl attempt failed; falling back to HTTP client.", exc_info=exc)

                with httpx.Client(follow_redirects=True) as client:
                    response = client.get(url, timeout=timeout_seconds)
                content_type = response.headers.get("content-type", "")
                html = response.text if "text/html" in content_type else ""
                redirect_chain = [
                    {
                        "url": str(item.url),
                        "status_code": item.status_code,
                        "location": item.headers.get("location"),
                    }
                    for item in response.history
                ]
                self._record_success()
                return CrawlFetchResult(
                    requested_url=url,
                    final_url=str(response.url),
                    status_code=response.status_code,
                    html=html,
                    redirect_chain=redirect_chain,
                    content_type=content_type or None,
                )
            except Exception:
                self._record_failure()
                if attempt < self.retry_attempts:
                    time.sleep(0.25 * (2 ** (attempt - 1)))
        return CrawlFetchResult(url, url, None, "", [])


@lru_cache
def get_crawl_adapter() -> CrawlAdapter:
    return DefaultCrawlAdapter()
