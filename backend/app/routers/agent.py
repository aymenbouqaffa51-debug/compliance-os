"""AI agent endpoint: grounded answers about a client's compliance position.

The agent retrieves facts from the database, composes an answer from them, and
returns it WITH citations. The LLM, when configured, only rewrites prose.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from compliance_os import agent as agent_engine
from compliance_os import cndp, registry, scoring
from compliance_os.models import Assessment

from .. import models, schemas
from ..db import get_db
from ..deps import Principal, audit, get_client_or_404, get_principal

router = APIRouter(prefix="/api", tags=["agent"])

# A question is a sentence, not a document. Cap it to keep a hostile client from
# using this endpoint to push megabytes through an LLM prompt.
MAX_QUESTION_CHARS = 1000


def _load_context(db: Session, client: models.ClientRecord) -> agent_engine.ContextBundle:
    """Assemble every fact the agent is allowed to see, from the database."""
    try:
        facts = json.loads(client.footprint or "{}")
    except Exception:
        facts = {}

    scores: list = []
    gaps: list = []
    partials: list = []
    unassessed = 0
    implemented = 0

    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        a = Assessment(client_slug=client.slug, framework_id=fid)

        rows = db.execute(
            select(models.ControlState).where(
                models.ControlState.client_id == client.id,
                models.ControlState.framework_id == fid,
            )
        ).scalars().all()
        state_by_id = {r.control_id: r for r in rows}
        for cid, r in state_by_id.items():
            a.row(cid).state = r.state

        from compliance_os.models import Client as CoreClient
        core_client = CoreClient.from_dict({
            **facts, "slug": client.slug, "legal_name": client.legal_name,
            "sector": client.sector, "headcount": client.headcount,
            "rc": client.rc, "ice": client.ice,
        })

        s = scoring.score(fw, core_client, a)
        scores.append({
            "framework_id": fid,
            "framework_name": fw.name.split(" — ")[0],
            "pct": round(s.pct, 1),
            "verdict": scoring.readiness_verdict(s.pct),
            "applicable": s.applicable,
            "gaps": len(s.gaps),
            "partials": len(s.partials),
            "unassessed": len(s.unassessed),
            "excluded": s.by_state.get("not_applicable", 0),
        })
        unassessed += len(s.unassessed)
        implemented += s.by_state.get("implemented", 0)

        for g in s.gaps:
            row = state_by_id.get(g.get("id", ""))
            gaps.append({
                **g,
                "framework": fw.name.split(" — ")[0],
                "framework_id": fid,
                "owner": (row.owner if row else "") or "",
                "due": (row.due if row else "") or "",
            })
        for p in s.partials:
            row = state_by_id.get(p.get("id", ""))
            partials.append({
                **p,
                "framework": fw.name.split(" — ")[0],
                "owner": (row.owner if row else "") or "",
                "due": (row.due if row else "") or "",
            })

    # Latest monitor run
    run = db.execute(
        select(models.MonitorRunRecord)
        .where(models.MonitorRunRecord.client_id == client.id)
        .order_by(models.MonitorRunRecord.started_at.desc())
        .limit(1)
    ).scalars().first()

    monitor_score = None
    failing: list = []
    drift: list = []
    last_run = ""
    if run is not None:
        monitor_score = round(run.score, 1)
        last_run = run.started_at.isoformat()
        try:
            for r in json.loads(run.results or "[]"):
                if r.get("outcome") == "FAIL":
                    failing.append({
                        "check_id": r.get("check_id"), "title": r.get("title"),
                        "severity": r.get("severity"), "observed": r.get("observed"),
                    })
                if r.get("drift"):
                    drift.append({
                        "check_id": r.get("check_id"), "title": r.get("title"),
                        "drift": r.get("drift"),
                    })
        except Exception:
            pass

    # Current policies
    docs = db.execute(
        select(models.PolicyDocument).where(
            models.PolicyDocument.client_id == client.id,
            models.PolicyDocument.is_current == True,  # noqa: E712
        )
    ).scalars().all()
    policy_current = []
    ack_total = 0
    for d in docs:
        acks = db.execute(
            select(models.PolicyAcknowledgement).where(
                models.PolicyAcknowledgement.policy_document_id == d.id)
        ).scalars().all()
        ack_total += len(acks)
        policy_current.append({
            "policy_id": d.policy_id, "title": d.title,
            "version": d.version, "acknowledgement_count": len(acks),
        })

    # Questionnaires pending review
    qs = db.execute(
        select(models.Questionnaire).where(models.Questionnaire.client_id == client.id)
    ).scalars().all()
    q_review = 0
    for q in qs:
        try:
            q_review += int(json.loads(q.counts or "{}").get("needs_review", 0))
        except Exception:
            pass

    evidence_total = len(db.execute(
        select(models.EvidenceRecord).where(models.EvidenceRecord.client_id == client.id)
    ).scalars().all())

    return agent_engine.build_context(
        client_slug=client.slug,
        legal_name=client.legal_name,
        sector=client.sector,
        headcount=client.headcount,
        hosting_country=facts.get("hosting_country", "France"),
        is_public_entity=bool(facts.get("is_public_entity", False)),
        is_iiv=bool(facts.get("is_iiv", False)),
        handles_cin=bool(facts.get("handles_cin", False)),
        handles_sensitive_data=bool(facts.get("handles_sensitive_data", False)),
        scores=scores,
        gaps=gaps,
        partials=partials,
        unassessed_count=unassessed,
        implemented_count=implemented,
        monitor_score=monitor_score,
        monitor_failing=failing,
        monitor_drift=drift,
        monitor_last_run=last_run,
        policy_current=policy_current,
        policy_ack_total=ack_total,
        questionnaire_total=len(qs),
        questionnaire_needs_review=q_review,
        evidence_total=evidence_total,
    )


@router.get("/agent/suggestions")
def suggestions(principal: Principal = Depends(get_principal)):
    """Questions the agent can answer from real data."""
    return {"suggestions": agent_engine.SUGGESTED_QUESTIONS}


@router.post("/clients/{client_id}/agent/ask", response_model=schemas.AgentAnswerOut)
def ask(
    client_id: str,
    body: schemas.AgentAskIn,
    request: Request,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Answer a question about this client, grounded in retrieved facts."""
    client = get_client_or_404(db, principal, client_id)

    question = (body.question or "").strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "question exceeds %d characters" % MAX_QUESTION_CHARS,
        )

    ctx = _load_context(db, client)
    answer = agent_engine.answer_question(question, ctx)
    if body.polish:
        answer = agent_engine.polish_with_llm(answer, question, ctx)

    # Record that the agent was consulted. The question itself is stored because
    # it is the operator's own words about their own client, and it is useful in
    # an audit trail ("who was told what, when").
    audit(db, principal, "agent.ask", "client", client.id,
          {"intent": answer.intent, "grounded": answer.grounded}, request)
    db.commit()

    return schemas.AgentAnswerOut(**answer.to_dict())


@router.get("/clients/{client_id}/agent/context")
def agent_context(
    client_id: str,
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
):
    """Expose exactly what the agent can see.

    Transparency is a feature: if the agent gives a bad answer, the operator can
    inspect the facts it reasoned from rather than guessing.
    """
    client = get_client_or_404(db, principal, client_id)
    ctx = _load_context(db, client)
    return {
        "client_slug": ctx.client_slug,
        "legal_name": ctx.legal_name,
        "scores": ctx.scores,
        "gap_count": len(ctx.gaps),
        "partial_count": len(ctx.partials),
        "unassessed_count": ctx.unassessed_count,
        "monitor_score": ctx.monitor_score,
        "monitor_failing_count": len(ctx.monitor_failing),
        "monitor_drift_count": len(ctx.monitor_drift),
        "policy_count": len(ctx.policy_current),
        "policy_ack_total": ctx.policy_ack_total,
        "questionnaire_needs_review": ctx.questionnaire_needs_review,
        "evidence_total": ctx.evidence_total,
        "hosting_country": ctx.hosting_country,
        "cndp_position": cndp.transfer_position(ctx.hosting_country),
    }
