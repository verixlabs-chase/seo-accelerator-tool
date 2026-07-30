from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.cost_economics import CostLedgerEntry, OrganizationCostAllocation, ProviderPriceCard
from app.models.organization import Organization


MONEY = Decimal("0.00000001")
DISPLAY_MONEY = Decimal("0.01")
ONE_MILLION = Decimal("1000000")


@dataclass(frozen=True)
class PlanEconomics:
    code: str
    name: str
    monthly_revenue: Decimal
    initial_api_budget_percent: Decimal = Decimal("0.05")
    maximum_api_budget_percent: Decimal = Decimal("0.05")
    non_api_reserve_percent: Decimal = Decimal("0.10")
    gross_margin_floor_percent: Decimal = Decimal("0.85")
    version: str = "public-pricing-2026-07-30-v3"

    @property
    def initial_api_budget(self) -> Decimal:
        return _money(self.monthly_revenue * self.initial_api_budget_percent)


PLAN_ECONOMICS: dict[str, PlanEconomics] = {
    "solo": PlanEconomics(code="solo", name="Solo", monthly_revenue=Decimal("299.00")),
    "multi_location": PlanEconomics(
        code="multi_location",
        name="Multi-location",
        monthly_revenue=Decimal("699.00"),
    ),
    "enterprise": PlanEconomics(
        code="enterprise",
        name="Enterprise",
        monthly_revenue=Decimal("1999.00"),
    ),
}

PLAN_ALIASES = {
    "standard": "solo",
    "solo": "solo",
    "pro": "multi_location",
    "multi-location": "multi_location",
    "multi_location": "multi_location",
    "enterprise": "enterprise",
    "internal_anchor": "enterprise",
}


class CostEconomicsError(RuntimeError):
    def __init__(self, message: str, *, reason_code: str, status_code: int) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


class CostAllowanceExceeded(CostEconomicsError):
    def __init__(
        self,
        *,
        budget: Decimal,
        current_exposure: Decimal,
        requested_cost: Decimal,
    ) -> None:
        super().__init__(
            "This paid data request would exceed the organization's monthly provider allowance.",
            reason_code="platform_provider_allowance_exhausted",
            status_code=402,
        )
        self.budget = budget
        self.current_exposure = current_exposure
        self.requested_cost = requested_cost


def resolve_plan_economics(plan_type: str) -> PlanEconomics:
    normalized = PLAN_ALIASES.get((plan_type or "").strip().lower())
    if normalized is None:
        raise CostEconomicsError(
            f"No economics policy is configured for plan '{plan_type}'.",
            reason_code="plan_economics_missing",
            status_code=409,
        )
    return PLAN_ECONOMICS[normalized]


