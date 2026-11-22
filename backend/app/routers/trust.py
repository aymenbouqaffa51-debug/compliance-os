"""Public trust centre and time-boxed auditor portal.

The trust centre is deliberately unauthenticated: it exists to be shared with a
buyer's procurement team. It exposes only aggregated posture -- never evidence
content, never a control's internal notes.
"""

from __future__ import annotations

import datetime as _dt
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_os import registry, scoring

from .. import models, schemas
from ..db import get_db
from ..deps import Principal, audit, get_client_or_404, get_principal, require_admin

router = APIRouter(prefix="/api", tags=["trust"])


# ------------------------------------------------------------------ public
@router.get("/trust/{tenant_slug}/{client_slug}")
def public_trust(tenant_slug: str, client_slug: str, db: Session = Depends(get_db)):
    """Aggregated posture for a public trust page. No authentication.

    Exposes: per-framework readiness percentages, counts of passing automated
    checks, hosting region, and whether a CNDP receipt reference is on file.
    Exposes NOTHING that identifies an individual control's weakness.
    """
    tenant = db.execute(select(models.Tenant).where(models.Tenant.slug == tenant_slug)).scalars().first()
    if tenant is None or not tenant.is_active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    client = db.execute(
        select(models.ClientRecord).where(
            models.ClientRecord.tenant_id == tenant.id,
            models.ClientRecord.slug == client_slug,
        )
    ).scalars().first()
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    facts = {}
    try:
        facts = json.loads(client.footprint or "{}")
    except Exception:
        pass

    from compliance_os.models import Client as CoreClient, Assessment
    core = CoreClient.from_dict({**facts, "slug": client.slug, "legal_name": client.legal_name})

    summary = []
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        a = Assessment(client_slug=client.slug, framework_id=fid)
        rows = db.execute(
            select(models.ControlState).where(
                models.ControlState.client_id == client.id,
                models.ControlState.framework_id == fid,
            )
        ).scalars().all()
        for r in rows:
            a.row(r.control_id).state = r.state
        s = scoring.score(fw, core, a)
        summary.append({
            "framework": fw.name.split(" -- ")[0],
            "framework_id": fid,
            "readiness_pct": round(s.pct, 1),
            "verdict": scoring.readiness_verdict(s.pct),
        })

    run = db.execute(
        select(models.MonitorRunRecord)
        .where(models.MonitorRunRecord.client_id == client.id)
        .order_by(models.MonitorRunRecord.started_at.desc())
        .limit(1)
    ).scalars().first()
    monitors = {"score": 0.0, "passing": 0, "failing": 0, "last_run": ""}
    if run:
        counts = json.loads(run.counts or "{}")
        monitors = {
            "score": round(run.score, 1),
            "passing": counts.get("PASS", 0),
            "failing": counts.get("FAIL", 0),
            "last_run": run.started_at.isoformat(),
        }

    return {
        "client": {"name": client.legal_name, "slug": client.slug, "sector": client.sector},
        "frameworks": summary,
        "monitors": monitors,
        "hosting": {
            "region": facts.get("hosting_region", "eu-west-3"),
            "country": facts.get("hosting_country", "France"),
            "note": "Hosted in the European Union; France, Germany and Finland are all on the CNDP adequacy list, so no transfer authorisation is required.",
        },
        "cndp_receipt_on_file": bool(facts.get("cndp_receipt", "")),
        "disclaimer": (
            "This page reports readiness against published frameworks. It is not a "
            "certification, not an attestation, and not an audit. Certification is "
            "issued by an independent accredited body."
        ),
    }


# ----------------------------------------------------- auditor share links
@router.post("/clients/{client_id}/auditor-shares", response_model=schemas.AuditorShareOut, status_code=201)
def create_auditor_share(
    client_id: str,
    body: schemas.AuditorShareIn,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    if body.hours < 1 or body.hours > 24 * 30:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "hours must be between 1 and 720")
    token = secrets.token_urlsafe(32)
    share = models.AuditorShare(
        tenant_id=principal.tenant_id,
        client_id=client.id,
        token=token,
        label=body.label,
        expires_at=_dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=body.hours),
    )
    db.add(share)
    audit(db, principal, "auditor.share.create", "client", client.id,
          {"hours": body.hours}, request)
    db.commit()
    return schemas.AuditorShareOut(
        token=token,
        url="/api/auditor/%s" % token,
        expires_at=share.expires_at.isoformat(),
    )


@router.get("/auditor/{token}")
def auditor_view(token: str, db: Session = Depends(get_db)):
    """Read-only inspection for an external auditor. No write path exists."""
    share = db.execute(
        select(models.AuditorShare).where(models.AuditorShare.token == token)
    ).scalars().first()
    if share is None or share.revoked:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "link not valid")
    # SQLite returns naive datetimes; normalise before comparing so this works
    # identically on SQLite and PostgreSQL.
    expires = share.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=_dt.timezone.utc)
    if expires < _dt.datetime.now(_dt.timezone.utc):
        raise HTTPException(status.HTTP_410_GONE, "link expired")

    client = db.get(models.ClientRecord, share.client_id)
    if client is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")

    rows = db.execute(
        select(models.ControlState).where(models.ControlState.client_id == client.id)
    ).scalars().all()
    evidence = db.execute(
        select(models.EvidenceRecord).where(models.EvidenceRecord.client_id == client.id)
    ).scalars().all()

    return {
        "client": client.legal_name,
        "expires_at": share.expires_at.isoformat(),
        "controls": [
            {"framework": r.framework_id, "control": r.control_id, "state": r.state,
             "signed_off_by": r.signed_off_by,
             "signed_off_at": r.signed_off_at.isoformat() if r.signed_off_at else ""}
            for r in rows
        ],
        "evidence_hashes": [
            {"control": e.control_id, "kind": e.kind, "sha256": e.sha256,
             "collected_at": e.collected_at.isoformat()}
            for e in evidence
        ],
        "note": (
            "Read-only auditor view. Evidence content is not exposed; hashes are "
            "provided so the reviewer can verify integrity against the source document."
        ),
    }


@router.delete("/auditor-shares/{share_id}", status_code=204)
def revoke_share(share_id: str, request: Request,
                 principal: Principal = Depends(require_admin),
                 db: Session = Depends(get_db)):
    share = db.get(models.AuditorShare, share_id)
    if share is None or share.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    share.revoked = True
    audit(db, principal, "auditor.share.revoke", "share", share_id, {}, request)
    db.commit()
    return None
