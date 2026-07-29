from app.services.location_normalization_service import _select_dataforseo_location


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
