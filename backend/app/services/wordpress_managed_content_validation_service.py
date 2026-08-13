from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from app.models.campaign import Campaign
from app.models.recommendation_execution import RecommendationExecution
from app.services import business_service_area_service, business_service_service
from app.services.wordpress_content_inventory_service import (
    get_wordpress_content_inventory,
)


VALIDATOR_VERSION = "wordpress-managed-content-v1"
INVENTORY_MAX_AGE = timedelta(hours=24)
ACTION_CONTRACTS: dict[str, frozenset[str]] = {
    "create_content_brief": frozenset({"publish_content_page"}),
    "fix_missing_title": frozenset(
        {"update_meta_title", "update_meta_description"}
    ),
    "improve_internal_links": frozenset(
        {"insert_internal_link", "create_internal_anchor"}
    ),
    "publish_schema_markup": frozenset({"add_schema_markup"}),
}
ALLOWED_SCHEMA_TYPES = frozenset(
    {
        "Service",
        "LocalBusiness",
        "ProfessionalService",
        "HomeAndConstructionBusiness",
        "Electrician",
        "GeneralContractor",
        "HousePainter",
        "HVACBusiness",
        "Locksmith",
        "MovingCompany",
        "Plumber",
        "RoofingContractor",
    }
)
UNVERIFIED_BUSINESS_PHRASES = (
    "award-winning",
    "best in",
    "cheapest",
    "family-owned",
    "free estimate",
    "guaranteed",
    "licensed and insured",
    "licensed & insured",
    "same-day",
    "top-rated",
    "years of experience",
)
UNSUPPORTED_OUTCOME_PHRASES = (
    "will rank",
    "increase traffic",
    "increase leads",
    "increase revenue",
    "more customers guaranteed",
    "proves that",
    "definitely caused",
)
GENERIC_ANCHORS = frozenset(
    {"click here", "learn more", "read more", "here", "website"}
)
UNSAFE_TEXT_PATTERN = re.compile(
    r"<\s*script\b|javascript\s*:|data\s*:\s*text/html|on(?:error|load)\s*=",
    re.IGNORECASE,
)
UNVERIFIED_NUMBER_PATTERN = re.compile(
    r"(?:\b\d+(?:\.\d+)?%|\$\s*\d|\b\d+\+?\s+(?:years?|customers?|jobs?|reviews?)\b)",
    re.IGNORECASE,
)


