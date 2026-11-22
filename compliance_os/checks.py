"""Automated check and drift engine.

This is the layer that turns Compliance OS from a checklist into continuous
monitoring. It sits between a collector (which produces raw observations) and a
control (which a human signs off).

The pipeline is deliberately three-stage:

    collector  ->  Observation      (facts, with provenance)
    checks.py  ->  CheckResult      (PASS / FAIL / ERROR / NOT_APPLICABLE)
    human      ->  control state    (the only thing an auditor will accept)

A check NEVER writes a control state. It produces evidence that a human reviews.
That separation is what makes the output defensible: an auditor asks "who
decided this control passes?" and the answer is a named person, not a script.

Drift detection compares the current CheckResult against the previous run for
the same client+check. A transition PASS -> FAIL is drift. That is the alert a
client actually pays for: they fixed it, then it broke again.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import operator
import os
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import yaml

CHECKS_DIR = os.path.join(os.path.dirname(__file__), "data", "checks")


# ---------------------------------------------------------------- outcomes
PASS = "PASS"
FAIL = "FAIL"
ERROR = "ERROR"
NOT_APPLICABLE = "NOT_APPLICABLE"
SKIPPED = "SKIPPED"

OUTCOMES = [PASS, FAIL, ERROR, NOT_APPLICABLE, SKIPPED]

# Drift transitions worth alerting on. PASS->FAIL is the expensive one.
DRIFT_TRANSITIONS = {
    (PASS, FAIL): "regression",
    (PASS, ERROR): "lost_visibility",
    (NOT_APPLICABLE, FAIL): "newly_applicable",
    (SKIPPED, FAIL): "newly_measured",
}


class CheckError(Exception):
    pass


# ---------------------------------------------------------------- operators
# A closed set. A check rule cannot express arbitrary Python.
_OPERATORS = {
    "eq": operator.eq,
    "ne": operator.ne,
    "gt": operator.gt,
    "gte": operator.ge,
    "lt": operator.lt,
    "lte": operator.le,
    "in": lambda a, b: a in b,
    "not_in": lambda a, b: a not in b,
    "contains": lambda a, b: b in a,
    "not_contains": lambda a, b: b not in a,
    "is_true": lambda a, _b=None: a is True,
    "is_false": lambda a, _b=None: a is False,
    "exists": lambda a, _b=None: a is not None,
    "not_exists": lambda a, _b=None: a is None,
    "matches": lambda a, b: bool(re.search(str(b), str(a))),
    "len_gte": lambda a, b: len(a) >= b,
    "len_lte": lambda a, b: len(a) <= b,
    "len_eq": lambda a, b: len(a) == b,
    "all_true": lambda a, _b=None: bool(a) and all(a) if isinstance(a, (list, tuple)) else False,
    "none_true": lambda a, _b=None: not any(a) if isinstance(a, (list, tuple)) else False,
    "version_gte": lambda a, b: _version_ge(str(a), str(b)),
}


# Operators whose semantic is "is this fact true/false". A None value for any of
# these means UNKNOWN, not false.
_BOOLEAN_OPERATORS = {
    "is_true",
    "is_false",
    "exists",
    "not_exists",
    "all_true",
    "none_true",
}


def _version_ge(actual: str, required: str) -> bool:
    """Compare dotted versions numerically.

    Handles the shapes the perimeter collector actually produces:
      '1.10'    >= '1.2'    -> True   (numeric, not lexical)
      'TLSv1.3' >= '1.2'    -> True   (prefix stripped)
      'TLSv1.1' >= '1.2'    -> False
      '1.2.3'   >= '1.2'    -> True   (missing components treated as 0)

    Strategy: pull every digit run out of the string in order, so a protocol
    prefix like 'TLSv' cannot make the leading component look like 0.
    """
    def parts(v: str) -> List[int]:
        # Split on dots/hyphens/plus first, then take the leading digits of each
        # chunk; if a chunk has no digits (e.g. 'TLSv1'), fall back to any digit
        # run inside it so 'TLSv1.3' becomes [1, 3] rather than [0, 3].
        out: List[int] = []
        for chunk in re.split(r"[.\-+]", v.strip()):
            chunk = chunk.strip()
            if not chunk:
                continue
            m = re.match(r"^(\d+)", chunk)
            if m:
                out.append(int(m.group(1)))
            else:
                inner = re.findall(r"\d+", chunk)
                out.extend(int(x) for x in inner)
        return out or [0]
    a, b = parts(actual), parts(required)
    n = max(len(a), len(b))
    a += [0] * (n - len(a))
    b += [0] * (n - len(b))
    return a >= b


# ---------------------------------------------------------------- observation
@dataclass
class Observation:
    """A fact produced by a collector, with provenance.

    `values` is a flat-ish dict of facts, e.g.
        {"org_mfa_enforced": True, "org_mfa_enforced_pct": 100}
    Nested dicts are addressable with dotted paths in a check's `field`.
    """

    source: str                      # github | aws | workspace | perimeter | manual
    collected_at: str = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    values: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)

    def get(self, path: str, default: Any = None) -> Any:
        """Resolve 'a.b.c' against values, then fall back to meta."""
        for root in (self.values, self.meta):
            cur: Any = root
            ok = True
            for part in path.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    ok = False
                    break
            if ok:
                return cur
        return default

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Observation":
        return cls(
            source=d.get("source", "unknown"),
            collected_at=d.get("collected_at", ""),
            values=d.get("values", {}),
            errors=d.get("errors", []),
            meta=d.get("meta", {}),
        )


# -------------------------------------------------------------------- check
@dataclass
class Check:
    """One automated test against an observation."""

    id: str
    title: str
    source: str                    # which collector feeds it
    field: str                     # dotted path into Observation.values
    operator: str                  # key into _OPERATORS
    value: Any = None
    severity: str = "medium"       # critical | high | medium | low
    controls: List[str] = field(default_factory=list)   # control ids this evidences
    maps_to: List[str] = field(default_factory=list)    # cross-framework ids
    remediation: str = ""
    rationale: str = ""
    frameworks: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Check":
        op = d.get("operator", "eq")
        if op not in _OPERATORS:
            raise CheckError(
                "check %r uses unknown operator %r (allowed: %s)"
                % (d.get("id"), op, ", ".join(sorted(_OPERATORS)))
            )
        return cls(
            id=d["id"],
            title=d.get("title", d["id"]),
            source=d["source"],
            field=d["field"],
            operator=op,
            value=d.get("value"),
            severity=d.get("severity", "medium"),
            controls=d.get("controls", []),
            maps_to=d.get("maps_to", []),
            remediation=d.get("remediation", ""),
            rationale=d.get("rationale", ""),
            frameworks=d.get("frameworks", []),
        )


_cache: Dict[str, List[Check]] = {}


def check_files() -> List[str]:
    if not os.path.isdir(CHECKS_DIR):
        return []
    return sorted(f for f in os.listdir(CHECKS_DIR) if f.endswith((".yaml", ".yml")))


def load_checks() -> List[Check]:
    """Load every check definition from data/checks/*.yaml."""
    if "_all" in _cache:
        return _cache["_all"]
    out: List[Check] = []
    seen = set()
    for fn in check_files():
        path = os.path.join(CHECKS_DIR, fn)
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        # `source` and `collector` are declared once per file and inherited by
        # every check in it, so a check cannot drift from its file's source.
        file_source = data.get("source")
        if not file_source:
            raise CheckError("%s does not declare a top-level `source`" % fn)
        for raw in data.get("checks", []):
            raw = dict(raw)
            raw.setdefault("source", file_source)
            if "id" not in raw:
                raise CheckError("a check in %s has no id" % fn)
            chk = Check.from_dict(raw)
            if chk.id in seen:
                raise CheckError("duplicate check id %r in %s" % (chk.id, fn))
            seen.add(chk.id)
            out.append(chk)
    out.sort(key=lambda c: (c.source, c.id))
    _cache["_all"] = out
    return out


def reload_checks() -> None:
    _cache.clear()


def checks_for_source(source: str) -> List[Check]:
    return [c for c in load_checks() if c.source == source]


# ------------------------------------------------------------------- result
@dataclass
class CheckResult:
    check_id: str
    title: str
    outcome: str
    severity: str
    observed: Any = None
    expected: Any = None
    operator: str = ""
    message: str = ""
    remediation: str = ""
    controls: List[str] = field(default_factory=list)
    maps_to: List[str] = field(default_factory=list)
    source: str = ""
    collected_at: str = ""
    drift: str = ""          # "" | regression | lost_visibility | newly_applicable | newly_measured
    previous_outcome: str = ""

    @property
    def is_pass(self) -> bool:
        return self.outcome == PASS

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "CheckResult":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


# ------------------------------------------------------------------ evaluate
def evaluate_check(check: Check, observation: Observation) -> CheckResult:
    """Evaluate one check against one observation.

    Missing field -> NOT_APPLICABLE, not FAIL. A check whose data source did not
    report a fact has not failed; it simply has no opinion. Conflating those two
    is how monitoring systems become noise that clients ignore.
    """
    base = CheckResult(
        check_id=check.id,
        title=check.title,
        outcome=NOT_APPLICABLE,
        severity=check.severity,
        operator=check.operator,
        expected=check.value,
        remediation=check.remediation,
        controls=list(check.controls),
        maps_to=list(check.maps_to),
        source=check.source,
        collected_at=observation.collected_at,
    )

    if observation.source != check.source:
        base.message = "observation source %r does not match check source %r" % (
            observation.source, check.source)
        base.outcome = SKIPPED
        return base

    sentinel = object()
    actual = observation.get(check.field, sentinel)
    if actual is sentinel:
        base.message = "fact %r was not reported by %s" % (check.field, check.source)
        base.outcome = NOT_APPLICABLE
        return base

    base.observed = actual

    # `None` means the collector ran but could not determine the fact.
    #
    # For a boolean operator that is NOT a failure: we have no opinion. Treating
    # it as FAIL would report AWS-07 ("CloudTrail log bucket is public") as
    # failing for every client whose bucket we lack permission to read -- a
    # false accusation in an audit dossier. NOT_APPLICABLE is the honest answer.
    if actual is None and check.operator in (_BOOLEAN_OPERATORS):
        base.outcome = NOT_APPLICABLE
        base.message = "%s was reported as unknown (None); no opinion" % check.field
        return base

    fn = _OPERATORS.get(check.operator)
    if fn is None:  # pragma: no cover - prevented at load time
        base.outcome = ERROR
        base.message = "unknown operator %r" % check.operator
        return base

    try:
        passed = bool(fn(actual, check.value))
    except TypeError as exc:
        base.outcome = ERROR
        base.message = "type error comparing %r %s %r: %s" % (
            actual, check.operator, check.value, exc)
        return base
    except Exception as exc:  # pragma: no cover - defensive
        base.outcome = ERROR
        base.message = "evaluation error: %s" % exc
        return base

    base.outcome = PASS if passed else FAIL
    base.message = (
        "%s %s %r (observed %r)" % (check.field, check.operator, check.value, actual)
        if not passed
        else "%s %s %r (observed %r)" % (check.field, check.operator, check.value, actual)
    )
    return base


def evaluate_all(observation: Observation, checks: Optional[List[Check]] = None) -> List[CheckResult]:
    """Evaluate every check that belongs to this observation's source."""
    pool = checks if checks is not None else checks_for_source(observation.source)
    return [evaluate_check(c, observation) for c in pool]


# --------------------------------------------------------------------- drift
def detect_drift(current: List[CheckResult], previous: List[CheckResult]) -> List[CheckResult]:
    """Annotate current results with drift vs the previous run.

    Returns the same list, mutated with `drift` and `previous_outcome` set.
    """
    prior = {p.check_id: p.outcome for p in previous}
    for r in current:
        prev = prior.get(r.check_id)
        if prev is None:
            continue
        r.previous_outcome = prev
        if prev == r.outcome:
            continue
        kind = DRIFT_TRANSITIONS.get((prev, r.outcome))
        if kind:
            r.drift = kind
    return current


def drift_summary(results: List[CheckResult]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in results:
        if r.drift:
            out[r.drift] = out.get(r.drift, 0) + 1
    return out


# --------------------------------------------------------------- run ledger
def run_fingerprint(results: List[CheckResult]) -> str:
    """SHA-256 over the deterministic content of a run.

    This is what makes the evidence ledger tamper-evident: each run's hash can be
    chained to the previous one, so deleting or editing a historical run breaks
    the chain.
    """
    payload = json.dumps(
        sorted(
            [{"id": r.check_id, "outcome": r.outcome, "observed": str(r.observed)} for r in results],
            key=lambda x: x["id"],
        ),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass
class CheckRun:
    """One execution of a check set against a set of observations."""

    client_slug: str
    started_at: str = field(default_factory=lambda: _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    finished_at: str = ""
    results: List[CheckResult] = field(default_factory=list)
    fingerprint: str = ""
    previous_fingerprint: str = ""
    sources: List[str] = field(default_factory=list)

    def counts(self) -> Dict[str, int]:
        out: Dict[str, int] = {k: 0 for k in OUTCOMES}
        for r in self.results:
            out[r.outcome] = out.get(r.outcome, 0) + 1
        return out

    def score(self) -> float:
        """Percentage of decisive checks that pass.

        NOT_APPLICABLE and SKIPPED are excluded from the denominator for the same
        reason not_applicable controls are: a check with no data must not drag a
        client's score down.
        """
        decisive = [r for r in self.results if r.outcome in (PASS, FAIL)]
        if not decisive:
            return 0.0
        return 100.0 * sum(1 for r in decisive if r.outcome == PASS) / len(decisive)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "client_slug": self.client_slug,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "fingerprint": self.fingerprint,
            "previous_fingerprint": self.previous_fingerprint,
            "sources": self.sources,
            "counts": self.counts(),
            "score": self.score(),
            "results": [r.to_dict() for r in self.results],
        }


# --------------------------------------------------------- evidence helpers
def results_to_evidence(results: List[CheckResult], limit: int = 5) -> Dict[str, Dict[str, Any]]:
    """Summarise results per control id, for attaching to an assessment row.

    Returns {control_id: {pass: n, fail: n, total: n, worst: severity}}.
    Only observations, never a verdict -- the human sets the control state.
    """
    out: Dict[str, Dict[str, Any]] = {}
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for r in results:
        for cid in r.controls:
            slot = out.setdefault(cid, {"pass": 0, "fail": 0, "error": 0, "total": 0, "worst": ""})
            slot["total"] += 1
            if r.outcome == PASS:
                slot["pass"] += 1
            elif r.outcome == FAIL:
                slot["fail"] += 1
                if not slot["worst"] or rank.get(r.severity, 9) < rank.get(slot["worst"], 9):
                    slot["worst"] = r.severity
            elif r.outcome == ERROR:
                slot["error"] += 1
    return out
