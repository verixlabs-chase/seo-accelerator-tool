from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    current = Path(__file__).resolve()

    for parent in current.parents:
        candidate = parent / 'backend' / 'reference_library'
        if candidate.exists():
            return parent

    raise RuntimeError(f'Unable to locate repository root from {current}')


def reference_library_root() -> Path:
    return repo_root() / 'backend' / 'reference_library'


def reference_library_file(section: str, filename: str) -> Path:
    path = reference_library_root() / section / filename

    if not path.exists():
        print(
            'reference_library path missing:',
            {
                'repo_root': str(repo_root()),
                'resolved_path': str(path),
                'cwd': str(Path.cwd()),
            }
        )

    return path