def validate_managed_wordpress_changes(
    db: Session,
    *,
    execution: RecommendationExecution,
    mutations: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = _load_payload(execution.execution_payload)
    if payload.get("managed_wordpress_automation") is not True:
        return {
            "required": False,
            "status": "not_required",
            "validator_version": VALIDATOR_VERSION,
            "checks": [],
            "blocking_issues": [],
            "traceability": {
                "execution_id": execution.id,
                "recommendation_id": execution.recommendation_id,
                "generation_mode": "manual_approval",
            },
        }

    campaign = db.get(Campaign, execution.campaign_id)
    issues: list[dict[str, str]] = []
    check_results: list[dict[str, Any]] = []
    traceability: dict[str, Any] = {
        "execution_id": execution.id,
        "recommendation_id": execution.recommendation_id,
        "campaign_id": execution.campaign_id,
        "execution_type": execution.execution_type,
        "automation_policy_version": payload.get("automation_policy_version"),
        "generation_mode": "deterministic",
        "model_run_id": None,
        "confirmed_service_ids": [],
        "confirmed_service_area_ids": [],
        "content_sync_run_id": None,
    }
    if campaign is None or campaign.tenant_id != str(payload.get("tenant_id") or ""):
        _issue(
            issues,
            "wordpress_content_scope_invalid",
            "The saved website update no longer matches this business.",
        )
        return _report(issues, check_results, traceability)

    _check_action_contract(execution.execution_type, mutations, issues)
    _add_check(
        check_results,
        "action_contract",
        not any(item["code"] == "wordpress_action_contract_invalid" for item in issues),
        "Every proposed field matches the allowed action contract.",
    )

    text_values = _content_text_values(mutations)
    combined_text = " ".join(text_values)
    _check_proposed_text(text_values, issues, confirmed_business_name=campaign.name)
    _check_field_shapes(campaign, mutations, issues)
    _add_check(
        check_results,
        "wording_and_field_safety",
        not any(
            item["code"]
            in {
                "wordpress_content_unsafe_text",
                "wordpress_content_unverified_claim",
                "wordpress_content_field_invalid",
                "wordpress_link_target_invalid",
                "wordpress_schema_invalid",
            }
            for item in issues
        ),
        "Wording, links, metadata, and structured data passed deterministic checks.",
    )

    services = business_service_service.confirmed_services_for_campaign(
        db,
        tenant_id=campaign.tenant_id,
        campaign_id=campaign.id,
    )
    included_areas, excluded_areas = (
        business_service_area_service.confirmed_areas_for_campaign(
            db,
            tenant_id=campaign.tenant_id,
            campaign_id=campaign.id,
        )
    )
    traceability["confirmed_service_ids"] = [row.id for row in services]
    traceability["confirmed_service_area_ids"] = [row.id for row in included_areas]
    if execution.execution_type == "create_content_brief":
        matched_service, service_score = business_service_service.match_keyword_to_service(
            combined_text,
            services,
        )
        if matched_service is None or service_score < 0.75:
            _issue(
                issues,
                "wordpress_confirmed_service_required",
                "Confirm the service this page describes before InsightOS can create it automatically.",
            )
        else:
            traceability["matched_service_id"] = matched_service.id
            traceability["matched_service_score"] = round(service_score, 2)

    normalized_combined = _normalize_text(combined_text)
    excluded_match = next(
        (
            area
            for area in excluded_areas
            if re.search(
                rf"\b{re.escape(_normalize_text(area.name))}\b",
                normalized_combined,
            )
        ),
        None,
    )
    if excluded_match is not None:
        _issue(
            issues,
            "wordpress_excluded_service_area",
            "The proposed wording names an area this location does not serve.",
        )
        traceability["excluded_service_area_id"] = excluded_match.id
    _add_check(
        check_results,
        "confirmed_business_facts",
        not any(
            item["code"]
            in {
                "wordpress_confirmed_service_required",
                "wordpress_excluded_service_area",
                "wordpress_content_unverified_claim",
            }
            for item in issues
        ),
        "The proposal stays within owner-confirmed business information.",
    )

    if execution.execution_type == "create_content_brief":
        inventory = get_wordpress_content_inventory(db, campaign=campaign, limit=500)
        traceability["content_sync_run_id"] = inventory.get("sync_run_id")
        traceability["content_inventory_synced_at"] = inventory.get("last_synced_at")
        _check_duplicate_page(mutations, inventory, issues)
        _add_check(
            check_results,
            "duplicate_content",
            not any(
                item["code"]
                in {
                    "wordpress_content_inventory_required",
                    "wordpress_content_inventory_incomplete",
                    "wordpress_content_inventory_stale",
                    "wordpress_duplicate_page",
                }
                for item in issues
            ),
            "The latest WordPress inventory found no matching page or address.",
        )

    return _report(issues, check_results, traceability)


def _check_action_contract(
    execution_type: str,
    mutations: list[dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    expected = ACTION_CONTRACTS.get(execution_type, frozenset())
    observed = [str(item.get("action") or "") for item in mutations]
    if not expected or set(observed) != set(expected) or len(observed) != len(expected):
        _issue(
            issues,
            "wordpress_action_contract_invalid",
            "The proposed website fields do not match this approved action type.",
        )


def _check_proposed_text(
    values: list[str],
    issues: list[dict[str, str]],
    *,
    confirmed_business_name: str,
) -> None:
    combined = " ".join(values)
    claim_text = re.sub(
        re.escape(confirmed_business_name.strip()),
        " ",
        combined,
        flags=re.IGNORECASE,
    ) if confirmed_business_name.strip() else combined
    lowered = claim_text.lower()
    if UNSAFE_TEXT_PATTERN.search(combined):
        _issue(
            issues,
            "wordpress_content_unsafe_text",
            "The proposed wording contains code or markup that cannot run automatically.",
        )
    unsupported = next(
        (
            phrase
            for phrase in (*UNVERIFIED_BUSINESS_PHRASES, *UNSUPPORTED_OUTCOME_PHRASES)
            if phrase in lowered
        ),
        None,
    )
    if unsupported or UNVERIFIED_NUMBER_PATTERN.search(claim_text):
        _issue(
            issues,
            "wordpress_content_unverified_claim",
            "The proposed wording includes a business or performance claim that is not confirmed in the saved facts.",
        )


def _check_field_shapes(
    campaign: Campaign,
    mutations: list[dict[str, Any]],
    issues: list[dict[str, str]],
) -> None:
    expected_host = _host(campaign.domain)
    for mutation in mutations:
        action = str(mutation.get("action") or "")
        payload = mutation.get("payload")
        if not isinstance(payload, dict):
            _issue(
                issues,
                "wordpress_content_field_invalid",
                "A proposed website field is missing its value.",
            )
            continue
        if action == "update_meta_title":
            _bounded_text(payload.get("title"), 1, 70, issues)
        elif action == "update_meta_description":
            _bounded_text(payload.get("description"), 1, 180, issues)
        elif action == "publish_content_page":
            _check_draft_page(payload, issues)
        elif action in {"insert_internal_link", "create_internal_anchor"}:
            _check_internal_link(action, payload, expected_host, issues)
        elif action == "add_schema_markup":
            _check_schema(payload, campaign, expected_host, issues)


def _bounded_text(
    value: Any,
    minimum: int,
    maximum: int,
    issues: list[dict[str, str]],
) -> None:
    length = len(str(value or "").strip())
    if length < minimum or length > maximum:
        _issue(
            issues,
            "wordpress_content_field_invalid",
            "A proposed title, description, or label is outside the allowed length.",
        )


def _check_draft_page(
    payload: dict[str, Any],
    issues: list[dict[str, str]],
) -> None:
    _bounded_text(payload.get("title"), 1, 100, issues)
    slug = str(payload.get("slug") or "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        _issue(
            issues,
            "wordpress_content_field_invalid",
            "The proposed draft has an invalid page address.",
        )
    if payload.get("publication_state") != "draft":
        _issue(
            issues,
            "wordpress_content_field_invalid",
            "Managed content must begin as a draft.",
        )
    blocks = payload.get("content_blocks")
    if not isinstance(blocks, list) or not blocks or len(blocks) > 24:
        _issue(
            issues,
            "wordpress_content_field_invalid",
            "The proposed draft does not have a supported content structure.",
        )
    else:
        for block in blocks:
            if (
                not isinstance(block, dict)
                or block.get("type") not in {"paragraph", "heading", "list"}
                or len(str(block.get("text") or "")) > 2500
            ):
                _issue(
                    issues,
                    "wordpress_content_field_invalid",
                    "The proposed draft contains an unsupported content block.",
                )
                break
    seo = payload.get("seo")
    if not isinstance(seo, dict):
        _issue(
            issues,
            "wordpress_content_field_invalid",
            "The proposed draft is missing its search title and description.",
        )
    else:
        _bounded_text(seo.get("meta_title"), 1, 70, issues)
        _bounded_text(seo.get("meta_description"), 1, 180, issues)


def _check_internal_link(
    action: str,
    payload: dict[str, Any],
    expected_host: str,
    issues: list[dict[str, str]],
) -> None:
    anchor = str(payload.get("anchor_text") or "").strip()
    if not 2 <= len(anchor) <= 80 or anchor.lower() in GENERIC_ANCHORS:
        _issue(
            issues,
            "wordpress_content_field_invalid",
            "The proposed link needs a clear, descriptive label.",
        )
    if action == "insert_internal_link":
        target = str(payload.get("target_url") or "")
        parsed = urlsplit(target)
        if not target or (parsed.hostname and _host(parsed.hostname) != expected_host):
            _issue(
                issues,
                "wordpress_link_target_invalid",
                "The proposed internal link points outside the connected website.",
            )


def _check_schema(
    payload: dict[str, Any],
    campaign: Campaign,
    expected_host: str,
    issues: list[dict[str, str]],
) -> None:
    schema_type = str(payload.get("schema_type") or "")
    schema = payload.get("schema_json")
    if (
        schema_type not in ALLOWED_SCHEMA_TYPES
        or not isinstance(schema, dict)
        or schema.get("@context") != "https://schema.org"
        or schema.get("@type") != schema_type
        or str(schema.get("name") or "").strip() != campaign.name.strip()
    ):
        _issue(
            issues,
            "wordpress_schema_invalid",
            "The proposed structured data does not match the saved business and supported schema types.",
        )
        return
    schema_url = str(schema.get("url") or "")
    if not schema_url or (urlsplit(schema_url).hostname and _host(schema_url) != expected_host):
        _issue(
            issues,
            "wordpress_schema_invalid",
            "The structured-data website address does not match the connected business website.",
        )


def _check_duplicate_page(
    mutations: list[dict[str, Any]],
    inventory: dict[str, Any],
    issues: list[dict[str, str]],
) -> None:
    if not inventory.get("has_inventory"):
        _issue(
            issues,
            "wordpress_content_inventory_required",
            "Refresh the WordPress page list before InsightOS creates a page automatically.",
        )
        return
    if inventory.get("truncated"):
        _issue(
            issues,
            "wordpress_content_inventory_incomplete",
            "The saved WordPress page list is incomplete, so duplicate-page safety cannot be confirmed.",
        )
        return
    try:
        synced_at = datetime.fromisoformat(str(inventory.get("last_synced_at") or ""))
    except ValueError:
        synced_at = None
    if synced_at is None or synced_at.tzinfo is None or datetime.now(UTC) - synced_at > INVENTORY_MAX_AGE:
        _issue(
            issues,
            "wordpress_content_inventory_stale",
            "Refresh the WordPress page list before InsightOS creates a page automatically.",
        )
        return
    page_mutation = next(
        (item for item in mutations if item.get("action") == "publish_content_page"),
        None,
    )
    if not isinstance(page_mutation, dict):
        return
    target_path = _path(str(page_mutation.get("target_url") or ""))
    payload = page_mutation.get("payload")
    title = _normalize_text(payload.get("title")) if isinstance(payload, dict) else ""
    slug = _normalize_text(payload.get("slug")) if isinstance(payload, dict) else ""
    for item in inventory.get("items") or []:
        if not isinstance(item, dict):
            continue
        if (
            _path(str(item.get("url") or "")) == target_path
            or (slug and _normalize_text(item.get("slug")) == slug)
            or (title and _normalize_text(item.get("title")) == title)
        ):
            _issue(
                issues,
                "wordpress_duplicate_page",
                "A WordPress page already uses this title or website address.",
            )
            return


def _content_text_values(mutations: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []

    def collect(value: Any, *, key: str = "") -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                collect(child_value, key=str(child_key))
        elif isinstance(value, list):
            for child in value:
                collect(child, key=key)
        elif isinstance(value, str) and key not in {
            "target_url",
            "url",
            "@context",
            "slug",
            "anchor_slug",
            "placement",
        }:
            values.append(value)

    for mutation in mutations:
        collect(mutation.get("payload") or {})
    return values


def _report(
    issues: list[dict[str, str]],
    checks: list[dict[str, Any]],
    traceability: dict[str, Any],
) -> dict[str, Any]:
    unique_issues = list(
        {f"{item['code']}:{item['message']}": item for item in issues}.values()
    )
    return {
        "required": True,
        "status": "blocked" if unique_issues else "passed",
        "validator_version": VALIDATOR_VERSION,
        "checks": checks,
        "blocking_issues": unique_issues,
        "traceability": traceability,
    }


def _add_check(
    checks: list[dict[str, Any]],
    code: str,
    passed: bool,
    message: str,
) -> None:
    checks.append({"code": code, "passed": passed, "message": message})


def _issue(
    issues: list[dict[str, str]],
    code: str,
    message: str,
) -> None:
    issues.append({"code": code, "message": message})


def _load_payload(raw: str | None) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _normalize_text(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _path(value: str) -> str:
    path = urlsplit(value).path or "/"
    return "/" + path.strip("/") if path.strip("/") else "/"


def _host(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    return str(parsed.hostname or "").lower().removeprefix("www.")
