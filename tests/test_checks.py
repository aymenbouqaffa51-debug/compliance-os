"""Tests for the check engine and drift detection.

These use synthetic observations -- no network, no credentials. The point is to
prove the evaluation logic, the drift transitions, and the hash-chained ledger
are correct before any real collector is trusted.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_os import checks as C
from compliance_os import monitor, registry
from compliance_os.checks import Check, CheckResult, Observation


# ------------------------------------------------------------------ loading
def test_checks_load_and_are_unique():
    cs = C.load_checks()
    assert len(cs) >= 30, "expected at least 30 checks, got %d" % len(cs)
    ids = [c.id for c in cs]
    assert len(ids) == len(set(ids)), "duplicate check ids"
    return True


def test_every_check_references_a_real_control():
    allids = set()
    for fid in registry.framework_ids():
        allids |= {c.id for c in registry.load_framework(fid).controls}
    bad = []
    for c in C.load_checks():
        for t in list(c.controls) + list(c.maps_to):
            if t not in allids:
                bad.append("%s -> %s" % (c.id, t))
    assert not bad, "checks reference unknown controls: %r" % bad
    return True


def test_operator_whitelist_rejects_unknown():
    try:
        Check.from_dict({"id": "X", "source": "aws", "field": "a", "operator": "exec"})
        raise AssertionError("unknown operator was accepted")
    except C.CheckError:
        return True


# ---------------------------------------------------------------- evaluation
def test_pass_and_fail_outcomes():
    chk = Check(id="T1", title="mfa", source="github",
                field="org.two_factor_required", operator="is_true", severity="critical")
    good = Observation(source="github", values={"org": {"two_factor_required": True}})
    bad = Observation(source="github", values={"org": {"two_factor_required": False}})
    assert C.evaluate_check(chk, good).outcome == C.PASS
    r = C.evaluate_check(chk, bad)
    assert r.outcome == C.FAIL
    assert r.observed is False
    return True


def test_missing_fact_is_not_applicable_not_fail():
    """A check with no data has no opinion. Conflating that with FAIL makes noise."""
    chk = Check(id="T2", title="x", source="aws", field="iam.root_mfa_enabled",
                operator="is_true")
    obs = Observation(source="aws", values={"iam": {}})
    r = C.evaluate_check(chk, obs)
    assert r.outcome == C.NOT_APPLICABLE, r.outcome
    return True


def test_source_mismatch_is_skipped():
    chk = Check(id="T3", title="x", source="aws", field="a", operator="is_true")
    obs = Observation(source="github", values={"a": True})
    assert C.evaluate_check(chk, obs).outcome == C.SKIPPED
    return True


def test_type_error_is_error_not_fail():
    chk = Check(id="T4", title="x", source="aws", field="n", operator="gte", value=5)
    obs = Observation(source="aws", values={"n": "not-a-number"})
    assert C.evaluate_check(chk, obs).outcome == C.ERROR
    return True


def test_len_operators():
    chk = Check(id="T5", title="x", source="aws", field="bad", operator="len_eq", value=0)
    assert C.evaluate_check(chk, Observation(source="aws", values={"bad": []})).outcome == C.PASS
    assert C.evaluate_check(chk, Observation(source="aws", values={"bad": ["a"]})).outcome == C.FAIL
    return True


def test_version_comparison_is_numeric_not_lexical():
    """The classic bug: '1.10' < '1.9' as strings. Must compare numerically."""
    assert C._version_ge("1.10", "1.9") is True
    assert C._version_ge("1.2", "1.2") is True
    assert C._version_ge("1.1", "1.2") is False
    assert C._version_ge("TLSv1.3", "1.3") is True
    return True


def test_tls_check_uses_numeric_version_compare():
    chk = Check(id="T6", title="tls", source="perimeter",
                field="tls.min_version", operator="version_gte", value="1.2")
    assert C.evaluate_check(chk, Observation(source="perimeter",
        values={"tls": {"min_version": "TLSv1.3"}})).outcome == C.PASS
    assert C.evaluate_check(chk, Observation(source="perimeter",
        values={"tls": {"min_version": "TLSv1.1"}})).outcome == C.FAIL
    return True


# --------------------------------------------------------------------- drift
def test_drift_regression_detected():
    chk = Check(id="D1", title="x", source="aws", field="a", operator="is_true")
    prev = [C.evaluate_check(chk, Observation(source="aws", values={"a": True}))]
    cur = [C.evaluate_check(chk, Observation(source="aws", values={"a": False}))]
    C.detect_drift(cur, prev)
    assert cur[0].drift == "regression", cur[0].drift
    assert cur[0].previous_outcome == C.PASS
    return True


def test_drift_no_change_is_silent():
    chk = Check(id="D2", title="x", source="aws", field="a", operator="is_true")
    prev = [C.evaluate_check(chk, Observation(source="aws", values={"a": True}))]
    cur = [C.evaluate_check(chk, Observation(source="aws", values={"a": True}))]
    C.detect_drift(cur, prev)
    assert cur[0].drift == ""
    return True


def test_drift_improvement_is_not_alerted():
    """FAIL -> PASS is good news, not an alert."""
    chk = Check(id="D3", title="x", source="aws", field="a", operator="is_true")
    prev = [C.evaluate_check(chk, Observation(source="aws", values={"a": False}))]
    cur = [C.evaluate_check(chk, Observation(source="aws", values={"a": True}))]
    C.detect_drift(cur, prev)
    assert cur[0].drift == ""
    return True


# ---------------------------------------------------------------------- runs
def test_score_excludes_non_decisive():
    run = C.CheckRun(client_slug="x")
    run.results = [
        CheckResult("a", "A", C.PASS, "high"),
        CheckResult("b", "B", C.FAIL, "high"),
        CheckResult("c", "C", C.NOT_APPLICABLE, "high"),
        CheckResult("d", "D", C.SKIPPED, "high"),
    ]
    assert run.score() == 50.0, run.score()
    return True


def test_run_persists_and_chains_ledger():
    d = tempfile.mkdtemp()
    try:
        ws = registry.Workspace(d)
        ws.init()
        ws.create_client("Ledger SARL", headcount="20")

        def obs_ok():
            return Observation(source="perimeter", values={
                "tls": {"min_version": "TLSv1.3", "days_to_expiry": 90},
                "headers": {"hsts_present": True, "hsts_max_age": 31536000,
                            "csp_present": True, "x_content_type_options": "nosniff",
                            "frame_protection": True,
                            "server_banner_discloses_version": False},
                "dns": {"spf_present": True, "dmarc_present": True,
                        "dmarc_policy": "reject", "dkim_present": True},
            })

        r1 = monitor.run_monitors(ws, "ledger-sarl", collectors={"perimeter": obs_ok})
        assert r1.fingerprint
        assert r1.score() > 0

        # Second run with a regression
        def obs_bad():
            return Observation(source="perimeter", values={
                "tls": {"min_version": "TLSv1.1", "days_to_expiry": 90},
                "headers": {"hsts_present": True, "hsts_max_age": 31536000,
                            "csp_present": True, "x_content_type_options": "nosniff",
                            "frame_protection": True,
                            "server_banner_discloses_version": False},
                "dns": {"spf_present": True, "dmarc_present": True,
                        "dmarc_policy": "reject", "dkim_present": True},
            })

        r2 = monitor.run_monitors(ws, "ledger-sarl", collectors={"perimeter": obs_bad})
        assert r2.previous_fingerprint == r1.fingerprint
        drift = [x for x in r2.results if x.drift]
        assert drift, "no drift detected on PER-01 regression"

        v = monitor.verify_ledger(ws, "ledger-sarl")
        assert v["ok"] is True, v
        assert v["records"] == 2, v
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_ledger_tamper_is_detected():
    """Editing a historical record must break the chain."""
    d = tempfile.mkdtemp()
    try:
        ws = registry.Workspace(d)
        ws.init()
        ws.create_client("Tamper SARL", headcount="10")
        monitor.run_monitors(
            ws, "tamper-sarl",
            collectors={"perimeter": lambda: Observation(source="perimeter", values={"tls": {"min_version": "TLSv1.3"}})},
        )
        assert monitor.verify_ledger(ws, "tamper-sarl")["ok"] is True

        # Tamper: rewrite the score in the ledger
        p = monitor.ledger_path(ws, "tamper-sarl")
        lines = open(p, encoding="utf-8").read().splitlines()
        lines[0] = lines[0].replace('"score": 0.0', '"score": 99.0')
        if '"score": 99.0' not in lines[0]:
            # score may not be 0.0; patch whatever it is
            import re
            lines[0] = re.sub(r'"score": [0-9.]+', '"score": 99.0', lines[0])
        open(p, "w", encoding="utf-8").write("\n".join(lines) + "\n")

        v = monitor.verify_ledger(ws, "tamper-sarl")
        assert v["ok"] is False, "tampering was not detected"
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_uncollected_source_reports_not_applicable():
    """Coverage must not silently shrink when a source is not configured."""
    d = tempfile.mkdtemp()
    try:
        ws = registry.Workspace(d)
        ws.init()
        ws.create_client("Coverage SARL", headcount="10")
        run = monitor.run_monitors(ws, "coverage-sarl", collectors={})
        outcomes = set(r.outcome for r in run.results)
        assert outcomes == {C.NOT_APPLICABLE}, outcomes
        assert len(run.results) == len(C.load_checks())
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_collector_crash_does_not_abort_run():
    d = tempfile.mkdtemp()
    try:
        ws = registry.Workspace(d)
        ws.init()
        ws.create_client("Crash SARL", headcount="10")

        def boom():
            raise RuntimeError("simulated failure")

        run = monitor.run_monitors(
            ws, "crash-sarl",
            collectors={
                "aws": boom,
                "perimeter": lambda: Observation(source="perimeter", values={"tls": {"min_version": "TLSv1.3"}}),
            },
        )
        # perimeter still evaluated
        assert any(r.source == "perimeter" and r.outcome == C.PASS for r in run.results)
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for name, fn in tests:
        try:
            fn()
            print("  PASS  %s" % name)
            passed += 1
        except AssertionError as exc:
            print("  FAIL  %s: %s" % (name, exc))
            failed += 1
        except Exception as exc:
            print("  ERROR %s: %s: %s" % (name, type(exc).__name__, exc))
            failed += 1
    print()
    print("%d passed, %d failed, %d total" % (passed, failed, len(tests)))
    raise SystemExit(0 if failed == 0 else 1)
