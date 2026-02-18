from __future__ import annotations

import time
from functools import lru_cache
from typing import Protocol

import httpx


class CrawlAdapter(Protocol):
    def fetch_url(self, url: str, timeout_seconds: float, use_playwright: bool) -> tuple[int | None, str]:
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

    def fetch_url(self, url: str, timeout_seconds: float, use_playwright: bool) -> tuple[int | None, str]:
        if self._circuit_open():
            return None, ""

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
                            browser.close()
                            self._record_success()
                            return status_code, html
                    except Exception:
                        pass

                with httpx.Client(follow_redirects=True) as client:
                    response = client.get(url, timeout=timeout_seconds)
                html = response.text if "text/html" in response.headers.get("content-type", "") else ""
                self._record_success()
                return response.status_code, html
            except Exception:
                self._record_failure()
                if attempt < self.retry_attempts:
                    time.sleep(0.25 * (2 ** (attempt - 1)))
        return None, ""


@lru_cache
def get_crawl_adapter() -> CrawlAdapter:
    return DefaultCrawlAdapter()
