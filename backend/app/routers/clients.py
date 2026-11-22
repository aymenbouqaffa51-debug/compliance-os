"""Client workspaces, frameworks, control state, scoring and evidence."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_os import registry, scoring
from compliance_os.models import Client as CoreClient

from .. import models, schemas
from ..db import get_db
from ..deps import Principal, audit, get_client_or_404, get_principal, require_write

router = APIRouter(prefix="/api", tags=["clients"])


def _to_core(client: models.ClientRecord) -> CoreClient:
    try:
        facts = json.loads(client.footprint or "{}")
    except Exception:
        facts = {}
    facts.setdefault("slug", client.slug)
    facts.setdefault("legal_name", client.legal_name)
    facts.setdefault("sector", client.sector)
    facts.setdefault("headcount", client.headcount)
    facts.setdefault("rc", client.rc)
    facts.setdefault("ice", client.ice)
    return CoreClient.from_dict(facts)


def _load_core_assessment(db: Session, client: models.ClientRecord, framework_id: str):
    from compliance_os.models import Assessment
    a = Assessment(client_slug=client.slug, framework_id=framework_id)
    rows = db.execute(
        select(models.ControlState).where(
            models.ControlState.client_id == client.id,
            models.ControlState.framework_id == framework_id,
        )
    ).scalars().all()
    for r in rows:
        row = a.row(r.control_id)
        row.state = r.state
        row.notes = r.notes
        row.owner = r.owner
        row.due = r.due
        evs = db.execute(
            select(models.EvidenceRecord).where(
                models.EvidenceRecord.client_id == client.id,
                models.EvidenceRecord.control_id == r.control_id,
            )
        ).scalars().all()
        from compliance_os.models import EvidenceItem
        for e in evs:
            row.evidence.append(EvidenceItem(
                kind=e.kind, summary=e.summary, source=e.source,
                sha256=e.sha256, collector=e.collector,
                collected_at=e.collected_at.isoformat() if e.collected_at else "",
            ))
    return a


# ------------------------------------------------------------------ frameworks
@router.get("/frameworks", response_model=list[schemas.FrameworkOut])
def list_frameworks(principal: Principal = Depends(get_principal)):
    out = []
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        out.append(schemas.FrameworkOut(
            id=fw.id, name=fw.name, version=fw.version, locale=fw.locale,
            control_count=len(fw.controls),
        ))
    return out


@router.get("/frameworks/{fid}/controls", response_model=list[schemas.ControlOut])
def list_controls(fid: str, principal: Principal = Depends(get_principal)):
    try:
        fw = registry.load_framework(fid)
    except registry.ComplianceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    return [
        schemas.ControlOut(
            id=c.id, title=c.title, ref=c.ref, theme=c.theme,
            objective=c.objective, weight=c.weight,
            applicability=c.applicability, condition=c.condition,
            evidence=c.evidence, maps_to=c.maps_to,
        ) for c in fw.controls
    ]


# --------------------------------------------------------------------- clients
@router.post("/clients", response_model=schemas.ClientOut, status_code=201)
def create_client(
    body: schemas.ClientIn,
    request: Request,
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    slug = registry.slugify(body.slug or body.legal_name)
    try:
        registry.validate_slug(slug)
    except registry.ComplianceError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    dup = db.execute(
        select(models.ClientRecord).where(
            models.ClientRecord.tenant_id == principal.tenant_id,
            models.ClientRecord.slug == slug,
        )
    ).scalars().first()
    if dup:
        raise HTTPException(status.HTTP_409_CONFLICT, "client slug already exists")

    facts = body.model_dump()
    facts.pop("slug", None)
    rec = models.ClientRecord(
        tenant_id=principal.tenant_id,
        slug=slug,
        legal_name=body.legal_name,
        sector=body.sector,
        headcount=body.headcount,
        rc=body.rc,
        ice=body.ice,
        footprint=json.dumps(facts),
    )
    db.add(rec)
    db.flush()
    audit(db, principal, "client.create", "client", rec.id, {"slug": slug}, request)
    db.commit()
    return schemas.ClientOut(
        id=rec.id, slug=rec.slug, legal_name=rec.legal_name, sector=rec.sector,
        headcount=rec.headcount, rc=rec.rc, ice=rec.ice,
        created_at=rec.created_at.isoformat(),
    )


@router.get("/clients", response_model=list[schemas.ClientOut])
def list_clients(principal: Principal = Depends(get_principal), db: Session = Depends(get_db)):
    rows = db.execute(
        select(models.ClientRecord)
        .where(models.ClientRecord.tenant_id == principal.tenant_id)
        .order_by(models.ClientRecord.created_at.desc())
    ).scalars().all()
    return [
        schemas.ClientOut(
            id=r.id, slug=r.slug, legal_name=r.legal_name, sector=r.sector,
            headcount=r.headcount, rc=r.rc, ice=r.ice,
            created_at=r.created_at.isoformat(),
        ) for r in rows
    ]


@router.get("/clients/{client_id}", response_model=schemas.ClientOut)
def get_client(client_id: str, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    r = get_client_or_404(db, principal, client_id)
    return schemas.ClientOut(
        id=r.id, slug=r.slug, legal_name=r.legal_name, sector=r.sector,
        headcount=r.headcount, rc=r.rc, ice=r.ice, created_at=r.created_at.isoformat(),
    )


# ------------------------------------------------------------------ controls
@router.get("/clients/{client_id}/frameworks/{fid}/state", response_model=list[schemas.ControlStateOut])
def get_states(client_id: str, fid: str, principal: Principal = Depends(get_principal),
               db: Session = Depends(get_db)):
    client = get_client_or_404(db, principal, client_id)
    try:
        registry.load_framework(fid)
    except registry.ComplianceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    rows = db.execute(
        select(models.ControlState).where(
            models.ControlState.client_id == client.id,
            models.ControlState.framework_id == fid,
        )
    ).scalars().all()
    out = []
    for r in rows:
        n = db.execute(
            select(models.EvidenceRecord).where(
                models.EvidenceRecord.client_id == client.id,
                models.EvidenceRecord.control_id == r.control_id,
            )
        ).scalars().all()
        out.append(schemas.ControlStateOut(
            control_id=r.control_id, framework_id=r.framework_id, state=r.state,
            notes=r.notes, owner=r.owner, due=r.due,
            signed_off_by=r.signed_off_by, evidence_count=len(n),
        ))
    return out


@router.put("/clients/{client_id}/frameworks/{fid}/controls/{control_id}",
            response_model=schemas.ControlStateOut)
def set_state(
    client_id: str, fid: str, control_id: str,
    body: schemas.ControlStateIn,
    request: Request,
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    try:
        fw = registry.load_framework(fid)
    except registry.ComplianceError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc))
    if fw.by_id(control_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown control %r" % control_id)
    from compliance_os.models import STATES
    if body.state not in STATES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "state must be one of %s" % ", ".join(STATES))

    row = db.execute(
        select(models.ControlState).where(
            models.ControlState.client_id == client.id,
            models.ControlState.framework_id == fid,
            models.ControlState.control_id == control_id,
        )
    ).scalars().first()
    if row is None:
        row = models.ControlState(
            tenant_id=principal.tenant_id, client_id=client.id,
            framework_id=fid, control_id=control_id,
        )
        db.add(row)
    row.state = body.state
    row.notes = body.notes
    row.owner = body.owner
    row.due = body.due
    row.signed_off_by = principal.user.email
    row.signed_off_at = _dt.datetime.now(_dt.timezone.utc)
    audit(db, principal, "control.set", "control", "%s/%s" % (fid, control_id),
          {"state": body.state}, request)
    db.commit()
    return schemas.ControlStateOut(
        control_id=row.control_id, framework_id=row.framework_id, state=row.state,
        notes=row.notes, owner=row.owner, due=row.due, signed_off_by=row.signed_off_by,
    )


# --------------------------------------------------------------------- score
@router.get("/clients/{client_id}/score", response_model=list[schemas.ScoreOut])
def get_score(client_id: str, principal: Principal = Depends(get_principal),
              db: Session = Depends(get_db)):
    client = get_client_or_404(db, principal, client_id)
    core = _to_core(client)
    out = []
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        a = _load_core_assessment(db, client, fid)
        s = scoring.score(fw, core, a)
        out.append(schemas.ScoreOut(
            framework_id=fid, framework_name=fw.name, pct=round(s.pct, 1),
            verdict=scoring.readiness_verdict(s.pct), applicable=s.applicable,
            gaps=len(s.gaps), partials=len(s.partials),
            unassessed=len(s.unassessed),
            excluded=s.by_state.get("not_applicable", 0),
        ))
    return out


# ------------------------------------------------------------------ evidence
@router.post("/clients/{client_id}/frameworks/{fid}/controls/{control_id}/evidence",
             response_model=schemas.EvidenceOut, status_code=201)
def add_evidence(
    client_id: str, fid: str, control_id: str,
    body: schemas.EvidenceIn,
    request: Request,
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    digest = hashlib.sha256(
        json.dumps({"summary": body.summary, "source": body.source}, sort_keys=True).encode()
    ).hexdigest()
    rec = models.EvidenceRecord(
        tenant_id=principal.tenant_id, client_id=client.id,
        control_id=control_id, framework_id=fid, kind=body.kind,
        summary=body.summary, source=body.source, sha256=digest, collector="api",
        meta=json.dumps({"contents_stored": False}),
    )
    db.add(rec)
    db.flush()
    audit(db, principal, "evidence.add", "evidence", rec.id,
          {"control": control_id}, request)
    db.commit()
    return schemas.EvidenceOut(
        id=rec.id, control_id=rec.control_id, kind=rec.kind, summary=rec.summary,
        source=rec.source, sha256=rec.sha256,
        collected_at=rec.collected_at.isoformat(),
    )


@router.get("/clients/{client_id}/evidence", response_model=list[schemas.EvidenceOut])
def list_evidence(client_id: str, principal: Principal = Depends(get_principal),
                  db: Session = Depends(get_db)):
    client = get_client_or_404(db, principal, client_id)
    rows = db.execute(
        select(models.EvidenceRecord)
        .where(models.EvidenceRecord.client_id == client.id)
        .order_by(models.EvidenceRecord.collected_at.desc())
    ).scalars().all()
    return [
        schemas.EvidenceOut(
            id=r.id, control_id=r.control_id, kind=r.kind, summary=r.summary,
            source=r.source, sha256=r.sha256,
            collected_at=r.collected_at.isoformat(),
        ) for r in rows
    ]
