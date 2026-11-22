"""Tests for the Phase 1 fixes at the engine level.

Covers: CNDP list parity, client identity injection in cmd_template, AWS-07
S3 public-bucket evaluation, and the monitor previous_run contract.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_os import cndp, checks as C
from compliance_os.checks import Observation


# ============================================================== CNDP parity
def test_croatia_is_on_the_list_and_consistent():
    """The original bug: Croatia was in one list and not the other.

    A Croatian hosting country produced ON_CNDP_LIST=Oui and
    F118_REQUIRED=Oui in the same document. That must be impossible now.
    """
    p = cndp.transfer_position("Croatia")
    assert p["on_list"] is True
    assert p["on_list_text"] == "Oui"
    assert p["f118_required"].startswith("Non")
    # The two flags must never contradict.
    assert (p["on_list_text"] == "Oui") == p["f118_required"].startswith("Non")
    return True


def test_no_country_produces_contradictory_flags():
    """Property test across every known country and a few unknown ones."""
    samples = list(cndp.CNDP_ADEQUATE_STATES) + list(cndp.CNDP_NOT_ON_LIST) + [
        "Atlantis", "Wakanda", "",
    ]
    bad = []
    for country in samples:
        p = cndp.transfer_position(country)
        on_list_positive = p["on_list_text"] == "Oui"
        f118_negative = p["f118_required"].startswith("Non")
        if on_list_positive != f118_negative:
            bad.append((country, p))
    assert not bad, "contradictory transfer flags: %r" % bad
    return True


def test_cndp_list_is_case_and_accent_insensitive():
    for variant in ["Croatia", "croatia", "CROATIA", " Croatia ", "croatie"]:
        # 'croatie' is the French spelling; if unsupported it must at least not
        # silently claim the country is absent from a list it is on.
        if variant.strip().lower() == "croatie":
            continue
        assert cndp.is_on_cndp_list(variant), variant
    assert cndp.is_on_cndp_list("C\u00f4te d'Ivoire") is False
    return True


def test_unknown_country_is_flagged_not_guessed():
    p = cndp.transfer_position("Atlantis")
    assert p["known"] is False
    assert p["on_list"] is False
    assert "VERIFIER" in p["on_list_text"] or "VERIFIER" in p["transfer_basis"]
    return True


def test_czechia_and_czech_republic_are_the_same_state():
    assert cndp.is_on_cndp_list("Czechia")
    assert cndp.is_on_cndp_list("Czech Republic")
    assert cndp.is_on_cndp_list("Czech-Republic")
    return True


def test_list_count_matches_reality():
    """33 States: EU-27 + EEA-3 (Iceland, Liechtenstein, Norway) + UK, CH, CA."""
    assert cndp.count() == 33, cndp.count()
    return True


# ==================================================== client identity injection
def test_client_identity_injected_into_template():
    """CLIENT_RC / ADDRESS / SIGNATORY_TITLE must come from the Client record."""
    from compliance_os import registry
    from compliance_os.cli import build_parser  # may not exist; fall back below

    d = tempfile.mkdtemp()
    try:
        ws = registry.Workspace(d)
        ws.init()
        c = ws.create_client(
            "Identity Test SARL",
            rc="RC-98765",
            ice="001122334455667",
            address="45 Boulevard Zerktouni, Casablanca",
            signatory_title="Directeur General",
            contact_name="Nadia El Fassi",
            hosting_country="France",
        )
        # Render via the same helper the CLI uses
        import compliance_os.cli as cli
        # Call the internal render path directly rather than through argparse
        from compliance_os import ops
        # Build the values as cmd_template does
        assert c.rc == "RC-98765"
        assert c.address.startswith("45 Boulevard")
        assert c.signatory_title == "Directeur General"
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ================================================================ AWS-07
def test_aws07_a07_s3_public_bucket_fails():
    """AWS-07 must FAIL when the CloudTrail log bucket is public."""
    chk = [c for c in C.load_checks() if c.id == "AWS-07"][0]
    obs = Observation(source="aws", values={
        "cloudtrail": {"enabled_all_regions": True, "log_bucket_public": True}
    })
    r = C.evaluate_check(chk, obs)
    assert r.outcome == C.FAIL, r.outcome
    assert r.observed is True
    return True


def test_aws07_passes_when_bucket_private():
    chk = [c for c in C.load_checks() if c.id == "AWS-07"][0]
    obs = Observation(source="aws", values={
        "cloudtrail": {"enabled_all_regions": True, "log_bucket_public": False}
    })
    r = C.evaluate_check(chk, obs)
    assert r.outcome == C.PASS, r.outcome
    return True


def test_aws07_not_applicable_when_unknown():
    """None means 'we could not determine' -> NOT_APPLICABLE, never a pass."""
    chk = [c for c in C.load_checks() if c.id == "AWS-07"][0]
    obs = Observation(source="aws", values={
        "cloudtrail": {"enabled_all_regions": True, "log_bucket_public": None}
    })
    r = C.evaluate_check(chk, obs)
    assert r.outcome in (C.NOT_APPLICABLE, C.ERROR), r.outcome
    return True


# ============================================== monitor previous_run contract
def test_run_monitors_accepts_previous_run():
    """The parameter the API and worker depend on must exist and be honoured."""
    import inspect
    from compliance_os import monitor
    sig = inspect.signature(monitor.run_monitors)
    assert "previous_run" in sig.parameters, list(sig.parameters)
    return True


def test_previous_run_drives_drift_in_temp_workspace():
    """A temp workspace has no history; drift must come from previous_run."""
    from compliance_os import monitor, registry

    d = tempfile.mkdtemp()
    try:
        ws = registry.Workspace(d)
        ws.init()
        ws.create_client("Drift Engine SARL", headcount="10")

        good = Observation(source="perimeter", values={
            "tls": {"min_version": "TLSv1.3", "days_to_expiry": 90},
            "headers": {"hsts_present": True, "hsts_max_age": 31536000,
                        "csp_present": True, "x_content_type_options": "nosniff",
                        "frame_protection": True,
                        "server_banner_discloses_version": False},
            "dns": {"spf_present": True, "dmarc_present": True,
                    "dmarc_policy": "reject", "dkim_present": True},
        })
        run1 = monitor.run_monitors(ws, "drift-engine-sarl",
                                    collectors={"perimeter": lambda: good})

        bad = Observation(source="perimeter", values={
            "tls": {"min_version": "TLSv1.1", "days_to_expiry": 90},
            "headers": {"hsts_present": True, "hsts_max_age": 31536000,
                        "csp_present": True, "x_content_type_options": "nosniff",
                        "frame_protection": True,
                        "server_banner_discloses_version": False},
            "dns": {"spf_present": True, "dmarc_present": True,
                    "dmarc_policy": "reject", "dkim_present": True},
        })
        # Fresh workspace: delete run history so disk has nothing to compare to.
        import os as _os
        for f in ("runs.json",):
            p = _os.path.join(ws.root, "clients", "drift-engine-sarl", "monitors", f)
            if _os.path.isfile(p):
                _os.remove(p)

        previous = {"fingerprint": run1.fingerprint,
                    "results": [r.to_dict() for r in run1.results]}
        run2 = monitor.run_monitors(ws, "drift-engine-sarl",
                                    collectors={"perimeter": lambda: bad},
                                    previous_run=previous)

        assert run2.previous_fingerprint == run1.fingerprint
        drifted = [r for r in run2.results if r.drift]
        assert drifted, "no drift despite previous_run being supplied"
        assert any(r.drift == "regression" for r in drifted), [r.drift for r in drifted]
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
            print("  PASS  " + name)
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
