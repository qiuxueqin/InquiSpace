"""Database-backed idempotency primitives for write endpoints.

The route must authorize the target object before calling ``begin``.  A replay is
therefore never an authorization bypass.  The stored payload is the already
serialized JSON envelope's *data* plus status; callers supply the request hash,
which includes the method/path/body and any relevant concurrency header.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from app.core.errors import AppError
from app.db.models import IdempotencyKey


def utc_now() -> datetime:
    return datetime.now(UTC)


def timestamp(value: datetime) -> str:
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def request_hash(method: str, path: str, body: Any, extra: str = "") -> str:
    encoded = json.dumps(
        {"method": method.upper(), "path": path, "body": body, "extra": extra},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class Replay:
    status: int
    body: dict[str, Any]


@dataclass(frozen=True)
class Reservation:
    row: IdempotencyKey
    replay: Replay | None = None


def begin(
    session: Session,
    *,
    user_id: str,
    method: str,
    path: str,
    key: str | None,
    digest: str,
    ttl_seconds: int = 24 * 60 * 60,
) -> Reservation | None:
    if key is None:
        raise AppError("PRECONDITION_REQUIRED", "需要 Idempotency-Key", 428)
    if not 1 <= len(key) <= 128:
        raise AppError("VALIDATION_ERROR", "Idempotency-Key 长度必须为 1 到 128 个字符", 422)

    now = utc_now()
    # Expired records may be reused after removing them in this transaction.
    session.execute(
        IdempotencyKey.__table__.delete().where(
            IdempotencyKey.expires_at <= timestamp(now),
        )
    )
    existing = session.exec(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user_id,
            IdempotencyKey.method == method.upper(),
            IdempotencyKey.path == path,
            IdempotencyKey.key == key,
        )
    ).first()
    if existing is not None:
        if existing.request_hash != digest:
            raise AppError("IDEMPOTENCY_CONFLICT", "幂等键已用于其他请求", 409)
        if existing.status == "completed" and existing.response_status and existing.response_json:
            return Reservation(
                row=existing,
                replay=Replay(existing.response_status, json.loads(existing.response_json)),
            )
        # A prior process may have died while holding the reservation.  Keep the
        # reservation and report conflict rather than running two writes.
        raise AppError("IDEMPOTENCY_IN_PROGRESS", "相同请求正在处理中", 409, retryable=True)

    row = IdempotencyKey(
        id=str(uuid4()),
        user_id=user_id,
        method=method.upper(),
        path=path,
        key=key,
        request_hash=digest,
        status="in_progress",
        created_at=timestamp(now),
        expires_at=timestamp(now + timedelta(seconds=ttl_seconds)),
    )
    session.add(row)
    session.flush()
    return Reservation(row=row)


def complete(
    session: Session,
    reservation: Reservation,
    *,
    status: int,
    body: dict[str, Any],
    resource_id: str | None = None,
) -> None:
    row = reservation.row
    row.status = "completed"
    row.response_status = status
    row.response_json = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    row.resource_id = resource_id
    session.add(row)
