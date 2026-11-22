"""Questionnaires, policy acceptance, drift alerts, and dossier export."""

from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import os
import secrets
import tempfile

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile, status)
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_os import cndp, dossier, policies as policy_gen
from compliance_os import questionnaire as qe
from compliance_os import registry, scoring
from compliance_os.models import Client as CoreClient

from .. import models, schemas
from ..db import get_db
from ..deps import (Principal, audit, get_client_or_404, get_principal,
                    require_admin, require_write)

router = APIRouter(prefix="/api", tags=["workspace"])

# Upload ceiling. A vendor questionnaire is a spreadsheet, not a disk image;
# anything larger is refused rather than parsed.
MAX_UPLOAD_BYTES = 5 * 1024 * 1024


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


# =====================================================================
# Questionnaires
# =====================================================================
@router.post("/clients/{client_id}/questionnaires/upload", status_code=201)
async def upload_questionnaire(
    client_id: str,
    request: Request,
    file: UploadFile = File(...),
    name: str = Form(""),
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    """Parse an uploaded questionnaire and draft answers from live control state.

    The uploaded file is parsed then discarded. Only extracted questions and
    drafted answers are persisted -- we do not warehouse a third party's
    document, which would be processing without a basis under Law 09-08.
    """
    client = get_client_or_404(db, principal, client_id)

    raw = await file.read()
    if len(raw) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "file exceeds %d bytes" % MAX_UPLOAD_BYTES,
        )
    if not raw:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty file")

    filename = file.filename or "questionnaire.csv"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in (".csv", ".xlsx", ".xlsm", ".txt"):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "unsupported file type %r; upload .csv or .xlsx" % ext,
        )

    with tempfile.TemporaryDirectory(prefix="compliance-q-") as tmp:
        path = os.path.join(tmp, "upload" + ext)
        with open(path, "wb") as f:
            f.write(raw)
        try:
            questions = qe.parse_questionnaire(path)
        except RuntimeError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
        except Exception as exc:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "could not parse the file: %s" % type(exc).__name__,
            )

    if not questions:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "no questions detected; the parser looks for a column named "
            "question / requirement / control / description",
        )

    # Build a throwaway workspace from the DB so the answer engine sees the
    # SAME control states the dashboard shows.
    with tempfile.TemporaryDirectory(prefix="compliance-qws-") as tmp:
        ws = registry.Workspace(tmp)
        ws.init()
        core = _to_core(client)
        ws.create_client(client.legal_name, slug=client.slug, **{
            k: v for k, v in core.data.items()
            if k in {"sector", "headcount", "rc", "ice", "if_number", "address",
                     "contact_name", "contact_email", "export_markets",
                     "handles_sensitive_data", "handles_cin", "is_public_entity",
                     "is_iiv", "hosting_region", "hosting_country"}
        })
        for fid in registry.framework_ids():
            a = ws.load_assessment(client.slug, fid)
            rows = db.execute(
                select(models.ControlState).where(
                    models.ControlState.client_id == client.id,
                    models.ControlState.framework_id == fid,
                )
            ).scalars().all()
            for r in rows:
                row = a.row(r.control_id)
                row.state = r.state
                row.notes = r.notes
            ws.save_assessment(a)

        result = qe.answer_questionnaire(
            ws, client.slug, questions, source_file=filename,
        )

    rec = models.Questionnaire(
        tenant_id=principal.tenant_id,
        client_id=client.id,
        name=name or os.path.splitext(filename)[0],
        source_file=filename,
        total_questions=result.total,
        counts=json.dumps(result.counts()),
        answers=json.dumps([a.to_dict() for a in result.answers]),
        file_sha256=hashlib.sha256(raw).hexdigest(),
        status="drafted",
        created_by=principal.user.email,
    )
    db.add(rec)
    db.flush()
    audit(db, principal, "questionnaire.upload", "questionnaire", rec.id,
          {"questions": result.total, "needs_review": result.counts()["needs_review"]},
          request)
    db.commit()

    return {
        "id": rec.id,
        "name": rec.name,
        "source_file": rec.source_file,
        "total_questions": rec.total_questions,
        "counts": result.counts(),
        "file_sha256": rec.file_sha256,
        "status": rec.status,
        "created_at": rec.created_at.isoformat(),
    }


