import httpx

from app.providers.errors import (
    ProviderBadRequestError,
    ProviderRateLimitError,
    classification_from_exception,
    classify_provider_error,
)


def test_classification_maps_timeout() -> None:
    row = classification_from_exception(TimeoutError("timeout"))
    assert row.error_code == "provider_timeout"
    assert row.reason_code == "timeout"
    assert row.retryable is True


def test_classification_maps_http_429_retryable() -> None:
    req = httpx.Request("GET", "https://example.test")
    resp = httpx.Response(429, request=req)
    exc = httpx.HTTPStatusError("rate", request=req, response=resp)
    row = classification_from_exception(exc)
    assert row.error_code == "provider_rate_limited"
    assert row.reason_code == "rate_limited"
    assert row.retryable is True


def test_classify_provider_error_returns_existing_provider_error() -> None:
    err = ProviderRateLimitError("slow down")
    mapped = classify_provider_error(err)
    assert mapped is err


def test_classify_provider_error_maps_non_retryable_bad_request() -> None:
    err = classify_provider_error(ProviderBadRequestError("bad payload"))
    assert err.reason_code == "bad_request"
    assert err.retryable is False
