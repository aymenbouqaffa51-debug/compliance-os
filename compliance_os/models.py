"""Core data model.

Design note: an ASSESSMENT is per-client and per-framework. A CONTROL is
immutable reference data loaded from a framework file. The two are joined by
control id. Evidence attaches to an assessment row, never to the control, so
that the same control can be evidenced differently for two clients.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# Maturity states, in ascending order. Not every state applies to every control.
STATE_NOT_ASSESSED = "not_assessed"
STATE_NOT_APPLICABLE = "not_applicable"
STATE_GAP = "gap"
STATE_PARTIAL = "partial"
STATE_IMPLEMENTED = "implemented"

STATES = [
    STATE_NOT_ASSESSED,
    STATE_NOT_APPLICABLE,
    STATE_GAP,
    STATE_PARTIAL,
    STATE_IMPLEMENTED,
]

# Score contribution per state (0-1). not_applicable is excluded from the
# denominator rather than scored as zero -- this matters commercially: a client
# who legitimately excludes controls should not be punished for it.
STATE_SCORE = {
    STATE_NOT_ASSESSED: 0.0,
    STATE_NOT_APPLICABLE: None,
    STATE_GAP: 0.0,
    STATE_PARTIAL: 0.5,
    STATE_IMPLEMENTED: 1.0,
}

STATE_LABEL = {
    STATE_NOT_ASSESSED: "Not assessed",
    STATE_NOT_APPLICABLE: "Not applicable",
    STATE_GAP: "Gap",
    STATE_PARTIAL: "Partial",
    STATE_IMPLEMENTED: "Implemented",
}

# Bumped when the persisted JSON shape changes. Readers must check this and
# refuse to silently misread an older workspace.
SCHEMA_VERSION = 2

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Control:
    """A single requirement from a framework. Immutable reference data."""

    id: str
    title: str
    ref: str = ""
    theme: str = ""
    objective: str = ""
    evidence: List[str] = field(default_factory=list)
    maps_to: List[str] = field(default_factory=list)
    applicability: str = "all"  # all | conditional
    condition: str = ""
    weight: float = 1.0
    guidance: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Control":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Framework:
    id: str
    name: str
    version: str = ""
    locale: str = "en"
    authority: str = ""
    source_url: str = ""
    description: str = ""
    disclaimer: str = ""
    controls: List[Control] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Framework":
        ctrls = [Control.from_dict(c) for c in d.get("controls", [])]
        return cls(
            id=d["id"],
            name=d["name"],
            version=d.get("version", ""),
            locale=d.get("locale", "en"),
            authority=d.get("authority", ""),
            source_url=d.get("source_url", ""),
            description=d.get("description", ""),
            disclaimer=d.get("disclaimer", ""),
            controls=ctrls,
        )

    def by_id(self, cid: str) -> Optional[Control]:
        for c in self.controls:
            if c.id == cid:
                return c
        return None


@dataclass
class EvidenceItem:
    kind: str                      # manual | command | file | url | attestation
    collected_at: str = field(default_factory=_now)
    source: str = ""
    summary: str = ""
    sha256: str = ""
    path: str = ""
    command: str = ""
    output_excerpt: str = ""
    collector: str = ""
    status: str = "ok"            # ok | failed | skipped
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssessedControl:
    control_id: str
    state: str = STATE_NOT_ASSESSED
    notes: str = ""
    owner: str = ""
    due: str = ""
    evidence: List[EvidenceItem] = field(default_factory=list)
    assessed_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence"] = [e.to_dict() for e in self.evidence]
        return d

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AssessedControl":
        ev = [EvidenceItem(**e) for e in d.get("evidence", [])]
        return cls(
            control_id=d["control_id"],
            state=d.get("state", STATE_NOT_ASSESSED),
            notes=d.get("notes", ""),
            owner=d.get("owner", ""),
            due=d.get("due", ""),
            evidence=ev,
            assessed_at=d.get("assessed_at", ""),
        )


@dataclass
class Client:
    """A client workspace. Persisted as client.json."""

    slug: str
    legal_name: str
    created_at: str = field(default_factory=_now)
    sector: str = ""
    headcount: str = ""
    contact_name: str = ""
    contact_email: str = ""
    export_markets: List[str] = field(default_factory=list)
    # Legal identity -- required to render DPA / SCC / declarez-moi templates
    # without manual editing. `rc` is the registre de commerce number, `ice` the
    # identifiant commun de l'entreprise.
    rc: str = ""
    ice: str = ""
    if_number: str = ""
    address: str = ""
    signatory_title: str = ""
    hosting_region: str = "eu-west-3"
    hosting_country: str = "France"
    # Things that change which controls apply
    handles_personal_data: bool = True
    handles_sensitive_data: bool = False   # CNDP art.1 sensitive categories
    handles_cin: bool = False              # triggers CNDP art.12 prior authorisation
    is_public_entity: bool = False         # Law 05-20 art.1 entity
    is_iiv: bool = False                   # vital infrastructure -> out of scope for us
    hosts_within_morocco: bool = False
    has_cloud: bool = True
    has_source_code: bool = True
    has_employees: bool = True
    engagement: str = "readiness_check"    # readiness_check | readiness_program | retainer
    notes: str = ""

    @property
    def data(self) -> Dict[str, Any]:
        out = asdict(self)
        out["schema_version"] = SCHEMA_VERSION
        return out

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Client":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Assessment:
    client_slug: str
    framework_id: str
    rows: Dict[str, AssessedControl] = field(default_factory=dict)
    started_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    assessor: str = ""

    def row(self, cid: str) -> AssessedControl:
        if cid not in self.rows:
            self.rows[cid] = AssessedControl(control_id=cid)
        return self.rows[cid]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "client_slug": self.client_slug,
            "framework_id": self.framework_id,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "assessor": self.assessor,
            "rows": {k: v.to_dict() for k, v in self.rows.items()},
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Assessment":
        a = cls(
            client_slug=d["client_slug"],
            framework_id=d["framework_id"],
            started_at=d.get("started_at", _now()),
            updated_at=d.get("updated_at", _now()),
            assessor=d.get("assessor", ""),
        )
        for k, v in d.get("rows", {}).items():
            a.rows[k] = AssessedControl.from_dict(v)
        return a


def new_id() -> str:
    return uuid.uuid4().hex[:12]
