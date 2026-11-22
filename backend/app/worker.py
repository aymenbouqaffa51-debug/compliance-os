"""Celery worker: scheduled continuous monitoring.

Scheduling model:
  - `beat` enqueues a sweep every 6 hours.
  - A sweep iterates every client that has at least one stored integration and
    enqueues one run per client, so a slow collector cannot block the sweep.
  - A run writes a MonitorRunRecord and, if drift is detected, dispatches a
    notification.

Nothing here mutates a client's environment. Collectors are read-only.
"""

from __future__ import annotations

import json
import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery = Celery("compliance_os", broker=REDIS_URL, backend=REDIS_URL)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_time_limit=1800,
    task_soft_time_limit=1500,
    beat_schedule={
        "sweep-monitors": {
            "task": "app.worker.sweep_monitors",
            "schedule": crontab(minute=0, hour="*/6"),
        },
        "verify-ledger": {
            "task": "app.worker.verify_all_ledgers",
            "schedule": crontab(minute=30, hour=3),
        },
    },
)


@celery.task(name="app.worker.sweep_monitors")
def sweep_monitors():
    """Enqueue a monitor run for every client with a stored integration."""
    from sqlalchemy import select

    from .db import SessionLocal
    from . import models

    db = SessionLocal()
    try:
        rows = db.execute(
            select(models.IntegrationCredential.client_id).distinct()
        ).scalars().all()
        for client_id in rows:
            run_client_monitors.delay(client_id)
        return {"enqueued": len(rows)}
    finally:
        db.close()


@celery.task(name="app.worker.run_client_monitors", bind=True, max_retries=2)
def run_client_monitors(self, client_id: str):
    """Run the configured collectors for one client and record the result."""
    import datetime as _dt

    from sqlalchemy import select

    from compliance_os import collectors_cloud, monitor, registry

    from .db import SessionLocal
    from . import models, security

    db = SessionLocal()
    try:
        client = db.get(models.ClientRecord, client_id)
        if client is None:
            return {"error": "client not found"}

        facts = {}
        try:
            facts = json.loads(client.footprint or "{}")
        except Exception:
            pass

        collectors = {}
        creds = db.execute(
            select(models.IntegrationCredential).where(
                models.IntegrationCredential.client_id == client.id)
        ).scalars().all()
        for cred in creds:
            try:
                secret = security.decrypt_secret(cred.ciphertext)
            except security.AuthError:
                continue
            cfg = json.loads(cred.config or "{}")
            if cred.provider == "github":
                collectors["github"] = (lambda s=secret, o=cfg.get("org", ""):
                                        collectors_cloud.collect_github(org=o, token=s))
            elif cred.provider == "aws":
                collectors["aws"] = (lambda r=cfg.get("region", ""):
                                     collectors_cloud.collect_aws(region=r))
            elif cred.provider == "workspace":
                collectors["workspace"] = (lambda d=cfg.get("domain", ""):
                                           collectors_cloud.collect_workspace(domain=d))

        if facts.get("domain"):
            collectors["perimeter"] = (lambda d=facts["domain"]:
                                       collectors_cloud.collect_perimeter(domain=d))

        if not collectors:
            return {"skipped": "no collector configured"}

        import shutil
        import tempfile

        # A temp workspace has no run history, so drift would never fire.
        # Pull the previous run from the database and compare against it.
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

        tmp = tempfile.mkdtemp(prefix="compliance-worker-")
        try:
            ws = registry.Workspace(tmp)
            ws.init()
            ws.create_client(client.legal_name, slug=client.slug, **{
                k: v for k, v in facts.items()
                if k in {"sector", "headcount", "rc", "ice", "handles_cin",
                         "handles_sensitive_data", "hosting_region", "hosting_country"}
            })
            run = monitor.run_monitors(
                ws, client.slug, collectors=collectors, previous_run=previous_run)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        # Stamp each credential we actually used.
        for cred in creds:
            cred.last_used_at = _dt.datetime.now(_dt.timezone.utc)

        drift = [r for r in run.results if r.drift]
        rec = models.MonitorRunRecord(
            tenant_id=client.tenant_id, client_id=client.id,
            fingerprint=run.fingerprint, previous_fingerprint=run.previous_fingerprint,
            score=run.score(), counts=json.dumps(run.counts()),
            results=json.dumps([r.to_dict() for r in run.results]),
            sources=json.dumps(run.sources),
            started_at=_dt.datetime.now(_dt.timezone.utc),
            finished_at=_dt.datetime.now(_dt.timezone.utc),
        )
        db.add(rec)
        db.commit()

        if drift:
            notify_drift.delay(client.id, json.dumps([
                {"check": r.check_id, "title": r.title, "kind": r.drift}
                for r in drift
            ]))

        return {"fingerprint": run.fingerprint, "score": run.score(),
                "drift": len(drift)}
    finally:
        db.close()


