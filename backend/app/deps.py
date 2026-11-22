"""Shared FastAPI dependencies: authentication, RBAC, audit logging."""

from __future__ import annotations

import datetime as _dt
import json
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models, security
from .db import get_db

bearer = HTTPBearer(auto_error=False)


class Principal:
    def __init__(self, user: models.User, tenant: models.Tenant):
        self.user = user
        self.tenant = tenant

    @property
    def role(self) -> str:
        return self.user.role

    @property
    def tenant_id(self) -> str:
        return self.user.tenant_id


def get_principal(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    try:
        payload = security.decode_token(creds.credentials)
    except security.AuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    user = db.get(models.User, payload.get("sub", ""))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not available")
    tenant = db.get(models.Tenant, user.tenant_id)
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant inactive")
    return Principal(user, tenant)


def require_write(principal: Principal = Depends(get_principal)) -> Principal:
    """Any role that may mutate control state. An auditor never can."""
    if principal.role not in models.WRITE_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "role %r is read-only" % principal.role,
        )
    return principal


def require_admin(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role not in (models.ROLE_PLATFORM_ADMIN, models.ROLE_CONSULTANT, models.ROLE_CLIENT_ADMIN):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required")
    return principal


def get_client_or_404(db: Session, principal: Principal, client_id: str) -> models.ClientRecord:
    """Tenant-scoped lookup. A client from another tenant is a 404, not a 403.

    Returning 404 avoids leaking the existence of another tenant's record.
    """
    obj = db.get(models.ClientRecord, client_id)
    if obj is None or obj.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "client not found")
    return obj


def audit(
    db: Session,
    principal: Optional[Principal],
    action: str,
    object_type: str = "",
    object_id: str = "",
    detail: Optional[dict] = None,
    request: Optional[Request] = None,
    tenant_id: str = "",
) -> None:
    """Append a hash-chained audit record.

    `tenant_id` may be passed explicitly for events that happen before a
    Principal exists -- registration is the important case, because the tenant
    row is created in the same transaction and the audit row must reference it.
    """
    if principal is not None:
        tenant_id = principal.tenant_id
    if not tenant_id:
        raise ValueError(
            "audit() needs a tenant_id: pre-authentication events must pass it explicitly"
        )
    # Ordering by created_at is not safe under concurrency: two requests in the
    # same millisecond produce identical timestamps, and on SQLite the order is
    # undefined, so both could read the same predecessor and FORK the chain.
    #
    # Fix: order by the monotonic primary key instead. Where the backend supports
    # row locking (PostgreSQL) take a FOR UPDATE lock on the tail row so two
    # concurrent appends serialise; SQLite serialises writers at the database
    # level already, so the lock is skipped there (FOR UPDATE is a syntax error
    # in SQLite).
    stmt = (
        select(models.AuditLog)
        .where(models.AuditLog.tenant_id == tenant_id)
        .order_by(models.AuditLog.id.desc())
        .limit(1)
    )
    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect == "postgresql":
        stmt = stmt.with_for_update()
    last = db.execute(stmt).scalars().first()
    prev = last.hash if last else ""

    ip = ""
    if request is not None and request.client:
        ip = request.client.host or ""

    payload = {
        "tenant_id": tenant_id,
        "actor_id": principal.user.id if principal else "",
        "actor_email": principal.user.email if principal else "",
        "action": action,
        "object_type": object_type,
        "object_id": object_id,
        "detail": json.dumps(detail or {}, sort_keys=True, default=str),
        "ip": ip,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    row = models.AuditLog(
        tenant_id=tenant_id,
        actor_id=payload["actor_id"],
        actor_email=payload["actor_email"],
        action=action,
        object_type=object_type,
        object_id=object_id,
        detail=payload["detail"],
        ip=ip,
        previous_hash=prev,
    )
    row.hash = models.AuditLog.compute_hash(prev, payload)
    db.add(row)
