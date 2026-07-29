from app.models.business_location import BusinessLocation
from app.services import location_normalization_service
from app.services.location_normalization_service import (
    _resolve_coordinates,
    _select_dataforseo_location,
)


def test_select_dataforseo_location_expands_us_region_abbreviation():
    rows = [
        {
            "location_code": 1,
            "location_name": "Reno,Ohio,United States",
            "country_iso_code": "US",
            "location_type": "City",
        },
        {
            "location_code": 1022653,
            "location_name": "Reno,Nevada,United States",
            "country_iso_code": "US",
            "location_type": "City",
        },
        {
            "location_code": 3,
            "location_name": "Reno,Nevada,United States",
            "country_iso_code": "US",
            "location_type": "County",
        },
    ]

    match = _select_dataforseo_location(
        rows,
        city="Reno",
        region="NV",
        country_code="US",
    )

    assert match == {
        "location_code": "1022653",
        "location_name": "Reno, Nevada, United States",
        "location_type": "City",
    }


def test_select_dataforseo_location_requires_exact_region():
    rows = [
        {
            "location_code": 1,
            "location_name": "Lexington,Massachusetts,United States",
            "country_iso_code": "US",
            "location_type": "City",
        }
    ]

    assert (
        _select_dataforseo_location(
            rows,
            city="Lexington",
            region="Kentucky",
            country_code="US",
        )
        is None
    )


def test_coordinate_resolution_falls_back_from_address_to_city_center(monkeypatch):
    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class _Client:
        def __init__(self):
            self.calls = []
            self.responses = [
                _Response([]),
                _Response([{"lat": "38.0406", "lon": "-84.5037"}]),
            ]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def get(self, url, *, params, headers):
            self.calls.append({"url": url, "params": dict(params), "headers": dict(headers)})
            return self.responses.pop(0)

    fake_client = _Client()
    monkeypatch.setattr(
        location_normalization_service.httpx,
        "Client",
        lambda **_kwargs: fake_client,
    )
    monkeypatch.setattr(location_normalization_service, "sleep", lambda _seconds: None)
    location = BusinessLocation(
        city="Lexington",
        region="Kentucky",
        country_code="US",
        address_line1="124 Junk Magic Dr",
    )

    result = _resolve_coordinates(location)

    assert result["status"] == "resolved"
    assert result["precision"] == "city_center"
    assert result["latitude"] == 38.0406
    assert result["longitude"] == -84.5037
    assert "street" in fake_client.calls[0]["params"]
    assert "street" not in fake_client.calls[1]["params"]
