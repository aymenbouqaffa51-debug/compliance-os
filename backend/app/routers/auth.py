"""Registration, login with optional TOTP, and MFA enrolment."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..db import get_db
from ..deps import Principal, audit, get_principal

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _slug(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return (s or "tenant")[:60]


@router.post("/register", response_model=schemas.TokenOut, status_code=201)
def register(body: schemas.RegisterIn, request: Request, db: Session = Depends(get_db)):
    """Create a tenant and its first user, who becomes platform_admin of it."""
    existing = db.execute(select(models.User).where(models.User.email == body.email.lower())).scalars().first()
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "email already registered")

    base = _slug(body.tenant_name)
    slug = base
    n = 1
    while db.execute(select(models.Tenant).where(models.Tenant.slug == slug)).scalars().first():
        n += 1
        slug = "%s-%d" % (base, n)

    tenant = models.Tenant(name=body.tenant_name, slug=slug)
    db.add(tenant)
    db.flush()

    try:
        pw_hash = security.hash_password(body.password)
    except security.AuthError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    user = models.User(
        tenant_id=tenant.id,
        email=body.email.lower(),
        password_hash=pw_hash,
        role=models.ROLE_PLATFORM_ADMIN,
    )
    db.add(user)
    db.flush()

    audit(db, None, "auth.register", "tenant", tenant.id,
          {"email": user.email}, request, tenant_id=tenant.id)
    db.commit()

    return schemas.TokenOut(
        access_token=security.issue_token(user.id, tenant.id, user.role, user.email),
        role=user.role, tenant_id=tenant.id, email=user.email,
    )


@router.post("/login", response_model=schemas.TokenOut)
def login(body: schemas.LoginIn, request: Request, db: Session = Depends(get_db)):
    user = db.execute(select(models.User).where(models.User.email == body.email.lower())).scalars().first()
    if user is None or not user.is_active:
        # Same error for unknown user and wrong password: do not leak which.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    if user.totp_enabled:
        if not body.totp_code:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "TOTP code required",
                headers={"X-TOTP-Required": "1"},
            )
        if not security.verify_totp(user.totp_secret, body.totp_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid TOTP code")

    import datetime as _dt
    user.last_login_at = _dt.datetime.now(_dt.timezone.utc)
    principal = Principal(user, db.get(models.Tenant, user.tenant_id))
    audit(db, principal, "auth.login", "user", user.id, {}, request)
    db.commit()

    return schemas.TokenOut(
        access_token=security.issue_token(user.id, user.tenant_id, user.role, user.email),
        role=user.role, tenant_id=user.tenant_id, email=user.email,
        totp_required=user.totp_enabled,
    )


@router.get("/me", response_model=schemas.MeOut)
def me(principal: Principal = Depends(get_principal)):
    return schemas.MeOut(
        id=principal.user.id,
        email=principal.user.email,
        role=principal.role,
        tenant_id=principal.tenant_id,
        tenant_name=principal.tenant.name,
        totp_enabled=principal.user.totp_enabled,
    )


@router.post("/totp/setup", response_model=schemas.TotpSetupOut)
def totp_setup(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    """Generate a TOTP secret. Not enabled until verified."""
    secret = security.generate_totp_secret()
    principal.user.totp_secret = secret
    principal.user.totp_enabled = False
    db.commit()
    return schemas.TotpSetupOut(
        secret=secret,
        uri=security.totp_uri(secret, principal.user.email),
    )


@router.post("/totp/verify")
def totp_verify(
    body: schemas.TotpVerifyIn,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    if not principal.user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "run /totp/setup first")
    if not security.verify_totp(principal.user.totp_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")
    principal.user.totp_enabled = True
    db.commit()
    return {"totp_enabled": True}


@router.post("/totp/disable")
def totp_disable(body: schemas.TotpVerifyIn, principal: Principal = Depends(get_principal),
                 db: Session = Depends(get_db)):
    """Disabling MFA requires a valid code, not just a session."""
    if not principal.user.totp_enabled:
        return {"totp_enabled": False}
    if not security.verify_totp(principal.user.totp_secret, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid code")
    principal.user.totp_enabled = False
    principal.user.totp_secret = ""
    db.commit()
    return {"totp_enabled": False}
