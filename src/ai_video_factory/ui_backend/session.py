"""Local-only bootstrap secret, signed session cookie and CSRF binding.

The bootstrap token is written by the launcher and exchanged exactly once for
a cookie-backed session. It is never logged and never sent in a URL.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path

SESSION_COOKIE = "avf_session"
CSRF_COOKIE = "avf_session_csrf"
CSRF_HEADER = "X-CSRF-Token"
SESSION_TTL_SECONDS = 12 * 3600


@dataclass(frozen=True)
class Session:
    id: str
    csrf: str
    expires_at: float


class BootstrapService:
    """Holds the single-use local bootstrap token on disk."""

    def __init__(self, token_path: Path) -> None:
        self.token_path = Path(token_path)

    def issue(self) -> str:
        token = secrets.token_urlsafe(32)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(token, encoding="ascii")
        try:
            os.chmod(self.token_path, 0o600)
        except OSError:
            # Windows does not expose POSIX permissions; the file is local.
            pass
        return token

    def redeem(self, token: str) -> bool:
        try:
            expected = self.token_path.read_text(encoding="ascii").strip()
        except OSError:
            return False
        if not hmac.compare_digest(expected, token):
            return False
        try:
            self.token_path.unlink()
        except OSError:
            return False
        return True


class SessionService:
    """Signed cookie sessions with an explicit CSRF token per session."""

    def __init__(self, secret: bytes, *, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
        self._secret = secret
        self._ttl = ttl_seconds
        self._sessions: dict[str, Session] = {}

    @classmethod
    def with_persisted_secret(cls, key_path: Path) -> "SessionService":
        key_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            secret = key_path.read_bytes()
        except OSError:
            secret = secrets.token_bytes(32)
            key_path.write_bytes(secret)
        if len(secret) < 32:
            secret = hashlib.sha256(secret).digest()
            key_path.write_bytes(secret)
        return cls(secret)

    def issue(self) -> tuple[str, str]:
        session = Session(
            id=secrets.token_urlsafe(24),
            csrf=secrets.token_urlsafe(24),
            expires_at=time.time() + self._ttl,
        )
        self._sessions[session.id] = session
        signature = hmac.new(
            self._secret, session.id.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return f"{session.id}.{signature}", session.csrf

    def verify_cookie(self, cookie: str | None) -> Session | None:
        if not cookie or "." not in cookie:
            return None
        session_id, signature = cookie.rsplit(".", 1)
        expected = hmac.new(
            self._secret, session_id.encode("ascii", errors="replace"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        session = self._sessions.get(session_id)
        if session is None or session.expires_at <= time.time():
            return None
        return session

    @staticmethod
    def verify_csrf(session: Session, token: str | None) -> bool:
        if not token:
            return False
        return hmac.compare_digest(session.csrf, token)
