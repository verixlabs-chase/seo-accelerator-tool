from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ.setdefault("APP_ENV", "production")
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        from app.core.settings import Settings

        _ = Settings()
    except Exception as exc:  # noqa: BLE001
        print(str(exc))
        return 1
    print("CONFIG VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
