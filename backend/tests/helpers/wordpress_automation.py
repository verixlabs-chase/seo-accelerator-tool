from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.wordpress_automation_policy import WordPressAutomationPolicy
from app.models.wordpress_site_connection import WordPressSiteConnection


def enable_managed_wordpress_automation(
    db: Session,
    *,
    tenant_id: str,
    organization_id: str,
    campaign_id: str,
    site_url: str,
    allowed_action_types: list[str],
) -> None:
    """Create the explicit connection and policy required by managed-action tests."""
    normalized_site_url = site_url.rstrip("/")
    now = datetime.now(UTC)
    db.add_all(
        [
            WordPressSiteConnection(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign_id,
                site_url=normalized_site_url,
                status="connected",
                plugin_version="test",
                paired_at=now,
            ),
            WordPressAutomationPolicy(
                tenant_id=tenant_id,
                organization_id=organization_id,
                campaign_id=campaign_id,
                automation_enabled=True,
                emergency_stop=False,
                allowed_action_types=list(allowed_action_types),
                allowed_url_prefixes=[f"{normalized_site_url}/"],
                schedule_timezone="UTC",
                schedule_days=[0, 1, 2, 3, 4, 5, 6],
                window_start_local="00:00",
                window_end_local="23:59",
                blackout_windows=[],
                monthly_action_limit=50,
                risk_tier_ceiling=3,
                requires_manual_approval=False,
                acknowledged_by="automated test",
                acknowledged_at=now,
                version=1,
            ),
        ]
    )
    db.commit()
