from __future__ import annotations

from pathlib import Path


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
CANONICAL_SERVICE = APP_ROOT / "services" / "location_service.py"
FORBIDDEN_PATTERNS = (
    'INSERT INTO locations',
    'UPDATE locations',
    'sa.insert(_LOCATIONS_TABLE)',
    'sa.update(_LOCATIONS_TABLE)',
)


def test_locations_write_surface_is_confined_to_canonical_service() -> None:
    violations: list[str] = []

    for path in APP_ROOT.rglob('*.py'):
        if path == CANONICAL_SERVICE:
            continue
        content = path.read_text(encoding='utf-8')
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in content:
                violations.append(f'{path.relative_to(APP_ROOT)} contains forbidden pattern: {pattern}')

    assert violations == []
