"""Monitor runner: orchestrate collectors, evaluate checks, persist runs.

This is the module a scheduler calls. It owns no business logic of its own --
it wires the collectors to the check engine and stores the result durably, in a
hash chain.

The chain matters: each run stores `previous_fingerprint`, so an operator who
deletes a run to hide a regression breaks the chain and that is detectable.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Callable, Dict, List, Optional

from compliance_os import checks as check_engine
from compliance_os import registry
from compliance_os.checks import CheckResult, CheckRun, Observation

MONITOR_DIR = "monitors"


def _monitor_dir(ws: registry.Workspace, slug: str) -> str:
    d = os.path.join(ws.client_dir(slug), MONITOR_DIR)
    os.makedirs(d, exist_ok=True)
    return d


def runs_path(ws: registry.Workspace, slug: str) -> str:
    return os.path.join(_monitor_dir(ws, slug), "runs.json")


def observations_path(ws: registry.Workspace, slug: str) -> str:
    return os.path.join(_monitor_dir(ws, slug), "observations.json")


def ledger_path(ws: registry.Workspace, slug: str) -> str:
    return os.path.join(_monitor_dir(ws, slug), "ledger.jsonl")


# ------------------------------------------------------------- persistence
def load_runs(ws: registry.Workspace, slug: str) -> List[Dict[str, Any]]:
    p = runs_path(ws, slug)
    if not os.path.isfile(p):
        return []
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return []


def save_runs(ws: registry.Workspace, slug: str, runs: List[Dict[str, Any]]) -> None:
    registry.atomic_write_json(runs_path(ws, slug), runs)


def latest_run(ws: registry.Workspace, slug: str) -> Optional[Dict[str, Any]]:
    runs = load_runs(ws, slug)
    return runs[-1] if runs else None


def append_ledger(ws: registry.Workspace, slug: str, record: Dict[str, Any]) -> None:
    """Append one JSON line to the hash-chained ledger.

    Chain construction: the hash covers the record body *including* its
    `previous_hash`, prefixed by the previous record's hash. Verification
    recomputes exactly that, so editing any field -- or reordering or deleting a
    record -- breaks the chain at a detectable index.

    Appending is not atomic in the same way a rewrite is; a torn final line is
    tolerated on read. The chain field is what provides integrity.
    """
    import hashlib
    p = ledger_path(ws, slug)
    prev = last_ledger_hash(ws, slug)
    body = dict(record)
    body["previous_hash"] = prev
    payload = json.dumps(body, sort_keys=True, ensure_ascii=False)
    body["hash"] = hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(body, sort_keys=True, ensure_ascii=False) + chr(10))
        f.flush()
        os.fsync(f.fileno())


def load_ledger(ws: registry.Workspace, slug: str) -> List[Dict[str, Any]]:
    p = ledger_path(ws, slug)
    if not os.path.isfile(p):
        return []
    out = []
    for line in open(p, encoding="utf-8", errors="ignore"):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            break  # torn write; stop at the last intact record
    return out


def last_ledger_hash(ws: registry.Workspace, slug: str) -> str:
    recs = load_ledger(ws, slug)
    return recs[-1].get("hash", "") if recs else ""


def verify_ledger(ws: registry.Workspace, slug: str) -> Dict[str, Any]:
    """Recompute the hash chain. Returns {ok, records, broken_at, reason}.

    Works on a shallow copy of each record so callers can still inspect the
    ledger afterwards.
    """
    import hashlib
    recs = load_ledger(ws, slug)
    prev = ""
    for i, original in enumerate(recs):
        rec = dict(original)
        claimed = rec.pop("hash", "")
        if rec.get("previous_hash", "") != prev:
            return {"ok": False, "records": len(recs), "broken_at": i,
                    "reason": "previous_hash mismatch at record %d" % i}
        payload = json.dumps(rec, sort_keys=True, ensure_ascii=False)
        recomputed = hashlib.sha256((prev + payload).encode("utf-8")).hexdigest()
        if recomputed != claimed:
            return {"ok": False, "records": len(recs), "broken_at": i,
                    "reason": "record hash mismatch at record %d" % i}
        prev = claimed
    return {"ok": True, "records": len(recs), "broken_at": None, "reason": ""}


def save_observations(ws: registry.Workspace, slug: str, obs: Dict[str, Observation]) -> None:
    registry.atomic_write_json(
        observations_path(ws, slug),
        {k: v.to_dict() for k, v in obs.items()},
    )


def load_observations(ws: registry.Workspace, slug: str) -> Dict[str, Observation]:
    p = observations_path(ws, slug)
    if not os.path.isfile(p):
        return {}
    try:
        raw = json.load(open(p, encoding="utf-8"))
        return {k: Observation.from_dict(v) for k, v in raw.items()}
    except Exception:
        return {}


# ------------------------------------------------------------------- run
def run_monitors(
    ws: registry.Workspace,
    slug: str,
    collectors: Optional[Dict[str, Callable[[], Observation]]] = None,
    sources: Optional[List[str]] = None,
    previous_run: Optional[Dict[str, Any]] = None,
) -> CheckRun:
    """Execute collectors, evaluate checks, detect drift, persist.

    `collectors` maps a source name to a zero-argument callable returning an
    Observation. The CLI builds this from environment configuration; tests pass
    synthetic callables. Anything not provided is simply not run, and its checks
    resolve NOT_APPLICABLE rather than FAIL.

    `previous_run` is the prior run as a dict, for drift comparison. The API and
    Celery worker pass the last MonitorRunRecord from the database here, because
    they execute against a throwaway temp workspace that has no run history on
    disk. Without it, drift detection silently never fires in the platform --
    only the CLI, which keeps a real workspace, would ever see a regression.
    """
    ws.load_client(slug)  # raises if unknown

    run = CheckRun(client_slug=slug)
    collected: Dict[str, Observation] = {}

    pool = collectors or {}
    wanted = sources if sources is not None else list(pool.keys())

    for source in wanted:
        fn = pool.get(source)
        if fn is None:
            continue
        try:
            obs = fn()
        except Exception as exc:  # a collector crash must not abort the run
            obs = Observation(source=source, errors=["collector raised %s" % type(exc).__name__])
        collected[source] = obs
        run.results.extend(check_engine.evaluate_all(obs))
        if source not in run.sources:
            run.sources.append(source)

    # Checks belonging to a source we did not run must still be visible as
    # NOT_APPLICABLE, otherwise the UI silently under-reports coverage.
    ran = set(run.sources)
    present = {r.check_id for r in run.results}
    for chk in check_engine.load_checks():
        if chk.source in ran or chk.id in present:
            continue
        run.results.append(CheckResult(
            check_id=chk.id, title=chk.title, outcome=check_engine.NOT_APPLICABLE,
            severity=chk.severity, controls=list(chk.controls), maps_to=list(chk.maps_to),
            source=chk.source, message="source %r was not collected in this run" % chk.source,
            remediation=chk.remediation,
        ))

    run.results.sort(key=lambda r: (r.source, r.check_id))

    # Drift against the previous run.
    # Prefer the caller-supplied prior run (API/worker); fall back to workspace
    # history (CLI). This ordering matters: a temp workspace always has no
    # history, so trusting disk first would disable drift in the platform.
    prev = previous_run if previous_run is not None else latest_run(ws, slug)
    if prev:
        prev_results = [CheckResult.from_dict(d) for d in prev.get("results", [])]
        check_engine.detect_drift(run.results, prev_results)
        run.previous_fingerprint = prev.get("fingerprint", "")

    run.finished_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    run.fingerprint = check_engine.run_fingerprint(run.results)

    # Persist
    runs = load_runs(ws, slug)
    runs.append(run.to_dict())
    save_runs(ws, slug, runs)
    if collected:
        save_observations(ws, slug, collected)

    append_ledger(ws, slug, {
        "type": "monitor_run",
        "at": run.finished_at,
        "fingerprint": run.fingerprint,
        "score": run.score(),
        "counts": run.counts(),
        "sources": run.sources,
    })

    return run


def build_collectors_from_env(domain: str = "", org: str = "") -> Dict[str, Callable[[], Observation]]:
    """Wire real collectors from environment configuration.

    A collector is only registered if its configuration is present, so a run
    never reports a source it could not actually reach.
    """
    from compliance_os import collectors_cloud as cc

    out: Dict[str, Callable[[], Observation]] = {}
    if domain or os.environ.get("PERIMETER_DOMAIN"):
        d = domain or os.environ.get("PERIMETER_DOMAIN", "")
        out["perimeter"] = lambda: cc.collect_perimeter(domain=d)
    if org or os.environ.get("GITHUB_ORG"):
        o = org or os.environ.get("GITHUB_ORG", "")
        out["github"] = lambda: cc.collect_github(org=o)
    if os.environ.get("AWS_PROFILE") or os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_ROLE_ARN"):
        out["aws"] = lambda: cc.collect_aws()
    if os.environ.get("WORKSPACE_DOMAIN"):
        out["workspace"] = lambda: cc.collect_workspace()
    return out
