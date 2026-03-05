from app.main import app


def test_app_boot_and_routes_load() -> None:
    assert app is not None
    assert len(app.routes) > 0
