"""Authentication service and request security policy.

The service owns session lifecycle and deliberately returns only public user
attributes. Session cookies contain an opaque token; only its SHA-256 digest is
persisted in ``login_sessions``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import uuid4

from fastapi import Request, Response
from sqlmodel import Session, select

from app.core.config import Settings
from app.core.errors import AppError
from app.core.security import generate_token, hash_token, tokens_equal, verify_password
from app.db.models import LoginSession, User

_DUMMY_PASSWORD_HASH: Final[str] = (
    "$argon2id$v=19$m=65536,t=3,p=4$NFSsAYquuqYM7oDEpSOs+A$"
    "f4L2UF8DQESY2QKz+O7wiNcbDY19aKYr7tQ6YhVf8J8"
)
CSRF_HEADER: Final[str] = "X-CSRF-Token"
_ORIGIN_HEADER: Final[str] = "Origin"
_ORIGIN_HEADER: Final[str] = "Origin"
CSRF_HEADER: Final[str] = "X-CSRF-Token"


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def public_user(user: User) -> dict[str, str]:
    return {"id": user.id, "displayName": user.display_name, "role": user.role}


def _configured_origins(request: Request, settings: Settings) -> set[str]:
    configured = {origin.rstrip("/") for origin in settings.allowed_origins if origin.strip()}
    # Same-origin development should work without requiring an env setting. The
    # Vite proxy is a browser origin at :5173 while the API itself is :8000.
    if not configured and settings.environment != "production":
        configured.update(
            {
                f"{request.url.scheme}://{request.url.netloc}",
                "http://127.0.0.1:5173",
                "http://localhost:5173",
            }
        )
    return configured


def validate_origin(request: Request, settings: Settings) -> None:
    origin = request.headers.get(_ORIGIN_HEADER)
    if not origin:
        raise AppError("ORIGIN_REQUIRED", "请求来源无法验证", status_code=403)
    if origin.rstrip("/") not in _configured_origins(request, settings):
        raise AppError("ORIGIN_INVALID", "请求来源无法验证", status_code=403)


def validate_write_security(request: Request, settings: Settings, session: LoginSession) -> None:
    validate_origin(request, settings)
    csrf = request.headers.get(CSRF_HEADER)
    if not csrf or not tokens_equal(csrf, session.csrf_token):
        raise AppError("CSRF_INVALID", "请求安全校验失败", status_code=403)


def _session_from_request(
    request: Request, db: Session, settings: Settings
) -> tuple[LoginSession, User]:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise AppError("AUTHENTICATION_REQUIRED", "请先登录", status_code=401)
    session = db.exec(
        select(LoginSession).where(LoginSession.token_hash == hash_token(token))
    ).first()
    if session is None:
        raise AppError("AUTHENTICATION_REQUIRED", "请先登录", status_code=401)
    now = utc_now()
    if session.revoked_at is not None or parse_timestamp(session.expires_at) <= now:
        raise AppError("AUTHENTICATION_REQUIRED", "请先登录", status_code=401)
    user = db.get(User, session.user_id)
    if user is None or not bool(user.is_active):
        raise AppError("AUTHENTICATION_REQUIRED", "请先登录", status_code=401)
    return session, user


def current_session(request: Request, db: Session, settings: Settings) -> tuple[LoginSession, User]:
    return _session_from_request(request, db, settings)


def login(
    db: Session,
    settings: Settings,
    username: str,
    password: str,
    *,
    request: Request,
    response: Response,
) -> tuple[User, str]:
    validate_origin(request, settings)
    user = db.exec(select(User).where(User.username == username)).first()
    # Keep the verification path identical for unknown accounts and bad passwords.
    if user is None:
        valid = verify_password(_DUMMY_PASSWORD_HASH, password)
    else:
        valid = verify_password(user.password_hash, password)
    if user is None or not valid or not bool(user.is_active):
        raise AppError("INVALID_CREDENTIALS", "账号或密码错误", status_code=401)

    now = utc_now()
    raw_token = generate_token()
    csrf_token = generate_token()
    db.add(
        LoginSession(
            id=str(uuid4()),
            user_id=user.id,
            token_hash=hash_token(raw_token),
            csrf_token=csrf_token,
            expires_at=timestamp(now + timedelta(seconds=settings.session_ttl_seconds)),
            created_at=timestamp(now),
        )
    )
    db.commit()
    _set_cookie(response, settings, raw_token)
    return user, csrf_token


def logout(
    db: Session,
    settings: Settings,
    request: Request,
    response: Response,
    session: LoginSession,
) -> None:
    validate_write_security(request, settings, session)
    session.revoked_at = timestamp(utc_now())
    db.add(session)
    db.commit()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )


def _set_cookie(response: Response, settings: Settings, token: str) -> None:
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        expires=settings.session_ttl_seconds,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,
    )
