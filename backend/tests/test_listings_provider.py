from __future__ import annotations

from decimal import Decimal

import httpx

from app.providers.listings import DataForSeoBusinessListingsProvider


def test_business_listing_provider_builds_scoped_request_and_normalizes_items():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "tasks": [
                    {
                        "status_code": 20000,
                        "cost": 0.01,
                        "result": [
                            {
                                "items": [
                                    {
                                        "type": "business_listing",
                                        "title": "Junk Magicians",
                                        "category": "Junk removal service",
                                        "place_id": "ChIJ-test",
                                        "address": "100 Main St, Reno, NV 89501",
                                        "address_info": {
                                            "address": "100 Main St",
                                            "city": "Reno",
                                            "region": "NV",
                                            "zip": "89501",
                                            "country_code": "US",
                                        },
                                        "phone": "+1 775-555-0100",
                                        "url": "https://junkmagiciansnv.com",
                                        "is_claimed": True,
                                    }
                                ]
                            }
                        ],
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = DataForSeoBusinessListingsProvider(
            login="api@example.com",
            password="secret",
            client=client,
        )
        result = provider.search(
            business_name="Junk Magicians",
            latitude=39.5296,
            longitude=-119.8138,
            radius_km=20,
        )

    assert captured["url"].endswith("/v3/business_data/business_listings/search/live")
    assert '"title":"Junk Magicians"' in captured["body"]
    assert '"location_coordinate":"39.5296000,-119.8138000,20.00"' in captured["body"]
    assert result["cost"] == Decimal("0.01")
    assert result["items"] == [
        {
            "source_key": "google_maps",
            "source_name": "Google Maps",
            "provider_name": "dataforseo",
            "external_id": "ChIJ-test",
            "listing_url": None,
            "status": "verified",
            "business_name": "Junk Magicians",
            "address_line1": "100 Main St",
            "city": "Reno",
            "region": "NV",
            "postal_code": "89501",
            "country_code": "US",
            "phone": "+1 775-555-0100",
            "website_url": "https://junkmagiciansnv.com",
            "primary_category": "Junk removal service",
            "directory_importance": "essential",
            "confidence": 1.0,
        }
    ]


def test_business_listing_provider_uses_customer_safe_error_language():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"status_code": 40100})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        provider = DataForSeoBusinessListingsProvider(
            login="api@example.com",
            password="bad",
            client=client,
        )
        try:
            provider.search(
                business_name="Junk Magicians",
                latitude=39.5296,
                longitude=-119.8138,
            )
        except ValueError as exc:
            message = str(exc).lower()
        else:
            raise AssertionError("Expected rejected provider credentials to fail.")

    assert "dataforseo" not in message
    assert "saved search-data connection" in message
