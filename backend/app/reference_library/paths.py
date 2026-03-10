from __future__ import annotations

import os
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def reference_library_root() -> Path:
    return repo_root() / 'backend' / 'reference_library'


def _debug_missing_path(path: Path) -> None:
    print(
        'reference_library path missing:',
        {
            'repo_root': str(repo_root()),
            'resolved_path': str(path.resolve(strict=False)),
            'cwd': os.getcwd(),
        },
    )


def reference_library_file(*parts: str) -> Path:
    path = reference_library_root().joinpath(*parts)
    if not path.exists():
        _debug_missing_path(path)
    return path
