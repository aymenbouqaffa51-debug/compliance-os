"""Applicability resolution and scoring.

Two decisions worth understanding, because they are commercial decisions:

1. `not_applicable` is EXCLUDED from the denominator, not scored zero. A client
   who legitimately excludes controls is not punished for it. This makes the
   percentage defensible in front of an auditor.

2. A conditional control whose condition is unmet is auto-marked
   `not_applicable` with the reason recorded. That is what makes the same
   framework usable for two very different clients without hand-editing.

Condition evaluation is delegated to `safe_eval`, which uses a strict AST
whitelist instead of `eval()`. Framework files are data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from compliance_os.safe_eval import ConditionError, evaluate as safe_evaluate
from compliance_os.models import (
    STATE_NOT_APPLICABLE,
    STATE_NOT_ASSESSED,
    STATE_SCORE,
    STATE_LABEL,
    Control,
    Framework,
    Client,
    Assessment,
)

__all__ = [
    "ConditionError",
    "evaluate_condition",
    "applicability",
    "resolve",
    "score",
    "readiness_verdict",
    "Score",
]


def _client_ns(client: Client) -> Dict[str, Any]:
    """Expose client fields plus derived helpers used by conditions."""
    data = client.data
    try:
        data["headcount_num"] = int(
            "".join(ch for ch in str(client.headcount) if ch.isdigit()) or 0
        )
    except Exception:
        data["headcount_num"] = 0
    data["transfers_abroad"] = bool(client.export_markets)
    return data


def evaluate_condition(expr: str, client: Client) -> bool:
    """Evaluate a framework applicability condition against a client.

    Raises ConditionError for malformed or disallowed expressions.
    """
    if not expr or not expr.strip():
        return True
    return safe_evaluate(expr, _client_ns(client))


def applicability(fw: Framework, control: Control, client: Client) -> Tuple[bool, str]:
    """Return (applies, reason)."""
    if control.applicability == "all":
        return True, "always applicable"
    if control.applicability == "conditional":
        try:
            ok = evaluate_condition(control.condition, client)
        except ConditionError:
            # A condition that cannot be evaluated must never silently hide a
            # control. Surface it as applicable and flag it for attention.
            return True, "condition could not be evaluated: %s" % control.condition
        if ok:
            return True, "condition met: %s" % control.condition
        return False, "condition not met: %s" % control.condition
    return True, "unknown applicability %r, treated as applicable" % control.applicability


def resolve(fw: Framework, client: Client) -> List[Dict[str, Any]]:
    """Resolve which controls apply to this client, without mutating anything."""
    out = []
    for c in fw.controls:
        applies, reason = applicability(fw, c, client)
        out.append({"control": c, "applies": applies, "reason": reason})
    return out


class Score:
    def __init__(self) -> None:
        self.total = 0
        self.applicable = 0
        self.weight_applicable = 0.0
        self.weight_earned = 0.0
        self.by_state: Dict[str, int] = {}
        self.gaps: List[Dict[str, Any]] = []
        self.partials: List[Dict[str, Any]] = []
        self.unassessed: List[Dict[str, Any]] = []

    @property
    def pct(self) -> float:
        if self.weight_applicable <= 0:
            return 0.0
        return 100.0 * self.weight_earned / self.weight_applicable


def score(fw: Framework, client: Client, assessment: Assessment) -> Score:
    s = Score()
    for c in fw.controls:
        applies, reason = applicability(fw, c, client)
        s.total += 1
        if not applies:
            s.by_state[STATE_NOT_APPLICABLE] = s.by_state.get(STATE_NOT_APPLICABLE, 0) + 1
            continue
        s.applicable += 1
        row = assessment.rows.get(c.id)
        state = row.state if row else STATE_NOT_ASSESSED
        s.by_state[state] = s.by_state.get(state, 0) + 1
        contrib = STATE_SCORE.get(state)
        if contrib is None:
            # not_applicable chosen by the assessor: leaves the denominator.
            s.applicable -= 1
            s.by_state[STATE_NOT_APPLICABLE] = s.by_state.get(STATE_NOT_APPLICABLE, 0) + 1
            s.by_state[state] = max(0, s.by_state.get(state, 1) - 1)
            continue
        s.weight_applicable += c.weight
        s.weight_earned += c.weight * contrib
        entry = {
            "id": c.id,
            "title": c.title,
            "ref": c.ref,
            "theme": c.theme,
            "weight": c.weight,
            "state": state,
            "state_label": STATE_LABEL.get(state, state),
            "objective": c.objective,
            "evidence_expected": c.evidence,
            "notes": row.notes if row else "",
            "owner": row.owner if row else "",
            "due": row.due if row else "",
            "evidence_count": len(row.evidence) if row else 0,
        }
        if state == "gap":
            s.gaps.append(entry)
        elif state == "partial":
            s.partials.append(entry)
        elif state == STATE_NOT_ASSESSED:
            s.unassessed.append(entry)
    s.gaps.sort(key=lambda e: (-e["weight"], e["theme"], e["id"]))
    s.partials.sort(key=lambda e: (-e["weight"], e["theme"], e["id"]))
    s.unassessed.sort(key=lambda e: (-e["weight"], e["theme"], e["id"]))
    return s


def readiness_verdict(pct: float) -> str:
    if pct >= 90:
        return "audit-ready"
    if pct >= 70:
        return "near-ready"
    if pct >= 40:
        return "material gaps"
    return "early stage"
