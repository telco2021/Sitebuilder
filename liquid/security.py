"""Passwords, sessions, CSRF, headers, and request limits."""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from liquid.config import Settings
from liquid.models import User, utcnow
from liquid.textutil import FormError

log = logging.getLogger("liquid.security")

_BUCKETS: dict[str, list[float]] = {}
_DUMMIES: dict[str, str] = {}
_PASSWORD = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{12,128}$")


def dummy_for(env: str) -> str:
    if env not in _DUMMIES:
        _DUMMIES[env] = hasher_for(env).hash("liquid-not-a-password")
    return _DUMMIES[env]


def hasher_for(env: str) -> PasswordHasher:
    if env == "test":
        return PasswordHasher(time_cost=1, memory_cost=8192, parallelism=1)
    return PasswordHasher()


def hash_password(password: str, env: str) -> str:
    return hasher_for(env).hash(password)


def verify_password(password: str, encoded: str, env: str) -> bool:
    try:
        return hasher_for(env).verify(encoded, password)
    except VerifyMismatchError:
        return False
    except Exception:
        log.info("password verification rejected a malformed hash")
        return False


def validate_password(password: str) -> str:
    if not isinstance(password, str) or not _PASSWORD.fullmatch(password):
        raise FormError("Use 12 to 128 characters with upper case, lower case, and a digit.")
    return password


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    if request.client is None:
        return ""
    return request.client.host[:64]


def rate_limit(key: str, limit: int, window_seconds: int) -> bool:
    now = time.monotonic()
    recent = [stamp for stamp in _BUCKETS.get(key, []) if now - stamp < window_seconds]
    if len(recent) >= limit:
        _BUCKETS[key] = recent
        return False
    recent.append(now)
    _BUCKETS[key] = recent
    return True


def reset_rate_limits() -> None:
    _BUCKETS.clear()


def account_locked(user: User) -> bool:
    locked = aware(user.locked_until)
    return bool(locked and locked > utcnow())


def register_failure(user: User, settings: Settings) -> None:
    user.failed_logins += 1
    if user.failed_logins >= settings.login_max_failures:
        user.locked_until = utcnow() + timedelta(minutes=settings.lock_minutes)


def session_serializer(settings: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.secret_key, salt="liquid-session-v1")


def load_session(raw: str | None, settings: Settings) -> dict:
    if not raw:
        return {"csrf": secrets.token_urlsafe(32)}
    try:
        data = session_serializer(settings).loads(raw, max_age=settings.session_seconds)
    except (BadSignature, SignatureExpired):
        return {"csrf": secrets.token_urlsafe(32)}
    if not isinstance(data, dict) or not isinstance(data.get("csrf"), str):
        return {"csrf": secrets.token_urlsafe(32)}
    return data


def assert_csrf(request: Request, token: object) -> None:
    expected = request.state.session.get("csrf", "")
    supplied = token if isinstance(token, str) else ""
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        from starlette.exceptions import HTTPException

        raise HTTPException(status_code=403, detail="The form expired. Reload the page and try again.")


def rotate_session(request: Request, **values: object) -> None:
    request.state.session.clear()
    request.state.session["csrf"] = secrets.token_urlsafe(32)
    request.state.session.update(values)


class SecurityMiddleware:
    """Signed session cookie and response headers, without reading the body."""

    def __init__(self, app: ASGIApp, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        host = headers.get("host", "").split(":")[0].lower()
        if self.settings.hosts and host not in self.settings.hosts:
            await Response("Host is not allowed.", status_code=400)(scope, receive, send)
            return
        raw_cookie = headers.get("cookie", "")
        token = _cookie_value(raw_cookie, "liquid_session")
        scope.setdefault("state", {})
        scope["state"]["session"] = load_session(token, self.settings)

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                packed = MutableHeaders(raw=list(message.get("headers", [])))
                cookie = _session_cookie(scope["state"]["session"], self.settings)
                packed.append("set-cookie", cookie)
                _security_headers(packed, scope.get("path", ""))
                message["headers"] = packed.raw
            await send(message)

        await self.app(scope, receive, send_with_headers)


def _cookie_value(header: str, name: str) -> str | None:
    prefix = name + "="
    for part in header.split(";"):
        item = part.strip()
        if item.startswith(prefix):
            return item[len(prefix) :]
    return None


def _session_cookie(session: dict, settings: Settings) -> str:
    token = session_serializer(settings).dumps(session)
    response = Response()
    response.set_cookie(
        "liquid_session",
        token,
        max_age=settings.session_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )
    return response.headers["set-cookie"]


_STUDIO_PATH = re.compile(r"^/admin/sites/[0-9]+/pages(?:/new|/[0-9]+)?$")


def _security_headers(headers: MutableHeaders, path: str = "") -> None:
    headers["X-Content-Type-Options"] = "nosniff"
    headers["X-Frame-Options"] = "DENY"
    headers["Referrer-Policy"] = "no-referrer"
    headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    script = "script-src 'self'" if _STUDIO_PATH.fullmatch(path or "") else "script-src 'none'"
    headers["Content-Security-Policy"] = (
        "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
        f"{script}; form-action 'self'; frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
    )
    headers["Cross-Origin-Opener-Policy"] = "same-origin"
    headers["X-Permitted-Cross-Domain-Policies"] = "none"
    headers["Cache-Control"] = "no-store"
    if "server" in headers:
        del headers["server"]
