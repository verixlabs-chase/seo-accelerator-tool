from __future__ import annotations

from pathlib import Path


def _looks_like_asset_root(candidate: Path) -> bool:
    return (
        candidate.is_dir()
        and (candidate / 'metrics' / 'core_web_vitals.json').is_file()
        and (candidate / 'recommendations' / 'perf_recommendations.json').is_file()
    )


def _candidate_reference_library_roots() -> list[Path]:
    current = Path(__file__).resolve()
    candidates: list[Path] = []
    seen: set[Path] = set()

    for parent in current.parents:
        for candidate in (parent / 'reference_library', parent / 'backend' / 'reference_library'):
            resolved = candidate.resolve(strict=False)
            if resolved in seen:
                continue
            seen.add(resolved)
            candidates.append(candidate)

    return candidates


def repo_root() -> Path:
    root = reference_library_root()
    if root.parent.name == 'backend':
        return root.parent.parent
    return root.parent


def reference_library_root() -> Path:
    for candidate in _candidate_reference_library_roots():
        if _looks_like_asset_root(candidate):
            return candidate

    checked = [str(path) for path in _candidate_reference_library_roots()]
    current = Path(__file__).resolve()
    raise RuntimeError(
        f'Unable to locate reference library assets from {current}; checked: {checked}'
    )


def reference_library_file(section: str, filename: str) -> Path:
    path = reference_library_root() / section / filename

    if not path.exists():
        print(
            'reference_library path missing:',
            {
                'reference_library_root': str(reference_library_root()),
                'resolved_path': str(path),
                'cwd': str(Path.cwd()),
            }
        )

    return path