def reserve_provider_cost(
    db: Session,
    *,
    organization_id: str,
    provider_name: str,
    capability: str,
    operation: str,
    credential_owner: str,
    quantity: Decimal | int | float | str,
    idempotency_key: str,
    business_location_id: str | None = None,
    campaign_id: str | None = None,
    model_name: str | None = None,
    input_tokens: int | None = None,
    cached_input_tokens: int | None = None,
    output_tokens: int | None = None,
    now: datetime | None = None,
) -> CostLedgerEntry:
    if credential_owner not in {"platform", "organization"}:
        raise CostEconomicsError(
            "credential_owner must be platform or organization.",
            reason_code="invalid_credential_owner",
            status_code=400,
        )

    existing = (
        db.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.organization_id == organization_id,
            CostLedgerEntry.idempotency_key == idempotency_key,
            CostLedgerEntry.event_type == "reservation",
        )
        .first()
    )
    if existing is not None:
        return existing

    occurred_at = _as_utc(now or datetime.now(UTC))
    org = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .with_for_update()
        .first()
    )
    if org is None:
        raise CostEconomicsError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    plan = resolve_plan_economics(org.plan_type)
    price_card = _find_price_card(
        db,
        provider_name=provider_name,
        capability=capability,
        operation=operation,
        model_name=model_name,
        now=occurred_at,
    )
    normalized_quantity = Decimal(str(quantity))
    estimated_cost = _estimate_cost(
        price_card,
        quantity=normalized_quantity,
        input_tokens=input_tokens,
        cached_input_tokens=cached_input_tokens,
        output_tokens=output_tokens,
    )
    budget_impact = estimated_cost if credential_owner == "platform" else Decimal("0")

    if credential_owner == "platform":
        period_start, period_end = period_bounds(occurred_at)
        current_exposure = _platform_exposure(
            db,
            organization_id=organization_id,
            period_start=period_start,
            period_end=period_end,
        )
        if current_exposure + budget_impact > plan.initial_api_budget:
            raise CostAllowanceExceeded(
                budget=plan.initial_api_budget,
                current_exposure=current_exposure,
                requested_cost=budget_impact,
            )

    row = CostLedgerEntry(
        organization_id=organization_id,
        business_location_id=business_location_id,
        campaign_id=campaign_id,
        provider_name=provider_name,
        capability=capability,
        operation=operation,
        credential_owner=credential_owner,
        quantity=normalized_quantity,
        unit=price_card.unit,
        estimated_cost=estimated_cost,
        provider_reported_cost=None,
        budget_impact_cost=budget_impact,
        currency=price_card.currency,
        status="reserved",
        event_type="reservation",
        idempotency_key=idempotency_key,
        reservation_id=None,
        price_card_version=price_card.version,
        plan_code=plan.code,
        plan_revenue_snapshot=plan.monthly_revenue,
        model_name=model_name,
        input_tokens=_nonnegative_int(input_tokens),
        cached_input_tokens=_nonnegative_int(cached_input_tokens),
        output_tokens=_nonnegative_int(output_tokens),
        created_at=occurred_at,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = (
            db.query(CostLedgerEntry)
            .filter(
                CostLedgerEntry.organization_id == organization_id,
                CostLedgerEntry.idempotency_key == idempotency_key,
                CostLedgerEntry.event_type == "reservation",
            )
            .first()
        )
        if concurrent is not None:
            return concurrent
        raise
    db.refresh(row)
    return row


def reconcile_provider_cost(
    db: Session,
    *,
    reservation: CostLedgerEntry | str,
    provider_reported_cost: Decimal | int | float | str | None,
    now: datetime | None = None,
) -> CostLedgerEntry:
    reservation_row = _reservation_or_error(db, reservation)
    existing = _terminal_event(db, reservation_row, "reconciliation")
    if existing is not None:
        return existing
    occurred_at = _as_utc(now or datetime.now(UTC))
    actual_cost = (
        _money(Decimal(str(provider_reported_cost)))
        if provider_reported_cost is not None
        else _money(Decimal(reservation_row.estimated_cost))
    )
    if actual_cost < 0:
        raise CostEconomicsError(
            "Provider-reported cost cannot be negative.",
            reason_code="invalid_provider_reported_cost",
            status_code=400,
        )
    estimated = Decimal(reservation_row.estimated_cost)
    budget_delta = (
        _money(actual_cost - estimated)
        if reservation_row.credential_owner == "platform"
        else Decimal("0")
    )
    row = _terminal_ledger_event(
        reservation_row,
        event_type="reconciliation",
        status="reconciled",
        provider_reported_cost=actual_cost,
        budget_impact_cost=budget_delta,
        occurred_at=occurred_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def release_provider_cost(
    db: Session,
    *,
    reservation: CostLedgerEntry | str,
    now: datetime | None = None,
) -> CostLedgerEntry:
    reservation_row = _reservation_or_error(db, reservation)
    reconciliation = _terminal_event(db, reservation_row, "reconciliation")
    if reconciliation is not None:
        return reconciliation
    existing = _terminal_event(db, reservation_row, "release")
    if existing is not None:
        return existing
    occurred_at = _as_utc(now or datetime.now(UTC))
    budget_delta = (
        _money(-Decimal(reservation_row.estimated_cost))
        if reservation_row.credential_owner == "platform"
        else Decimal("0")
    )
    row = _terminal_ledger_event(
        reservation_row,
        event_type="release",
        status="released",
        provider_reported_cost=None,
        budget_impact_cost=budget_delta,
        occurred_at=occurred_at,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_allowance_summary(
    db: Session,
    *,
    organization_id: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    occurred_at = _as_utc(now or datetime.now(UTC))
    org = db.get(Organization, organization_id)
    if org is None:
        raise CostEconomicsError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    plan = resolve_plan_economics(org.plan_type)
    period_start, period_end = period_bounds(occurred_at)
    exposure = _platform_exposure(
        db,
        organization_id=organization_id,
        period_start=period_start,
        period_end=period_end,
    )
    realized = (
        db.query(func.coalesce(func.sum(CostLedgerEntry.provider_reported_cost), 0))
        .filter(
            CostLedgerEntry.organization_id == organization_id,
            CostLedgerEntry.credential_owner == "platform",
            CostLedgerEntry.event_type == "reconciliation",
            CostLedgerEntry.created_at >= period_start,
            CostLedgerEntry.created_at < period_end,
        )
        .scalar()
    )
    realized_cost = _money(Decimal(str(realized or 0)))
    reserved_cost = _money(max(Decimal("0"), exposure - realized_cost))
    remaining = _money(max(Decimal("0"), plan.initial_api_budget - exposure))
    percent = (
        (exposure / plan.initial_api_budget * Decimal("100")).quantize(Decimal("0.1"))
        if plan.initial_api_budget > 0
        else Decimal("100.0")
    )
    warning_level = _warning_level(percent)
    org_owned_operations = (
        db.query(func.count(CostLedgerEntry.id))
        .filter(
            CostLedgerEntry.organization_id == organization_id,
            CostLedgerEntry.credential_owner == "organization",
            CostLedgerEntry.event_type == "reservation",
            CostLedgerEntry.created_at >= period_start,
            CostLedgerEntry.created_at < period_end,
        )
        .scalar()
    )
    return {
        "plan": {
            "code": plan.code,
            "name": plan.name,
            "economics_version": plan.version,
        },
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "allowance": {
            "currency": "USD",
            "monthly": _float_money(plan.initial_api_budget),
            "used": _float_money(realized_cost),
            "reserved": _float_money(reserved_cost),
            "remaining": _float_money(remaining),
            "percent_committed": float(percent),
            "warning_level": warning_level,
            "blocked": exposure >= plan.initial_api_budget,
        },
        "organization_owned_operations": int(org_owned_operations or 0),
        "recovery_actions": _recovery_actions(warning_level),
    }


def record_monthly_allocation(
    db: Session,
    *,
    organization_id: str,
    period: datetime,
    created_by_user_id: str | None,
    revenue_override: Decimal | int | float | str | None = None,
    hosting_cost: Decimal | int | float | str = 0,
    storage_cost: Decimal | int | float | str = 0,
    email_cost: Decimal | int | float | str = 0,
    support_cost: Decimal | int | float | str = 0,
    other_cost: Decimal | int | float | str = 0,
    source: str = "operator",
) -> OrganizationCostAllocation:
    if db.get(Organization, organization_id) is None:
        raise CostEconomicsError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    period_start, period_end = period_bounds(period)
    latest_version = (
        db.query(func.max(OrganizationCostAllocation.version))
        .filter(
            OrganizationCostAllocation.organization_id == organization_id,
            OrganizationCostAllocation.period_start == period_start,
        )
        .scalar()
    )
    values = {
        "hosting_cost": _nonnegative_money(hosting_cost, "hosting_cost"),
        "storage_cost": _nonnegative_money(storage_cost, "storage_cost"),
        "email_cost": _nonnegative_money(email_cost, "email_cost"),
        "support_cost": _nonnegative_money(support_cost, "support_cost"),
        "other_cost": _nonnegative_money(other_cost, "other_cost"),
    }
    normalized_revenue = (
        _nonnegative_money(revenue_override, "revenue_override")
        if revenue_override is not None
        else None
    )
    row = OrganizationCostAllocation(
        organization_id=organization_id,
        period_start=period_start,
        period_end=period_end,
        version=int(latest_version or 0) + 1,
        revenue_override=normalized_revenue,
        currency="USD",
        source=source.strip() or "operator",
        created_by_user_id=created_by_user_id,
        **values,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_margin_report(
    db: Session,
    *,
    organization_id: str,
    period: datetime | None = None,
) -> dict[str, Any]:
    org = db.get(Organization, organization_id)
    if org is None:
        raise CostEconomicsError(
            "Organization not found.",
            reason_code="organization_not_found",
            status_code=404,
        )
    plan = resolve_plan_economics(org.plan_type)
    period_start, period_end = period_bounds(period or datetime.now(UTC))
    plan_snapshot = (
        db.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.organization_id == organization_id,
            CostLedgerEntry.event_type == "reservation",
            CostLedgerEntry.created_at >= period_start,
            CostLedgerEntry.created_at < period_end,
        )
        .order_by(CostLedgerEntry.created_at.asc())
        .first()
    )
    if plan_snapshot is not None and plan_snapshot.plan_code in PLAN_ECONOMICS:
        plan = PLAN_ECONOMICS[plan_snapshot.plan_code]
        plan_revenue_snapshot = Decimal(plan_snapshot.plan_revenue_snapshot)
    else:
        plan_revenue_snapshot = plan.monthly_revenue
    allocation = (
        db.query(OrganizationCostAllocation)
        .filter(
            OrganizationCostAllocation.organization_id == organization_id,
            OrganizationCostAllocation.period_start == period_start,
        )
        .order_by(OrganizationCostAllocation.version.desc())
        .first()
    )
    allowance = get_allowance_summary(db, organization_id=organization_id, now=period_start)
    api_cost = Decimal(str(allowance["allowance"]["used"]))
    reserved_api_cost = Decimal(str(allowance["allowance"]["reserved"]))
    revenue = (
        Decimal(allocation.revenue_override)
        if allocation and allocation.revenue_override is not None
        else plan_revenue_snapshot
    )
    category_costs = {
        "hosting": Decimal(allocation.hosting_cost) if allocation else Decimal("0"),
        "storage": Decimal(allocation.storage_cost) if allocation else Decimal("0"),
        "email": Decimal(allocation.email_cost) if allocation else Decimal("0"),
        "support": Decimal(allocation.support_cost) if allocation else Decimal("0"),
        "other": Decimal(allocation.other_cost) if allocation else Decimal("0"),
    }
    non_api_cost = sum(category_costs.values(), Decimal("0"))
    total_cogs = api_cost + non_api_cost
    gross_profit = revenue - total_cogs
    gross_margin_percent = (
        (gross_profit / revenue * Decimal("100")).quantize(Decimal("0.1"))
        if revenue > 0
        else Decimal("0")
    )
    reserved_non_api = _money(plan.monthly_revenue * plan.non_api_reserve_percent)
    heavy_api = _money(plan.monthly_revenue * plan.maximum_api_budget_percent)
    modeled_margin = (
        (plan.monthly_revenue - heavy_api - reserved_non_api)
        / plan.monthly_revenue
        * Decimal("100")
    ).quantize(Decimal("0.1"))
    return {
        "organization": {
            "id": org.id,
            "name": org.name,
            "plan_code": plan.code,
            "plan_name": plan.name,
        },
        "period": {
            "start": period_start.isoformat(),
            "end": period_end.isoformat(),
        },
        "currency": "USD",
        "economics_version": plan.version,
        "allocation_version": allocation.version if allocation else None,
        "allocation_status": "configured" if allocation else "not_configured",
        "revenue": _float_money(revenue),
        "platform_api_cost": _float_money(api_cost),
        "reserved_platform_api_cost": _float_money(reserved_api_cost),
        "costs": {key: _float_money(value) for key, value in category_costs.items()},
        "total_cogs": _float_money(total_cogs),
        "gross_profit": _float_money(gross_profit),
        "gross_margin_percent": float(gross_margin_percent),
        "modeled_heavy_use": {
            "platform_api_cost": _float_money(heavy_api),
            "reserved_non_api_cogs": _float_money(reserved_non_api),
            "gross_margin_percent": float(modeled_margin),
            "margin_floor_percent": float(plan.gross_margin_floor_percent * 100),
            "publishable": modeled_margin >= plan.gross_margin_floor_percent * 100,
        },
    }


def list_tier_margin_models() -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    for plan in PLAN_ECONOMICS.values():
        initial_api = plan.initial_api_budget
        maximum_api = _money(plan.monthly_revenue * plan.maximum_api_budget_percent)
        other_reserve = _money(plan.monthly_revenue * plan.non_api_reserve_percent)
        heavy_margin = (
            (plan.monthly_revenue - maximum_api - other_reserve)
            / plan.monthly_revenue
            * Decimal("100")
        ).quantize(Decimal("0.1"))
        models.append(
            {
                "code": plan.code,
                "name": plan.name,
                "economics_version": plan.version,
                "monthly_revenue": _float_money(plan.monthly_revenue),
                "initial_api_budget": _float_money(initial_api),
                "maximum_api_budget": _float_money(maximum_api),
                "reserved_non_api_cogs": _float_money(other_reserve),
                "heavy_use_margin_percent": float(heavy_margin),
                "margin_floor_percent": float(plan.gross_margin_floor_percent * 100),
                "publishable": heavy_margin >= plan.gross_margin_floor_percent * 100,
            }
        )
    return models


def period_bounds(value: datetime) -> tuple[datetime, datetime]:
    normalized = _as_utc(value)
    start = normalized.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _find_price_card(
    db: Session,
    *,
    provider_name: str,
    capability: str,
    operation: str,
    model_name: str | None,
    now: datetime,
) -> ProviderPriceCard:
    row = (
        db.query(ProviderPriceCard)
        .filter(
            ProviderPriceCard.provider_name == provider_name,
            ProviderPriceCard.capability == capability,
            ProviderPriceCard.operation == operation,
            ProviderPriceCard.model_name == (model_name or ""),
            ProviderPriceCard.active.is_(True),
            ProviderPriceCard.effective_from <= now,
            (ProviderPriceCard.effective_to.is_(None) | (ProviderPriceCard.effective_to > now)),
        )
        .order_by(ProviderPriceCard.effective_from.desc(), ProviderPriceCard.created_at.desc())
        .first()
    )
    if row is None:
        raise CostEconomicsError(
            f"No active price card exists for {provider_name}/{capability}/{operation}.",
            reason_code="provider_price_card_missing",
            status_code=409,
        )
    return row


def _estimate_cost(
    price_card: ProviderPriceCard,
    *,
    quantity: Decimal,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
) -> Decimal:
    if quantity < 0:
        raise CostEconomicsError(
            "Usage quantity cannot be negative.",
            reason_code="invalid_usage_quantity",
            status_code=400,
        )
    total = Decimal(price_card.unit_cost) * quantity
    token_fields = (
        (input_tokens, price_card.input_token_cost_per_million),
        (cached_input_tokens, price_card.cached_input_token_cost_per_million),
        (output_tokens, price_card.output_token_cost_per_million),
    )
    for token_count, price in token_fields:
        normalized_count = _nonnegative_int(token_count)
        if normalized_count and price is None:
            raise CostEconomicsError(
                "The active model price card is missing a requested token price.",
                reason_code="model_token_price_missing",
                status_code=409,
            )
        if normalized_count and price is not None:
            total += Decimal(normalized_count) / ONE_MILLION * Decimal(price)
    return _money(total)


def _platform_exposure(
    db: Session,
    *,
    organization_id: str,
    period_start: datetime,
    period_end: datetime,
) -> Decimal:
    value = (
        db.query(func.coalesce(func.sum(CostLedgerEntry.budget_impact_cost), 0))
        .filter(
            CostLedgerEntry.organization_id == organization_id,
            CostLedgerEntry.credential_owner == "platform",
            CostLedgerEntry.created_at >= period_start,
            CostLedgerEntry.created_at < period_end,
        )
        .scalar()
    )
    return _money(Decimal(str(value or 0)))


def _reservation_or_error(db: Session, reservation: CostLedgerEntry | str) -> CostLedgerEntry:
    row = reservation if isinstance(reservation, CostLedgerEntry) else db.get(CostLedgerEntry, reservation)
    if row is None or row.event_type != "reservation":
        raise CostEconomicsError(
            "Cost reservation not found.",
            reason_code="cost_reservation_not_found",
            status_code=404,
        )
    return row


def _terminal_event(
    db: Session,
    reservation: CostLedgerEntry,
    event_type: str,
) -> CostLedgerEntry | None:
    return (
        db.query(CostLedgerEntry)
        .filter(
            CostLedgerEntry.organization_id == reservation.organization_id,
            CostLedgerEntry.idempotency_key == reservation.idempotency_key,
            CostLedgerEntry.event_type == event_type,
        )
        .first()
    )


def _terminal_ledger_event(
    reservation: CostLedgerEntry,
    *,
    event_type: str,
    status: str,
    provider_reported_cost: Decimal | None,
    budget_impact_cost: Decimal,
    occurred_at: datetime,
) -> CostLedgerEntry:
    return CostLedgerEntry(
        organization_id=reservation.organization_id,
        business_location_id=reservation.business_location_id,
        campaign_id=reservation.campaign_id,
        provider_name=reservation.provider_name,
        capability=reservation.capability,
        operation=reservation.operation,
        credential_owner=reservation.credential_owner,
        quantity=reservation.quantity,
        unit=reservation.unit,
        estimated_cost=reservation.estimated_cost,
        provider_reported_cost=provider_reported_cost,
        budget_impact_cost=budget_impact_cost,
        currency=reservation.currency,
        status=status,
        event_type=event_type,
        idempotency_key=reservation.idempotency_key,
        reservation_id=reservation.id,
        price_card_version=reservation.price_card_version,
        plan_code=reservation.plan_code,
        plan_revenue_snapshot=reservation.plan_revenue_snapshot,
        model_name=reservation.model_name,
        input_tokens=reservation.input_tokens,
        cached_input_tokens=reservation.cached_input_tokens,
        output_tokens=reservation.output_tokens,
        reconciled_at=occurred_at,
        created_at=occurred_at,
    )


def _warning_level(percent: Decimal) -> int | None:
    for threshold in (90, 75, 50):
        if percent >= threshold:
            return threshold
    return None


def _recovery_actions(warning_level: int | None) -> list[str]:
    if warning_level is None:
        return []
    actions = [
        "Wait until the monthly allowance resets before running optional paid checks.",
        "Connect your own provider credentials so those vendor charges do not use the platform allowance.",
    ]
    if warning_level >= 90:
        actions.insert(0, "Use smaller or fewer paid checks for the rest of this month.")
    return actions


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


def _float_money(value: Decimal) -> float:
    return float(value.quantize(DISPLAY_MONEY, rounding=ROUND_HALF_UP))


def _nonnegative_money(value: Decimal | int | float | str, field_name: str) -> Decimal:
    normalized = Decimal(str(value))
    if normalized < 0:
        raise CostEconomicsError(
            f"{field_name} cannot be negative.",
            reason_code="invalid_cost_allocation",
            status_code=400,
        )
    return normalized.quantize(DISPLAY_MONEY, rounding=ROUND_HALF_UP)


def _nonnegative_int(value: int | None) -> int | None:
    if value is None:
        return None
    normalized = int(value)
    if normalized < 0:
        raise CostEconomicsError(
            "Token counts cannot be negative.",
            reason_code="invalid_token_count",
            status_code=400,
        )
    return normalized


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
