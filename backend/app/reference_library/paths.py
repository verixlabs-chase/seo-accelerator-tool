from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def reference_library_root() -> Path:
    return repo_root() / "backend" / "reference_library"


def resolve_reference_library_root(configured_path: str | Path | None = None) -> Path:
    default_root = reference_library_root()
    if configured_path is None:
        return default_root

    raw = str(configured_path).strip()
    if not raw:
        return default_root

    candidate = Path(raw).expanduser()
    if candidate.is_absolute():
        if candidate.exists():
            return candidate.resolve()

        parts = candidate.parts
        if len(parts) >= 3 and parts[1] == 'backend' and parts[2] == 'reference_library':
            remapped = repo_root().joinpath(*parts[1:])
            if remapped.exists():
                return remapped.resolve()
        return candidate

    repo_relative = (repo_root() / candidate).resolve()
    if repo_relative.exists():
        return repo_relative

    backend_relative = (repo_root() / 'backend' / candidate).resolve()
    if backend_relative.exists():
        return backend_relative

    return repo_relative


def reference_library_file(*parts: str, configured_path: str | Path | None = None) -> Path:
    return resolve_reference_library_root(configured_path).joinpath(*parts)
