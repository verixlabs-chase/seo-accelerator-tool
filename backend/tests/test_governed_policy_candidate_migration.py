from pathlib import Path


def test_governed_policy_candidate_migration_is_scoped_and_immutable() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20260814_0152_governed_policy_candidates.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "20260814_0151"' in migration
    assert '"governed_policy_candidates"' in migration
    assert '"governed_policy_replays"' in migration
    assert '"governed_policy_decisions"' in migration
    assert "action_learning_eligibility" in migration
    assert "uq_governed_policy_candidates_tenant_protocol_family" in migration
    assert "uq_governed_policy_decisions_tenant_candidate" in migration
    assert "ordered_measurement_ids" in migration
    assert "cumulative_results" in migration
    assert "approved_for_future_activation" in migration
    assert migration.count("automatic_activation_allowed") >= 6
    assert migration.count("automatic_activation_allowed = false") == 3
    assert "GRANT SELECT, INSERT" in migration
    assert "REVOKE UPDATE, DELETE" in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "app.current_tenant_id" in migration
    assert "app.current_organization_id" in migration
    assert "BEFORE UPDATE OR DELETE" in migration
    assert "app.platform_maintenance" in migration
    assert "append-only and immutable" in migration
