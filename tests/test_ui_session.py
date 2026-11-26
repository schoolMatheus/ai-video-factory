"""Local bootstrap secret, same-origin session and CSRF protection."""

from pathlib import Path

from ai_video_factory.ui_backend.session import BootstrapService, SessionService


def test_bootstrap_secret_is_single_use(tmp_path: Path) -> None:
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    token = bootstrap.issue()

    assert bootstrap.redeem(token) is True
    assert bootstrap.redeem(token) is False


def test_bootstrap_rejects_wrong_token(tmp_path: Path) -> None:
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    bootstrap.issue()

    assert bootstrap.redeem("wrong-token") is False


def test_session_cookie_is_signed_and_csrf_is_bound(tmp_path: Path) -> None:
    sessions = SessionService(b"test-secret")
    cookie, csrf = sessions.issue()

    session = sessions.verify_cookie(cookie)
    assert session is not None
    assert sessions.verify_csrf(session, csrf) is True
    assert sessions.verify_csrf(session, "other") is False


def test_tampered_cookie_is_rejected() -> None:
    sessions = SessionService(b"test-secret")
    cookie, _ = sessions.issue()

    assert sessions.verify_cookie(cookie + "tampered") is None


def test_bootstrap_token_is_not_written_to_logs(tmp_path: Path, caplog) -> None:
    bootstrap = BootstrapService(tmp_path / "bootstrap.token")
    token = bootstrap.issue()

    with caplog.at_level("DEBUG"):
        bootstrap.redeem(token)

    assert token not in caplog.text
