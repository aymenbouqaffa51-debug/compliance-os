"""Monitoring runs, drift, integrations and the audit log."""

from __future__ import annotations

import datetime as _dt
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_os import checks as check_engine
from compliance_os import collectors_cloud, monitor
from compliance_os.checks import Observation

from .. import models, schemas, security
from ..db import get_db
from ..deps import Principal, audit, get_client_or_404, get_principal, require_admin, require_write

router = APIRouter(prefix="/api", tags=["monitoring"])


@router.get("/checks")
def list_checks(source: str = "", principal: Principal = Depends(get_principal)):
    pool = check_engine.load_checks()
    if source:
        pool = [c for c in pool if c.source == source]
    return [
        {"id": c.id, "title": c.title, "source": c.source, "severity": c.severity,
         "field": c.field, "operator": c.operator, "value": c.value,
         "controls": c.controls, "remediation": c.remediation}
        for c in pool
    ]


@router.post("/clients/{client_id}/monitor/run", response_model=schemas.MonitorRunOut)
def run_monitors(
    client_id: str,
    request: Request,
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    """Execute the configured collectors for this client.

    Credentials are decrypted in memory only. If a provider has no stored
    credential, its checks resolve NOT_APPLICABLE rather than failing.
    """
    client = get_client_or_404(db, principal, client_id)
    facts = {}
    try:
        facts = json.loads(client.footprint or "{}")
    except Exception:
        pass

    collectors = {}
    creds = db.execute(
        select(models.IntegrationCredential).where(
            models.IntegrationCredential.client_id == client.id
        )
    ).scalars().all()

    for cred in creds:
        try:
            secret = security.decrypt_secret(cred.ciphertext)
        except security.AuthError:
            continue
        cfg = {}
        try:
            cfg = json.loads(cred.config or "{}")
        except Exception:
            pass

        if cred.provider == "github":
            org = cfg.get("org", "")
            collectors["github"] = (lambda s=secret, o=org: collectors_cloud.collect_github(org=o, token=s))
        elif cred.provider == "aws":
            region = cfg.get("region", "")
            collectors["aws"] = (lambda r=region: collectors_cloud.collect_aws(region=r))
        elif cred.provider == "workspace":
            dom = cfg.get("domain", "")
            collectors["workspace"] = (lambda d=dom: collectors_cloud.collect_workspace(domain=d))

    # Perimeter needs no credential -- always run it when a domain is known.
    domain = facts.get("domain", "")
    if domain:
        collectors["perimeter"] = (lambda d=domain: collectors_cloud.collect_perimeter(domain=d))

    # The monitor engine needs a workspace for applicability evaluation, but a
    # temp workspace has no run history -- so drift would never fire. Fetch the
    # last MonitorRunRecord from the database and hand it in explicitly.
    from compliance_os import registry as core_registry
    import tempfile, shutil

    prior = db.execute(
        select(models.MonitorRunRecord)
        .where(models.MonitorRunRecord.client_id == client.id)
        .order_by(models.MonitorRunRecord.started_at.desc())
        .limit(1)
    ).scalars().first()

    previous_run = None
    if prior is not None:
        try:
            previous_run = {
                "fingerprint": prior.fingerprint,
                "results": json.loads(prior.results or "[]"),
            }
        except Exception:
            previous_run = None

    tmp = tempfile.mkdtemp(prefix="compliance-api-")
    try:
        ws = core_registry.Workspace(tmp)
        ws.init()
        # Build a minimal core client for applicability evaluation
        ws.create_client(client.legal_name, slug=client.slug, **{
            k: v for k, v in facts.items()
            if k in {"sector","headcount","rc","ice","if_number","address",
                     "contact_name","contact_email","export_markets",
                     "handles_sensitive_data","handles_cin","is_public_entity",
                     "is_iiv","hosting_region","hosting_country"}
        })
        run = monitor.run_monitors(
            ws, client.slug, collectors=collectors, previous_run=previous_run)
        verify = monitor.verify_ledger(ws, client.slug)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Stamp credential use so an operator can see which integrations are live.
    for cred in creds:
        cred.last_used_at = _dt.datetime.now(_dt.timezone.utc)

    rec = models.MonitorRunRecord(
        tenant_id=principal.tenant_id,
        client_id=client.id,
        fingerprint=run.fingerprint,
        previous_fingerprint=run.previous_fingerprint,
        score=run.score(),
        counts=json.dumps(run.counts()),
        results=json.dumps([r.to_dict() for r in run.results]),
        sources=json.dumps(run.sources),
        started_at=_dt.datetime.now(_dt.timezone.utc),
        finished_at=_dt.datetime.now(_dt.timezone.utc),
    )
    db.add(rec)
    audit(db, principal, "monitor.run", "client", client.id,
          {"fingerprint": run.fingerprint, "score": run.score()}, request)
    db.commit()

    return schemas.MonitorRunOut(
        fingerprint=rec.fingerprint, score=rec.score,
        counts=json.loads(rec.counts), sources=json.loads(rec.sources),
        started_at=rec.started_at.isoformat(),
        finished_at=rec.finished_at.isoformat(),
        results=[schemas.MonitorResultOut(**r) for r in json.loads(rec.results)],
    )


@router.get("/clients/{client_id}/monitor/latest", response_model=schemas.MonitorRunOut)
def latest_monitor(client_id: str, principal: Principal = Depends(get_principal),
                   db: Session = Depends(get_db)):
    client = get_client_or_404(db, principal, client_id)
    rec = db.execute(
        select(models.MonitorRunRecord)
        .where(models.MonitorRunRecord.client_id == client.id)
        .order_by(models.MonitorRunRecord.started_at.desc())
        .limit(1)
    ).scalars().first()
    if rec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no monitoring run yet")
    return schemas.MonitorRunOut(
        fingerprint=rec.fingerprint, score=rec.score,
        counts=json.loads(rec.counts), sources=json.loads(rec.sources),
        started_at=rec.started_at.isoformat(),
        finished_at=rec.finished_at.isoformat() if rec.finished_at else "",
        results=[schemas.MonitorResultOut(**r) for r in json.loads(rec.results)],
    )


# ------------------------------------------------------------- integrations
@router.post("/clients/{client_id}/integrations", response_model=schemas.IntegrationOut, status_code=201)
def set_integration(
    client_id: str,
    body: schemas.IntegrationIn,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    if body.provider not in ("github", "aws", "workspace"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "provider must be github, aws or workspace")

    ciphertext = security.encrypt_secret(body.secret)
    row = db.execute(
        select(models.IntegrationCredential).where(
            models.IntegrationCredential.client_id == client.id,
            models.IntegrationCredential.provider == body.provider,
        )
    ).scalars().first()
    if row is None:
        row = models.IntegrationCredential(
            tenant_id=principal.tenant_id, client_id=client.id, provider=body.provider,
        )
        db.add(row)
    row.ciphertext = ciphertext
    row.config = json.dumps({k: v for k, v in body.config.items() if k != "secret"})

    # The audit record deliberately records only that a credential was set.
    audit(db, principal, "integration.set", "integration", body.provider, {}, request)
    db.commit()
    return schemas.IntegrationOut(
        provider=row.provider, config=json.loads(row.config or "{}"),
        created_at=row.created_at.isoformat(),
    )


@router.get("/clients/{client_id}/integrations", response_model=list[schemas.IntegrationOut])
def list_integrations(client_id: str, principal: Principal = Depends(get_principal),
                     db: Session = Depends(get_db)):
    client = get_client_or_404(db, principal, client_id)
    rows = db.execute(
        select(models.IntegrationCredential).where(
            models.IntegrationCredential.client_id == client.id
        )
    ).scalars().all()
    # Never returns the secret.
    return [
        schemas.IntegrationOut(
            provider=r.provider, config=json.loads(r.config or "{}"),
            created_at=r.created_at.isoformat(),
            last_used_at=r.last_used_at.isoformat() if r.last_used_at else None,
        ) for r in rows
    ]


@router.delete("/clients/{client_id}/integrations/{provider}", status_code=204)
def delete_integration(client_id: str, provider: str, request: Request,
                     principal: Principal = Depends(require_admin),
                     db: Session = Depends(get_db)):
    client = get_client_or_404(db, principal, client_id)
    row = db.execute(
        select(models.IntegrationCredential).where(
            models.IntegrationCredential.client_id == client.id,
            models.IntegrationCredential.provider == provider,
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "integration not found")
    db.delete(row)
    audit(db, principal, "integration.delete", "integration", provider, {}, request)
    db.commit()
    return None


# ---------------------------------------------------------------- audit log
@router.get("/audit-log", response_model=list[schemas.AuditLogOut])
def get_audit_log(limit: int = 100, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    rows = db.execute(
        select(models.AuditLog)
        .where(models.AuditLog.tenant_id == principal.tenant_id)
        .order_by(models.AuditLog.created_at.desc())
        .limit(min(limit, 500))
    ).scalars().all()
    return [
        schemas.AuditLogOut(
            action=r.action, object_type=r.object_type, object_id=r.object_id,
            actor_email=r.actor_email, created_at=r.created_at.isoformat(),
        ) for r in rows
    ]
