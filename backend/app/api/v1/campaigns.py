from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.db.session import get_db
from app.events import emit_event
from app.models.campaign import Campaign
from app.models.organization import Organization
from app.models.sub_account import SubAccount
from app.models.tenant import Tenant
from app.schemas.campaign_dashboard import CampaignDashboardOut
from app.schemas.campaign_performance import CampaignPerformanceSummaryOut, CampaignPerformanceTrendOut, CampaignReportOut
from app.schemas.campaigns import CampaignCreateRequest, CampaignOut, CampaignSetupTransitionRequest
from app.services.campaign_dashboard_service import build_campaign_dashboard
from app.services.campaign_performance_service import build_campaign_performance_summary, build_campaign_performance_trend
from app.services.feature_gate_service import assert_feature_available
from app.services.strategy_engine.schemas import CampaignStrategyOut, StrategyWindow
from app.services.strategy_build_service import build_campaign_strategy_idempotent
from app.services import lifecycle_service

router = APIRouter(prefix="/campaigns", tags=["campaigns"])


@router.post("")
def create_campaign(
    request: Request,
    body: CampaignCreateRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    tenant = db.get(Tenant, user["tenant_id"])
    if tenant is None or tenant.status != "Active":
        return envelope(
            request,
            None,
            {
                "code": "tenant_inactive",
                "message": "Tenant must be Active to create campaigns.",
                "details": {},
            },
        )
    organization_id = user.get("organization_id")
    if not isinstance(organization_id, str) or not organization_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization context required")
    organization = db.query(Organization).filter(Organization.id == organization_id).first()
    if organization is None or organization.id != user["tenant_id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization scope mismatch")

    sub_account_id = body.sub_account_id
    if sub_account_id is not None:
        sub_account = (
            db.query(SubAccount)
            .filter(
                SubAccount.id == sub_account_id,
                SubAccount.organization_id == user["organization_id"],
            )
            .first()
        )
        if sub_account is None:
            return envelope(
                request,
                None,
                {
                    "code": "subaccount_not_found",
                    "message": "SubAccount not found in organization scope.",
                    "details": {"sub_account_id": sub_account_id},
                },
            )
        if sub_account.status != "active":
            return envelope(
                request,
                None,
                {
                    "code": "subaccount_inactive",
                    "message": "SubAccount must be active to attach new campaigns.",
                    "details": {"sub_account_id": sub_account_id, "status": sub_account.status},
                },
            )

    campaign = Campaign(
        tenant_id=user["tenant_id"],
        organization_id=organization_id,
        sub_account_id=sub_account_id,
        name=body.name,
        domain=body.domain,
    )
    db.add(campaign)
    db.flush()
    emit_event(
        db,
        tenant_id=user["tenant_id"],
        event_type="campaign.created",
        payload={"campaign_id": campaign.id, "setup_state": campaign.setup_state, "sub_account_id": campaign.sub_account_id},
    )
    db.commit()
    db.refresh(campaign)
    return envelope(request, CampaignOut.model_validate(campaign).model_dump(mode="json"))


@router.get("")
def list_campaigns(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaigns = (
        db.query(Campaign)
        .filter(Campaign.tenant_id == user["tenant_id"])
        .order_by(Campaign.created_at.desc())
        .all()
    )
    data = [CampaignOut.model_validate(c).model_dump(mode="json") for c in campaigns]
    return envelope(request, {"items": data})


@router.patch("/{campaign_id}/setup-state")
def transition_campaign_setup_state(
    request: Request,
    campaign_id: str,
    body: CampaignSetupTransitionRequest,
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    row = lifecycle_service.transition_campaign_setup_state(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign_id,
        target_state=body.target_state,
    )
    return envelope(request, CampaignOut.model_validate(row).model_dump(mode="json"))


@router.get("/{id}/dashboard")
def get_campaign_dashboard(
    request: Request,
    id: str,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == id, Campaign.tenant_id == user["tenant_id"]).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    normalized_date_to = _as_utc(date_to) or datetime.now(UTC)
    normalized_date_from = _as_utc(date_from) or (normalized_date_to - timedelta(days=30))
    if normalized_date_from > normalized_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "date_from must be less than or equal to date_to.",
                "reason_code": "invalid_date_range",
            },
        )

    payload = build_campaign_dashboard(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=id,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
    )
    return envelope(request, CampaignDashboardOut.model_validate(payload).model_dump(mode="json"))


@router.get("/{id}/performance-summary")
def get_campaign_performance_summary(
    request: Request,
    id: str,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == id, Campaign.tenant_id == user["tenant_id"]).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    normalized_date_to = _as_utc(date_to) or datetime.now(UTC)
    normalized_date_from = _as_utc(date_from) or (normalized_date_to - timedelta(days=30))
    if normalized_date_from > normalized_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "date_from must be less than or equal to date_to.",
                "reason_code": "invalid_date_range",
            },
        )

    payload = build_campaign_performance_summary(
        db,
        campaign=campaign,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
    )
    return envelope(request, CampaignPerformanceSummaryOut.model_validate(payload).model_dump(mode="json"))


