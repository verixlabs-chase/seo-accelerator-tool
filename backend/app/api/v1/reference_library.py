from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.api.response import envelope
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.reference_library import (
    AIDecisionContextIn,
    CoreWebVitalsEvaluateIn,
    CruxStandardsCheckIn,
    ReferenceLibraryActivateIn,
    ReferenceLibraryActivationOut,
    ReferenceLibraryActiveOut,
    ReferenceLibraryValidateIn,
    ReferenceLibraryValidationOut,
    ReferenceLibraryVersionOut,
)
from app.intelligence.lexicon.ai_context import build_ai_decision_context
from app.intelligence.lexicon.evaluator import evaluate_core_web_vitals
from app.intelligence.lexicon.loader import get_active_lexicon
from app.intelligence.lexicon.standards import (
    latest_crux_standards_check,
    run_and_record_crux_standards_check,
)
from app.services import reference_library_service

router = APIRouter(prefix="/reference-library", tags=["reference-library"])


def _ensure_loader_enabled() -> None:
    if not get_settings().reference_library_loader_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Reference library loader is disabled"
        )


@router.post("/validate")
def validate_reference_library(
    request: Request,
    body: ReferenceLibraryValidateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.validate_version(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        version=body.version,
        artifacts=body.artifacts,
        strict_mode=body.strict_mode,
    )
    return envelope(
        request, ReferenceLibraryValidationOut.model_validate(result).model_dump(mode="json")
    )


@router.post("/activate")
def activate_reference_library(
    request: Request,
    body: ReferenceLibraryActivateIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.activate_version(
        db,
        tenant_id=user["tenant_id"],
        actor_user_id=user["id"],
        version=body.version,
        reason=body.reason,
    )
    return envelope(
        request, ReferenceLibraryActivationOut.model_validate(result).model_dump(mode="json")
    )


@router.get("/versions")
def list_reference_library_versions(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    rows = reference_library_service.list_versions(db, tenant_id=user["tenant_id"])
    return envelope(
        request,
        {
            "items": [
                ReferenceLibraryVersionOut.model_validate(row).model_dump(mode="json")
                for row in rows
            ]
        },
    )


@router.get("/active")
def get_active_reference_library(
    request: Request,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    result = reference_library_service.get_active(db, tenant_id=user["tenant_id"])
    return envelope(
        request, ReferenceLibraryActiveOut.model_validate(result).model_dump(mode="json")
    )


@router.get("/lexicon")
def get_intelligence_lexicon(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    return envelope(request, lexicon.model_dump(mode="json"))


@router.post("/core-web-vitals/evaluate")
def evaluate_current_core_web_vitals(
    request: Request,
    body: CoreWebVitalsEvaluateIn,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    result = evaluate_core_web_vitals(
        lexicon,
        body.measurements,
        form_factor=body.form_factor,
        collection_period_days=body.collection_period_days,
        measured_at=body.measured_at,
        source=body.source,
    )
    return envelope(request, result)


@router.post("/core-web-vitals/standards/check")
def check_current_core_web_vitals_standard(
    request: Request,
    body: CruxStandardsCheckIn,
    user: dict = Depends(require_roles({"platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    settings = get_settings()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    try:
        result = run_and_record_crux_standards_check(
            db,
            lexicon=lexicon,
            api_key=settings.crux_api_key,
            origin=body.origin or settings.cwv_standards_probe_origin,
            timeout_seconds=settings.google_oauth_http_timeout_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Unable to verify Core Web Vitals standards with the official CrUX API.",
        ) from exc
    return envelope(request, result)


@router.get("/core-web-vitals/standards/status")
def get_current_core_web_vitals_standard_status(
    request: Request,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    latest = latest_crux_standards_check(db)
    return envelope(
        request,
        {
            "lexicon_version": lexicon.meta.version,
            "standards_reviewed_at": lexicon.meta.standards_reviewed_at,
            "latest_check": latest,
            "automatic_activation_allowed": False,
        },
    )


@router.post("/ai-decision-context")
def create_ai_decision_context(
    request: Request,
    body: AIDecisionContextIn,
    user: dict = Depends(require_roles({"tenant_admin", "platform_admin"})),
    db: Session = Depends(get_db),
) -> dict:
    _ensure_loader_enabled()
    lexicon = get_active_lexicon(db, tenant_id=user["tenant_id"])
    result = build_ai_decision_context(
        lexicon,
        facts=body.facts,
        deterministic_assessments=body.deterministic_assessments,
        diagnostic_ids=body.diagnostic_ids,
        action_ids=body.action_ids,
    )
    return envelope(request, result)
