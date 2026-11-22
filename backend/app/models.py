"""SQLAlchemy models for the multi-tenant platform.

Tenancy model: every row that holds client data carries a tenant_id. Every
query in the routers filters on the authenticated user's tenant. There is no
cross-tenant read path except for platform_admin, which is explicit.

The audit_logs table is hash-chained: each row's hash covers the previous row's
hash plus its own content, so editing or deleting history is detectable.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import uuid

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")


# Roles, in ascending order of privilege within a tenant.
ROLE_PLATFORM_ADMIN = "platform_admin"
ROLE_CONSULTANT = "consultant"
ROLE_CLIENT_ADMIN = "client_admin"
ROLE_CLIENT_MEMBER = "client_member"
ROLE_EXTERNAL_AUDITOR = "external_auditor"

ROLES = [
    ROLE_PLATFORM_ADMIN,
    ROLE_CONSULTANT,
    ROLE_CLIENT_ADMIN,
    ROLE_CLIENT_MEMBER,
    ROLE_EXTERNAL_AUDITOR,
]

# Roles allowed to mutate control state. An external auditor never can.
WRITE_ROLES = {ROLE_PLATFORM_ADMIN, ROLE_CONSULTANT, ROLE_CLIENT_ADMIN}


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(40), default=ROLE_CLIENT_MEMBER)
    totp_secret: Mapped[str] = mapped_column(String(64), default="")
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped[Tenant] = relationship(back_populates="users")


class ClientRecord(Base):
    """Mirror of the CLI workspace client, so the API and CLI share a model."""

    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_client_slug"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str] = mapped_column(String(120), default="")
    headcount: Mapped[str] = mapped_column(String(40), default="")
    rc: Mapped[str] = mapped_column(String(80), default="")
    ice: Mapped[str] = mapped_column(String(80), default="")
    footprint: Mapped[str] = mapped_column(Text, default="{}")   # JSON of client facts
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)

    assessments: Mapped[list["ControlState"]] = relationship(back_populates="client")


class ControlState(Base):
    """State of one control for one client. Evidence lives in EvidenceRecord."""

    __tablename__ = "control_states"
    __table_args__ = (
        UniqueConstraint("client_id", "framework_id", "control_id", name="uq_control_state"),
        Index("ix_control_client_fw", "client_id", "framework_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    framework_id: Mapped[str] = mapped_column(String(80), nullable=False)
    control_id: Mapped[str] = mapped_column(String(40), nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="not_assessed")
    notes: Mapped[str] = mapped_column(Text, default="")
    owner: Mapped[str] = mapped_column(String(120), default="")
    due: Mapped[str] = mapped_column(String(40), default="")
    signed_off_by: Mapped[str] = mapped_column(String(320), default="")
    signed_off_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    client: Mapped[ClientRecord] = relationship(back_populates="assessments")


class EvidenceRecord(Base):
    """An evidence item. Stores hashes and metadata, never document contents."""

    __tablename__ = "evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    control_id: Mapped[str] = mapped_column(String(40), index=True)
    framework_id: Mapped[str] = mapped_column(String(80), default="")
    kind: Mapped[str] = mapped_column(String(40), default="attestation")
    summary: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(255), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    collector: Mapped[str] = mapped_column(String(60), default="")
    collected_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    meta: Mapped[str] = mapped_column(Text, default="{}")


class IntegrationCredential(Base):
    """Encrypted credential for a read-only integration.

    The secret is Fernet-encrypted with a key derived from COMPLIANCE_SECRET_KEY.
    It is never returned by any endpoint, and never logged.
    """

    __tablename__ = "integration_credentials"
    __table_args__ = (UniqueConstraint("client_id", "provider", name="uq_integration"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(40), nullable=False)  # github | aws | workspace
    ciphertext: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[str] = mapped_column(Text, default="{}")  # non-secret config e.g. org name
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_used_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MonitorRunRecord(Base):
    __tablename__ = "monitor_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    previous_fingerprint: Mapped[str] = mapped_column(String(64), default="")
    score: Mapped[float] = mapped_column(default=0.0)
    counts: Mapped[str] = mapped_column(Text, default="{}")
    results: Mapped[str] = mapped_column(Text, default="[]")
    sources: Mapped[str] = mapped_column(Text, default="[]")
    started_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[_dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    """Hash-chained audit log. Append-only by convention; the chain detects edits."""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(String(32), default="")
    actor_email: Mapped[str] = mapped_column(String(320), default="")
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(60), default="")
    object_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[str] = mapped_column(Text, default="{}")
    ip: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    previous_hash: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64), default="")

    @staticmethod
    def compute_hash(previous_hash: str, payload: dict) -> str:
        body = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256((previous_hash + body).encode("utf-8")).hexdigest()


class Questionnaire(Base):
    """An uploaded buyer security questionnaire and its drafted answers.

    The uploaded file is PARSED AND DISCARDED -- only the extracted questions
    and the drafted answers are stored. Warehousing a customer's vendor
    questionnaire would mean holding a third party's document under no
    processing agreement, which is exactly what Law 09-08 art. 12 is about.
    """

    __tablename__ = "questionnaires"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    source_file: Mapped[str] = mapped_column(String(255), default="")
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    counts: Mapped[str] = mapped_column(Text, default="{}")          # JSON
    answers: Mapped[str] = mapped_column(Text, default="[]")         # JSON list
    file_sha256: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(30), default="drafted")
    created_by: Mapped[str] = mapped_column(String(320), default="")
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class PolicyDocument(Base):
    """A published, versioned policy that employees must acknowledge."""

    __tablename__ = "policy_documents"
    __table_args__ = (UniqueConstraint("client_id", "policy_id", "version", name="uq_policy_version"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    policy_id: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    language: Mapped[str] = mapped_column(String(5), default="fr")
    body: Mapped[str] = mapped_column(Text, default="")
    controls: Mapped[str] = mapped_column(Text, default="[]")        # JSON list
    content_sha256: Mapped[str] = mapped_column(String(64), default="")
    published_by: Mapped[str] = mapped_column(String(320), default="")
    published_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_acknowledgement: Mapped[bool] = mapped_column(Boolean, default=True)


class PolicyAcknowledgement(Base):
    """One person accepting one policy version, with a timestamp.

    This is the evidence. An unsigned policy is a document, not a control.
    """

    __tablename__ = "policy_acknowledgements"
    __table_args__ = (
        UniqueConstraint("policy_document_id", "person_email", name="uq_policy_ack"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    policy_document_id: Mapped[str] = mapped_column(
        ForeignKey("policy_documents.id", ondelete="CASCADE"), index=True)
    person_email: Mapped[str] = mapped_column(String(320), nullable=False)
    person_name: Mapped[str] = mapped_column(String(200), default="")
    acknowledged_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ip: Mapped[str] = mapped_column(String(64), default="")
    method: Mapped[str] = mapped_column(String(30), default="web")


class DriftAlertChannel(Base):
    """Per-client notification target for PASS->FAIL regressions."""

    __tablename__ = "drift_alert_channels"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(30), nullable=False)   # webhook | slack | email
    target: Mapped[str] = mapped_column(Text, nullable=False)          # URL or address
    min_severity: Mapped[str] = mapped_column(String(20), default="medium")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditorShare(Base):
    """A time-boxed, read-only link for an external auditor."""

    __tablename__ = "auditor_shares"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id", ondelete="CASCADE"), index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(200), default="")
    expires_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[_dt.datetime] = mapped_column(DateTime(timezone=True), default=_now)
