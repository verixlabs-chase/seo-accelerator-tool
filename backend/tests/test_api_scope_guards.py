from fastapi import HTTPException

from app.api.deps import enforce_organization_scope


def test_enforce_organization_scope_allows_matching_org_context() -> None:
    user = {"organization_id": "org-1", "platform_role": None}
    enforce_organization_scope(user=user, organization_id="org-1")


def test_enforce_organization_scope_allows_platform_context() -> None:
    user = {"organization_id": None, "platform_role": "platform_admin"}
    enforce_organization_scope(user=user, organization_id="org-1")


def test_enforce_organization_scope_rejects_cross_org_context() -> None:
    user = {"organization_id": "org-2", "platform_role": None}
    try:
        enforce_organization_scope(user=user, organization_id="org-1")
    except HTTPException as exc:
        assert exc.status_code == 403
        assert exc.detail["reason_code"] == "organization_scope_mismatch"
    else:
        raise AssertionError("Expected cross-org access to be rejected")
