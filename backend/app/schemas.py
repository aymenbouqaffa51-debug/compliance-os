"""Request/response models. Pydantic v2."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    tenant_id: str
    email: str
    totp_required: bool = False


class MeOut(BaseModel):
    id: str
    email: str
    role: str
    tenant_id: str
    tenant_name: str
    totp_enabled: bool


class TotpSetupOut(BaseModel):
    secret: str
    uri: str


class TotpVerifyIn(BaseModel):
    code: str


class ClientIn(BaseModel):
    legal_name: str = Field(min_length=2, max_length=255)
    slug: Optional[str] = None
    domain: str = ""
    sector: str = ""
    headcount: str = ""
    rc: str = ""
    ice: str = ""
    if_number: str = ""
    address: str = ""
    contact_name: str = ""
    contact_email: str = ""
    export_markets: List[str] = []
    handles_sensitive_data: bool = False
    handles_cin: bool = False
    is_public_entity: bool = False
    is_iiv: bool = False
    hosting_region: str = "eu-west-3"
    hosting_country: str = "France"


class ClientOut(BaseModel):
    id: str
    slug: str
    legal_name: str
    sector: str
    headcount: str
    rc: str
    ice: str
    created_at: str


class ControlStateIn(BaseModel):
    state: str
    notes: str = ""
    owner: str = ""
    due: str = ""


class ControlStateOut(BaseModel):
    control_id: str
    framework_id: str
    state: str
    notes: str
    owner: str
    due: str
    signed_off_by: str = ""
    evidence_count: int = 0


class FrameworkOut(BaseModel):
    id: str
    name: str
    version: str
    locale: str
    control_count: int


class ControlOut(BaseModel):
    id: str
    title: str
    ref: str
    theme: str
    objective: str
    weight: float
    applicability: str
    condition: str
    evidence: List[str]
    maps_to: List[str]


class ScoreOut(BaseModel):
    framework_id: str
    framework_name: str
    pct: float
    verdict: str
    applicable: int
    gaps: int
    partials: int
    unassessed: int
    excluded: int


class EvidenceIn(BaseModel):
    kind: str = "attestation"
    summary: str = ""
    source: str = ""


class EvidenceOut(BaseModel):
    id: str
    control_id: str
    kind: str
    summary: str
    source: str
    sha256: str
    collected_at: str


class IntegrationIn(BaseModel):
    provider: str
    secret: str
    config: Dict[str, Any] = {}


class IntegrationOut(BaseModel):
    provider: str
    config: Dict[str, Any]
    created_at: str
    last_used_at: Optional[str] = None


class MonitorResultOut(BaseModel):
    check_id: str
    title: str
    outcome: str
    severity: str
    observed: Optional[Any] = None
    message: str = ""
    drift: str = ""
    controls: List[str] = []


class MonitorRunOut(BaseModel):
    fingerprint: str
    score: float
    counts: Dict[str, int]
    sources: List[str]
    started_at: str
    finished_at: str
    results: List[MonitorResultOut] = []


class AuditorShareIn(BaseModel):
    label: str = ""
    hours: int = 72


class AuditorShareOut(BaseModel):
    token: str
    url: str
    expires_at: str


class AuditLogOut(BaseModel):
    action: str
    object_type: str
    object_id: str
    actor_email: str
    created_at: str

class QuestionnaireAnswerPatch(BaseModel):
    row: int
    draft: str
    confidence: Optional[str] = None


class PolicyPublishIn(BaseModel):
    policy_id: str
    language: str = "fr"
    requires_acknowledgement: bool = True


class AcknowledgeIn(BaseModel):
    person_email: EmailStr
    person_name: str = ""
    method: str = "web"


class DriftChannelIn(BaseModel):
    channel: str
    target: str
    min_severity: str = "medium"

class AgentAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    polish: bool = False


class AgentCitationOut(BaseModel):
    kind: str
    ref: str
    label: str = ""


class AgentAnswerOut(BaseModel):
    text: str
    citations: List[AgentCitationOut] = []
    intent: str = "unknown"
    grounded: bool = True
    follow_ups: List[str] = []
    used_llm: bool = False