@router.get("/clients/{client_id}/questionnaires")
def list_questionnaires(
    client_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    rows = db.execute(
        select(models.Questionnaire)
        .where(models.Questionnaire.client_id == client.id)
        .order_by(models.Questionnaire.created_at.desc())
    ).scalars().all()
    return [
        {
            "id": r.id, "name": r.name, "source_file": r.source_file,
            "total_questions": r.total_questions,
            "counts": json.loads(r.counts or "{}"),
            "status": r.status, "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/clients/{client_id}/questionnaires/{q_id}")
def get_questionnaire(
    client_id: str, q_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    rec = db.get(models.Questionnaire, q_id)
    if rec is None or rec.client_id != client.id or rec.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "questionnaire not found")
    return {
        "id": rec.id, "name": rec.name, "source_file": rec.source_file,
        "total_questions": rec.total_questions,
        "counts": json.loads(rec.counts or "{}"),
        "status": rec.status,
        "file_sha256": rec.file_sha256,
        "created_at": rec.created_at.isoformat(),
        "answers": json.loads(rec.answers or "[]"),
    }


@router.patch("/clients/{client_id}/questionnaires/{q_id}/answers")
def patch_answer(
    client_id: str, q_id: str,
    body: schemas.QuestionnaireAnswerPatch,
    request: Request,
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    """Edit one drafted answer. A human edit clears the review flag."""
    client = get_client_or_404(db, principal, client_id)
    rec = db.get(models.Questionnaire, q_id)
    if rec is None or rec.client_id != client.id or rec.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "questionnaire not found")

    answers = json.loads(rec.answers or "[]")
    idx = next((i for i, a in enumerate(answers) if a.get("row") == body.row), None)
    if idx is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "row %r not found" % body.row)

    answers[idx]["draft"] = body.draft
    if body.confidence:
        answers[idx]["confidence"] = body.confidence
    answers[idx]["review_flag"] = ""
    answers[idx]["review_reason"] = ""
    answers[idx]["edited_by"] = principal.user.email
    answers[idx]["edited_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

    rec.answers = json.dumps(answers)

    counts = {"high": 0, "medium": 0, "low": 0, "needs_review": 0, "unmatched": 0}
    for a in answers:
        counts[a.get("confidence", "low")] = counts.get(a.get("confidence", "low"), 0) + 1
        if a.get("review_flag"):
            counts["needs_review"] += 1
        if not a.get("matched_controls"):
            counts["unmatched"] += 1
    rec.counts = json.dumps(counts)

    audit(db, principal, "questionnaire.edit", "questionnaire", rec.id,
          {"row": body.row}, request)
    db.commit()
    return {"row": body.row, "counts": counts, "answers": answers}


@router.get("/clients/{client_id}/questionnaires/{q_id}/export")
def export_questionnaire(
    client_id: str, q_id: str, fmt: str = "md",
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Export the finished questionnaire as Markdown or CSV."""
    client = get_client_or_404(db, principal, client_id)
    rec = db.get(models.Questionnaire, q_id)
    if rec is None or rec.client_id != client.id or rec.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "questionnaire not found")

    answers = json.loads(rec.answers or "[]")
    result = qe.QuestionnaireResult(
        client_slug=client.slug, source_file=rec.source_file,
        total=rec.total_questions, generated_at=rec.created_at.isoformat(),
    )
    for a in answers:
        result.answers.append(qe.Answer(**{
            k: v for k, v in a.items()
            if k in qe.Answer.__dataclass_fields__
        }))

    if fmt == "csv":
        rows = qe.to_csv_rows(result)
        body = io.StringIO()
        import csv as _csv
        _csv.writer(body).writerows(rows)
        return Response(
            content=body.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition":
                     'attachment; filename="questionnaire-%s.csv"' % rec.id[:8]},
        )

    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "q.md")
        qe.write_markdown(result, path, client.legal_name)
        text = open(path, encoding="utf-8").read()
    return Response(
        content=text, media_type="text/markdown",
        headers={"Content-Disposition":
                 'attachment; filename="questionnaire-%s.md"' % rec.id[:8]},
    )


# =====================================================================
# Policy acceptance
# =====================================================================
@router.post("/clients/{client_id}/policies/publish", status_code=201)
def publish_policy(
    client_id: str,
    body: schemas.PolicyPublishIn,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Render a policy from the generator and publish a version."""
    client = get_client_or_404(db, principal, client_id)
    core = _to_core(client)

    try:
        text = policy_gen.render_policy(body.policy_id, core, lang=body.language)
    except KeyError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))

    meta = next((p for p in policy_gen.list_policies() if p["id"] == body.policy_id), None)
    if meta is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown policy")

    prior = db.execute(
        select(models.PolicyDocument)
        .where(models.PolicyDocument.client_id == client.id,
               models.PolicyDocument.policy_id == body.policy_id)
        .order_by(models.PolicyDocument.version.desc())
        .limit(1)
    ).scalars().first()
    version = (prior.version + 1) if prior else 1

    # Only one current version per policy.
    db.execute(
        select(models.PolicyDocument).where(
            models.PolicyDocument.client_id == client.id,
            models.PolicyDocument.policy_id == body.policy_id,
        )
    )
    for old in db.execute(
        select(models.PolicyDocument).where(
            models.PolicyDocument.client_id == client.id,
            models.PolicyDocument.policy_id == body.policy_id,
            models.PolicyDocument.is_current == True,  # noqa: E712
        )
    ).scalars().all():
        old.is_current = False

    rec = models.PolicyDocument(
        tenant_id=principal.tenant_id,
        client_id=client.id,
        policy_id=body.policy_id,
        title=(meta["title_fr"] if body.language == "fr" else meta["title_en"]),
        version=version,
        language=body.language,
        body=text,
        controls=json.dumps(meta["controls"]),
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        published_by=principal.user.email,
        is_current=True,
        requires_acknowledgement=body.requires_acknowledgement,
    )
    db.add(rec)
    db.flush()
    audit(db, principal, "policy.publish", "policy", rec.id,
          {"policy_id": body.policy_id, "version": version}, request)
    db.commit()

    return {
        "id": rec.id, "policy_id": rec.policy_id, "title": rec.title,
        "version": rec.version, "language": rec.language,
        "content_sha256": rec.content_sha256,
        "published_at": rec.published_at.isoformat(),
    }


@router.get("/clients/{client_id}/policies")
def list_policies(
    client_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    docs = db.execute(
        select(models.PolicyDocument)
        .where(models.PolicyDocument.client_id == client.id)
        .order_by(models.PolicyDocument.policy_id, models.PolicyDocument.version.desc())
    ).scalars().all()

    out = []
    for d in docs:
        acks = db.execute(
            select(models.PolicyAcknowledgement)
            .where(models.PolicyAcknowledgement.policy_document_id == d.id)
        ).scalars().all()
        out.append({
            "id": d.id, "policy_id": d.policy_id, "title": d.title,
            "version": d.version, "language": d.language,
            "is_current": d.is_current,
            "requires_acknowledgement": d.requires_acknowledgement,
            "controls": json.loads(d.controls or "[]"),
            "acknowledgement_count": len(acks),
            "published_at": d.published_at.isoformat(),
            "content_sha256": d.content_sha256,
        })
    return out


@router.get("/policies/available")
def available_policies(principal: Principal = Depends(get_principal)):
    return policy_gen.list_policies()


@router.get("/clients/{client_id}/policies/{doc_id}")
def get_policy(
    client_id: str, doc_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    d = db.get(models.PolicyDocument, doc_id)
    if d is None or d.client_id != client.id or d.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")
    acks = db.execute(
        select(models.PolicyAcknowledgement)
        .where(models.PolicyAcknowledgement.policy_document_id == d.id)
        .order_by(models.PolicyAcknowledgement.acknowledged_at.desc())
    ).scalars().all()
    return {
        "id": d.id, "policy_id": d.policy_id, "title": d.title,
        "version": d.version, "language": d.language, "body": d.body,
        "controls": json.loads(d.controls or "[]"),
        "content_sha256": d.content_sha256,
        "acknowledgements": [
            {"person_email": a.person_email, "person_name": a.person_name,
             "acknowledged_at": a.acknowledged_at.isoformat(), "method": a.method}
            for a in acks
        ],
    }


@router.post("/clients/{client_id}/policies/{doc_id}/acknowledge", status_code=201)
def acknowledge_policy(
    client_id: str, doc_id: str,
    body: schemas.AcknowledgeIn,
    request: Request,
    principal: Principal = Depends(require_write),
    db: Session = Depends(get_db),
):
    """Record one person accepting one policy version.

    This row is the evidence. An unsigned policy is a document, not a control.
    """
    client = get_client_or_404(db, principal, client_id)
    d = db.get(models.PolicyDocument, doc_id)
    if d is None or d.client_id != client.id or d.tenant_id != principal.tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")

    existing = db.execute(
        select(models.PolicyAcknowledgement).where(
            models.PolicyAcknowledgement.policy_document_id == d.id,
            models.PolicyAcknowledgement.person_email == body.person_email.lower(),
        )
    ).scalars().first()
    if existing:
        return {
            "already_acknowledged": True,
            "acknowledged_at": existing.acknowledged_at.isoformat(),
        }

    ip = request.client.host if request.client else ""
    rec = models.PolicyAcknowledgement(
        tenant_id=principal.tenant_id, client_id=client.id,
        policy_document_id=d.id,
        person_email=body.person_email.lower(),
        person_name=body.person_name,
        ip=ip, method=body.method,
    )
    db.add(rec)
    audit(db, principal, "policy.acknowledge", "policy", d.id,
          {"person": body.person_email.lower()}, request)
    db.commit()
    return {
        "already_acknowledged": False,
        "acknowledged_at": rec.acknowledged_at.isoformat(),
        "policy_id": d.policy_id, "version": d.version,
    }


@router.get("/clients/{client_id}/policies/{doc_id}/acceptance")
def policy_acceptance(
    client_id: str, doc_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Acceptance rate for one policy version.

    `expected` is the client headcount where recorded. Without a roster we
    cannot compute a true rate, so it is reported as None rather than guessed.
    """
    client = get_client_or_404(db, principal, client_id)
    d = db.get(models.PolicyDocument, doc_id)
    if d is None or d.client_id != client.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "policy not found")
    acks = db.execute(
        select(models.PolicyAcknowledgement)
        .where(models.PolicyAcknowledgement.policy_document_id == d.id)
    ).scalars().all()

    expected = None
    digits = "".join(c for c in (client.headcount or "") if c.isdigit())
    if digits:
        expected = int(digits)

    return {
        "policy_id": d.policy_id, "version": d.version,
        "acknowledged": len(acks),
        "expected": expected,
        "rate": (len(acks) / expected) if expected else None,
        "people": [
            {"person_email": a.person_email, "person_name": a.person_name,
             "acknowledged_at": a.acknowledged_at.isoformat()}
            for a in acks
        ],
    }


# =====================================================================
# Drift alert channels
# =====================================================================
@router.post("/clients/{client_id}/drift-alerts", status_code=201)
def add_drift_channel(
    client_id: str,
    body: schemas.DriftChannelIn,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    if body.channel not in ("webhook", "slack", "email"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "channel must be webhook, slack or email")
    if body.channel in ("webhook", "slack") and not body.target.startswith("https://"):
        # A drift alert carries control names and client identity. Sending it
        # over cleartext would leak exactly the information it reports on.
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "webhook and slack targets must use https://")
    if body.channel == "email" and "@" not in body.target:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid email target")

    rec = models.DriftAlertChannel(
        tenant_id=principal.tenant_id, client_id=client.id,
        channel=body.channel, target=body.target,
        min_severity=body.min_severity, enabled=True,
    )
    db.add(rec)
    audit(db, principal, "drift_channel.add", "client", client.id,
          {"channel": body.channel}, request)
    db.commit()
    return {"id": rec.id, "channel": rec.channel, "min_severity": rec.min_severity}


@router.get("/clients/{client_id}/drift-alerts")
def list_drift_channels(
    client_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    rows = db.execute(
        select(models.DriftAlertChannel)
        .where(models.DriftAlertChannel.client_id == client.id)
    ).scalars().all()
    # Target is returned masked: it may embed a webhook secret path.
    out = []
    for r in rows:
        t = r.target
        masked = t if r.channel == "email" else (t[:32] + "..." if len(t) > 35 else t)
        out.append({"id": r.id, "channel": r.channel, "target_masked": masked,
                    "min_severity": r.min_severity, "enabled": r.enabled})
    return out


@router.delete("/clients/{client_id}/drift-alerts/{channel_id}", status_code=204)
def delete_drift_channel(
    client_id: str, channel_id: str,
    request: Request,
    principal: Principal = Depends(require_admin),
    db: Session = Depends(get_db),
):
    client = get_client_or_404(db, principal, client_id)
    rec = db.get(models.DriftAlertChannel, channel_id)
    if rec is None or rec.client_id != client.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "channel not found")
    db.delete(rec)
    audit(db, principal, "drift_channel.delete", "client", client.id, {}, request)
    db.commit()
    return None


# =====================================================================
# Audit dossier export
# =====================================================================
@router.get("/clients/{client_id}/audit-dossier")
def export_dossier(
    client_id: str,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """One-click audit dossier ZIP.

    Read-only for every role, including external_auditor: an auditor preparing
    their own working papers is a normal, expected action.
    """
    client = get_client_or_404(db, principal, client_id)
    core = _to_core(client)

    scores_payload = []
    control_rows = []
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        from compliance_os.models import Assessment
        a = Assessment(client_slug=client.slug, framework_id=fid)
        rows = db.execute(
            select(models.ControlState).where(
                models.ControlState.client_id == client.id,
                models.ControlState.framework_id == fid,
            )
        ).scalars().all()
        for r in rows:
            a.row(r.control_id).state = r.state
            a.row(r.control_id).owner = r.owner
            a.row(r.control_id).due = r.due
        s = scoring.score(fw, core, a)
        scores_payload.append({
            "framework_id": fid, "framework_name": fw.name, "pct": round(s.pct, 1),
            "verdict": scoring.readiness_verdict(s.pct), "applicable": s.applicable,
            "gaps": len(s.gaps), "partials": len(s.partials),
            "unassessed": len(s.unassessed),
            "excluded": s.by_state.get("not_applicable", 0),
            "gap_list": s.gaps,
        })
        for r in rows:
            control_rows.append({
                "id": r.control_id, "framework": fid,
                "title": (fw.by_id(r.control_id).title if fw.by_id(r.control_id) else ""),
                "state": r.state, "weight": (fw.by_id(r.control_id).weight if fw.by_id(r.control_id) else ""),
                "owner": r.owner, "due": r.due,
                "evidence_count": db.execute(
                    select(models.EvidenceRecord).where(
                        models.EvidenceRecord.client_id == client.id,
                        models.EvidenceRecord.control_id == r.control_id,
                    )
                ).scalars().all().__len__(),
            })

    evidence_rows = [
        {"id": e.id, "control_id": e.control_id, "framework": e.framework_id,
         "kind": e.kind, "sha256": e.sha256,
         "collected_at": e.collected_at.isoformat() if e.collected_at else "",
         "summary": e.summary}
        for e in db.execute(
            select(models.EvidenceRecord)
            .where(models.EvidenceRecord.client_id == client.id)
        ).scalars().all()
    ]

    runs = db.execute(
        select(models.MonitorRunRecord)
        .where(models.MonitorRunRecord.client_id == client.id)
        .order_by(models.MonitorRunRecord.started_at.desc())
        .limit(30)
    ).scalars().all()
    monitor_payload = [
        {"fingerprint": r.fingerprint, "score": r.score,
         "previous_fingerprint": r.previous_fingerprint,
         "counts": json.loads(r.counts or "{}"),
         "sources": json.loads(r.sources or "[]"),
         "started_at": r.started_at.isoformat(),
         "drift": [
             {"check_id": x.get("check_id"), "drift": x.get("drift"),
              "severity": x.get("severity")}
             for x in json.loads(r.results or "[]") if x.get("drift")
         ]}
        for r in runs
    ]

    observations = {}
    if runs:
        latest = runs[0]
        try:
            for res in json.loads(latest.results or "[]"):
                if res.get("outcome") in ("PASS", "FAIL"):
                    observations.setdefault(res.get("source", "unknown"), {})[
                        res.get("check_id")] = {
                            "outcome": res.get("outcome"),
                            "observed": res.get("observed"),
                        }
        except Exception:
            observations = {}

    policy_rows = []
    for d in db.execute(
        select(models.PolicyDocument).where(models.PolicyDocument.client_id == client.id)
    ).scalars().all():
        for ack in db.execute(
            select(models.PolicyAcknowledgement).where(
                models.PolicyAcknowledgement.policy_document_id == d.id)
        ).scalars().all():
            policy_rows.append({
                "policy_id": d.policy_id, "title": d.title, "version": d.version,
                "person_email": ack.person_email, "person_name": ack.person_name,
                "acknowledged_at": ack.acknowledged_at.isoformat(),
            })

    data = dossier.build_dossier_bytes(
        client=core,
        scores=scores_payload,
        control_rows=control_rows,
        evidence_rows=evidence_rows,
        observations=observations,
        monitor_runs=monitor_payload,
        policy_acceptance=policy_rows,
    )

    audit(db, principal, "dossier.export", "client", client.id,
          {"bytes": len(data)}, request)
    db.commit()

    stamp = _dt.date.today().isoformat()
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition":
                 'attachment; filename="%s-audit-dossier-%s.zip"' % (client.slug, stamp)},
    )
