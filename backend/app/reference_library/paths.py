from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def reference_library_root() -> Path:
    return repo_root() / 'backend' / 'reference_library'


def _is_within_repo(path: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(repo_root())
        return True
    except ValueError:
        return False


def _debug_missing_path(path: Path) -> None:
    print(
        'reference_library path missing:',
        {
            'repo_root': str(repo_root()),
            'resolved_path': str(path.resolve(strict=False)),
            'cwd': os.getcwd(),
        },
    )


def _repo_tree_candidates(candidate: Path) -> list[Path]:
    root = repo_root()
    normalized_parts = candidate.parts[1:] if candidate.is_absolute() else candidate.parts

    candidates: list[Path] = []
    if normalized_parts[:2] == ('backend', 'reference_library'):
        candidates.append(root.joinpath(*normalized_parts))
    if normalized_parts[:1] == ('reference_library',):
        candidates.append(root / 'backend' / Path(*normalized_parts))
    if normalized_parts:
        relative_candidate = Path(*normalized_parts)
        candidates.append(root / relative_candidate)
        candidates.append(root / 'backend' / relative_candidate)
    else:
        candidates.append(root)
        candidates.append(root / 'backend')

    unique: list[Path] = []
    seen: set[Path] = set()
    for option in candidates:
        resolved = option.resolve(strict=False)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def resolve_reference_library_root(configured_path: str | Path | None = None) -> Path:
    default_root = reference_library_root().resolve(strict=False)
    if configured_path is None:
        return default_root

    raw = str(configured_path).strip()
    if not raw:
        return default_root

    candidate = Path(raw).expanduser()
    for option in _repo_tree_candidates(candidate):
        if option.exists() and _is_within_repo(option):
            return option

    if candidate.is_absolute() and candidate.exists() and _is_within_repo(candidate):
        return candidate.resolve()

    if default_root.exists():
        return default_root

    _debug_missing_path(default_root)
    return default_root


def reference_library_file(*parts: str, configured_path: str | Path | None = None) -> Path:
    path = resolve_reference_library_root(configured_path).joinpath(*parts)
    if not path.exists():
        _debug_missing_path(path)
    return path
