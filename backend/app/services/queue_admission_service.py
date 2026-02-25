from __future__ import annotations

from app.core.config import get_settings
from app.services import infra_service


def shadow_replay_allowed() -> bool:
    settings = get_settings()
    if not settings.shadow_replay_enabled:
        return False
    if not settings.shadow_replay_backpressure_disable:
        return True

    try:
        crawl_backpressured = infra_service.queue_backpressure_active("crawl")
        content_backpressured = infra_service.queue_backpressure_active("content")
    except Exception:
        # Fail closed: disable shadow replay when admission cannot be evaluated.
        return False

    return not (crawl_backpressured or content_backpressured)
