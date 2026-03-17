from types import SimpleNamespace

from app.models.user import User
from app.services.auth_service import seed_local_admin


def test_seed_local_admin_is_noop_without_explicit_local_opt_in(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth_service.get_settings",
        lambda: SimpleNamespace(app_env="local", local_admin_bootstrap_enabled=False),
    )

    seed_local_admin(db_session)

    user = db_session.query(User).filter(User.email == "admin@local.dev").first()
    assert user is None


def test_seed_local_admin_runs_when_explicitly_enabled_for_local(db_session, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.auth_service.get_settings",
        lambda: SimpleNamespace(app_env="local", local_admin_bootstrap_enabled=True),
    )

    seed_local_admin(db_session)

    user = db_session.query(User).filter(User.email == "admin@local.dev").first()
    assert user is not None
    assert user.platform_role == "platform_admin"