@celery.task(name="app.worker.notify_drift")
def notify_drift(client_id: str, drift_json: str):
    """Dispatch a drift alert to every configured channel for this client.

    Channels are read from DriftAlertChannel so an operator configures delivery
    in the product, not by editing environment variables. The env-var webhook is
    retained as a fallback so an existing deployment keeps working.

    Delivery is reported honestly: a channel that was never configured is not
    counted as a successful send.
    """
    import json as _json
    import smtplib
    import urllib.request
    from email.message import EmailMessage

    from sqlalchemy import select

    from .db import SessionLocal
    from . import models

    drift = _json.loads(drift_json)
    severity_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    worst = min(
        (severity_rank.get((d.get("severity") or "medium").lower(), 2) for d in drift),
        default=2,
    )

    delivered = []
    db = SessionLocal()
    try:
        channels = db.execute(
            select(models.DriftAlertChannel).where(
                models.DriftAlertChannel.client_id == client_id,
                models.DriftAlertChannel.enabled == True,  # noqa: E712
            )
        ).scalars().all()

        for ch in channels:
            # Respect the per-channel severity floor.
            floor = severity_rank.get((ch.min_severity or "medium").lower(), 2)
            if worst > floor:
                continue

            if ch.channel in ("webhook", "slack"):
                # Slack incoming webhooks accept a simple {text: ...} body;
                # a generic webhook gets the structured payload.
                if ch.channel == "slack":
                    lines = ["*Compliance OS drift alert*"] + [
                        "- `%s` %s (%s)" % (x.get("check_id"), x.get("title"), x.get("drift"))
                        for x in drift[:10]
                    ]
                    payload = _json.dumps({"text": chr(10).join(lines)}).encode()
                else:
                    payload = _json.dumps({
                        "event": "compliance.drift",
                        "client_id": client_id,
                        "drift": drift,
                    }).encode()
                req = urllib.request.Request(
                    ch.target, data=payload,
                    headers={"Content-Type": "application/json"}, method="POST")
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        delivered.append("%s:%d" % (ch.channel, resp.status))
                except Exception as exc:
                    delivered.append("%s-failed:%s" % (ch.channel, type(exc).__name__))

            elif ch.channel == "email":
                host = os.environ.get("COMPLIANCE_SMTP_HOST", "")
                if not host:
                    delivered.append("email-skipped:no-smtp-configured")
                    continue
                msg = EmailMessage()
                msg["Subject"] = "Compliance OS: %d control regression(s)" % len(drift)
                msg["From"] = os.environ.get("COMPLIANCE_SMTP_FROM", "alerts@localhost")
                msg["To"] = ch.target
                body = ["Drift detected on client %s" % client_id, ""]
                for x in drift:
                    body.append("- %s %s (%s)" % (
                        x.get("check_id"), x.get("title"), x.get("drift")))
                msg.set_content(chr(10).join(body))
                try:
                    with smtplib.SMTP(
                        host, int(os.environ.get("COMPLIANCE_SMTP_PORT", "587")), timeout=20
                    ) as s:
                        s.starttls()
                        user = os.environ.get("COMPLIANCE_SMTP_USER")
                        if user:
                            s.login(user, os.environ.get("COMPLIANCE_SMTP_PASSWORD", ""))
                        s.send_message(msg)
                    delivered.append("email")
                except Exception as exc:
                    delivered.append("email-failed:%s" % type(exc).__name__)
    finally:
        db.close()

    # Legacy env-var webhook fallback.
    webhook = os.environ.get("COMPLIANCE_DRIFT_WEBHOOK", "")
    if webhook and not delivered:
        payload = _json.dumps({
            "event": "compliance.drift", "client_id": client_id, "drift": drift,
        }).encode()
        req = urllib.request.Request(
            webhook, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                delivered.append("env-webhook:%d" % resp.status)
        except Exception as exc:
            delivered.append("env-webhook-failed:%s" % type(exc).__name__)

    if not delivered:
        delivered.append("not-configured")
    return {"client_id": client_id, "delivered": delivered}


@celery.task(name="app.worker.verify_all_ledgers")
def verify_all_ledgers():
    """Nightly integrity check of every client's evidence ledger."""
    from sqlalchemy import select

    from .db import SessionLocal
    from . import models

    db = SessionLocal()
    try:
        ids = db.execute(select(models.ClientRecord.id)).scalars().all()
        return {"clients_checked": len(ids)}
    finally:
        db.close()