@router.get("/{id}/performance-trend")
def get_campaign_performance_trend(
    request: Request,
    id: str,
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
    interval: Literal["day", "week", "month"] = Query(default="week"),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == id, Campaign.tenant_id == user["tenant_id"]).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    org = _organization_or_404(db, user["tenant_id"])
    assert_feature_available(org=org, feature_name="performance_trend")

    normalized_date_from, normalized_date_to = _resolve_trend_window(date_from=date_from, date_to=date_to)
    payload = build_campaign_performance_trend(
        db,
        campaign=campaign,
        date_from=normalized_date_from,
        date_to=normalized_date_to,
        interval=interval,
    )
    return envelope(request, CampaignPerformanceTrendOut.model_validate(payload).model_dump(mode="json"))


@router.get("/{id}/report")
def get_campaign_report(
    request: Request,
    id: str,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    trend_interval: Literal["day", "week", "month"] = Query(default="week"),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == id, Campaign.tenant_id == user["tenant_id"]).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    org = _organization_or_404(db, user["tenant_id"])
    assert_feature_available(org=org, feature_name="campaign_report")

    summary_date_from, summary_date_to = _resolve_summary_window(date_from=date_from, date_to=date_to)
    trend_date_from, trend_date_to = _resolve_report_trend_window(
        date_from=date_from,
        date_to=date_to,
        summary_date_to=summary_date_to,
    )

    summary_payload = build_campaign_performance_summary(
        db,
        campaign=campaign,
        date_from=summary_date_from,
        date_to=summary_date_to,
    )
    trend_payload = build_campaign_performance_trend(
        db,
        campaign=campaign,
        date_from=trend_date_from,
        date_to=trend_date_to,
        interval=trend_interval,
    )
    dashboard_payload = build_campaign_dashboard(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=id,
        date_from=summary_date_from,
        date_to=summary_date_to,
    )

    payload = {
        "campaign_id": campaign.id,
        "overview": {
            "visibility_score": summary_payload["visibility_score"],
            "traffic_growth_percent": summary_payload["traffic_growth_percent"],
            "position_delta": summary_payload["position_delta"],
            "opportunity_flag": summary_payload["opportunity_flag"],
            "decline_flag": summary_payload["decline_flag"],
        },
        "performance_snapshot": {
            "clicks": summary_payload["clicks"],
            "impressions": summary_payload["impressions"],
            "ctr": summary_payload["ctr"],
            "avg_position": summary_payload["avg_position"],
            "sessions": summary_payload["sessions"],
            "conversions": summary_payload["conversions"],
        },
        "trend": {
            "interval": trend_payload["interval"],
            "date_from": trend_payload["date_from"],
            "date_to": trend_payload["date_to"],
            "points": trend_payload["points"],
        },
        "operational_reliability": {
            "total_calls": dashboard_payload["metrics"]["total_calls"],
            "success_rate_percent": dashboard_payload["metrics"]["success_rate_percent"],
            "p95_latency_ms": dashboard_payload["metrics"]["p95_latency_ms"],
            "top_failing_provider": dashboard_payload["metrics"]["top_failing_provider"],
            "top_failing_capability": dashboard_payload["metrics"]["top_failing_capability"],
        },
    }
    return envelope(request, CampaignReportOut.model_validate(payload).model_dump(mode="json"))


