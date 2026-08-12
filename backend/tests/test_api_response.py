from types import SimpleNamespace

from app.api.response import customer_safe_api_value, envelope, exception_envelope


def test_exception_envelope_removes_internal_supplier_from_nested_messages() -> None:
    supplier = "".join(("Data", "For", "SEO"))
    request = SimpleNamespace(state=SimpleNamespace(request_id="request-1", tenant_id="tenant-1"))

    payload = exception_envelope(
        request,
        502,
        f"{supplier} request failed",
        "provider_failed",
        {"message": f"https://api.{supplier.lower()}.com/v3 failed", "items": [supplier]},
    )

    assert "dataforseo" not in str(payload).lower()
    assert payload["errors"][0]["message"] == "the search data service request failed"
    assert payload["errors"][0]["details"]["items"] == ["the search data service"]


def test_customer_safe_api_value_preserves_non_string_values() -> None:
    assert customer_safe_api_value({"count": 3, "ready": True}) == {
        "count": 3,
        "ready": True,
    }


def test_success_envelope_sanitizes_legacy_error_payloads() -> None:
    supplier = "".join(("Data", "For", "SEO"))
    request = SimpleNamespace(state=SimpleNamespace(request_id="request-2", tenant_id="tenant-1"))

    payload = envelope(
        request,
        {"status": "partial"},
        error={"message": f"{supplier} refresh failed"},
    )

    assert payload["error"]["message"] == "the search data service refresh failed"
