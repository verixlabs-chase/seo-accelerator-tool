from collections import Counter

from app.main import app


def test_no_duplicate_route_method_pairs() -> None:
    pairs: list[tuple[str, str]] = []
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if not methods:
            continue
        for method in methods:
            pairs.append((route.path, method))

    duplicates = [pair for pair, count in Counter(pairs).items() if count > 1]
    assert not duplicates, f"Duplicate route+method pairs found: {duplicates}"