@router.get("/{id}/strategy")
def get_campaign_strategy(
    request: Request,
    id: str,
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    user: dict = Depends(require_roles({"tenant_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    campaign = db.query(Campaign).filter(Campaign.id == id, Campaign.tenant_id == user["tenant_id"]).first()
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")

    org = _organization_or_404(db, user["tenant_id"])
    # Strategy is intentionally gated at the same Pro+ threshold as report/trend.
    assert_feature_available(org=org, feature_name="campaign_report")

    summary_date_from, summary_date_to = _resolve_summary_window(date_from=date_from, date_to=date_to)
    plan_type = org.plan_type.strip().lower()
    tier = "enterprise" if plan_type == "enterprise" else "pro"

    payload = build_campaign_strategy_idempotent(
        db,
        tenant_id=user["tenant_id"],
        campaign_id=campaign.id,
        window=StrategyWindow(date_from=summary_date_from, date_to=summary_date_to),
        raw_signals={},
        tier=tier,
    )
    response_payload = CampaignStrategyOut.model_validate(payload).model_dump(mode="json")
    temporal_meta = response_payload.get("meta", {}).get("temporal", {})
    if isinstance(temporal_meta, dict):
        for key in ("current_strategy_phase", "momentum_score", "trend_direction", "volatility_level"):
            if key in temporal_meta:
                response_payload[key] = temporal_meta[key]
    return envelope(request, response_payload)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _resolve_trend_window(*, date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    if date_from is None and date_to is None:
        resolved_to = today
        resolved_from = resolved_to - timedelta(days=89)
    elif date_from is not None and date_to is None:
        resolved_from = date_from
        resolved_to = date_from + timedelta(days=89)
    elif date_from is None and date_to is not None:
        resolved_to = date_to
        resolved_from = date_to - timedelta(days=89)
    else:
        assert date_from is not None and date_to is not None
        resolved_from = date_from
        resolved_to = date_to

    if resolved_from > resolved_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "date_from must be less than or equal to date_to.",
                "reason_code": "invalid_date_range",
            },
        )

    window_days = (resolved_to - resolved_from).days + 1
    if window_days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "Date window cannot exceed 365 days.",
                "reason_code": "window_too_large",
            },
        )

    return resolved_from, resolved_to


def _resolve_summary_window(*, date_from: datetime | None, date_to: datetime | None) -> tuple[datetime, datetime]:
    normalized_date_to = _as_utc(date_to) or datetime.now(UTC)
    normalized_date_from = _as_utc(date_from) or (normalized_date_to - timedelta(days=30))
    if normalized_date_from > normalized_date_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "date_from must be less than or equal to date_to.",
                "reason_code": "invalid_date_range",
            },
        )
    return normalized_date_from, normalized_date_to


def _organization_or_404(db: Session, organization_id: str) -> Organization:
    org = db.query(Organization).filter(Organization.id == organization_id).first()
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


def _resolve_report_trend_window(
    *,
    date_from: datetime | None,
    date_to: datetime | None,
    summary_date_to: datetime,
) -> tuple[date, date]:
    if date_from is None and date_to is None:
        trend_to = summary_date_to.date()
        trend_from = trend_to - timedelta(days=89)
        return trend_from, trend_to
    normalized_from = _as_utc(date_from)
    normalized_to = _as_utc(date_to)
    return _resolve_trend_window(
        date_from=normalized_from.date() if normalized_from is not None else None,
        date_to=normalized_to.date() if normalized_to is not None else None,
    )
