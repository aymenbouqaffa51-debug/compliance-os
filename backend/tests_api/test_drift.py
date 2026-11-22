import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
CORE = os.path.dirname(BACKEND)

sys.path.insert(0, BACKEND)
sys.path.insert(0, CORE)

os.environ.setdefault("COMPLIANCE_JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("COMPLIANCE_SECRET_KEY", "aGVsbG8td29ybGQtdGhpcy1pcy1hLXRlc3Qta2V5LTMyYnl0ZXM=")

from fastapi.testclient import TestClient
from app.main import app


def _register(c, email, tenant="Drift Co"):
    r = c.post("/api/auth/register", json={
        "tenant_name": tenant, "email": email, "password": "averylongpassword123"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def test_drift_detected_across_consecutive_api_runs():
    """PASS -> FAIL across two runs must be flagged as a regression.

    This is the bug the whole Phase 1 fix exists for: the API ran monitors in a
    throwaway temp workspace, so latest_run() saw no history and drift never
    fired. Now the prior MonitorRunRecord is loaded from the database.

    We drive it through the real endpoint with a stubbed collector so the test
    is deterministic and needs no network.
    """
    import app.routers.monitoring as mon_router
    from compliance_os.checks import Observation
    from compliance_os import collectors_cloud

    # Run 1: TLS is good. Run 2: TLS regresses to 1.1.
    state = {"version": "TLSv1.3"}
    original = collectors_cloud.collect_perimeter

    def fake_perimeter(domain="", base_url=""):
        return Observation(source="perimeter", values={
            "tls": {"min_version": state["version"], "days_to_expiry": 90},
            "headers": {
                "hsts_present": True, "hsts_max_age": 31536000,
                "csp_present": True, "x_content_type_options": "nosniff",
                "frame_protection": True, "server_banner_discloses_version": False,
            },
            "dns": {"spf_present": True, "dmarc_present": True,
                    "dmarc_policy": "reject", "dkim_present": True},
        })

    collectors_cloud.collect_perimeter = fake_perimeter
    try:
        with TestClient(app) as c:
            h = _register(c, "drift1@acme.ma")
            cid = c.post("/api/clients", headers=h, json={
                "legal_name": "Drift Client SARL",
                "handles_cin": False}).json()["id"]

            # Store a domain so the perimeter collector is wired in.
            # (The API builds it from footprint["domain"].)
            # We instead inject via the integrations path is not needed: the
            # endpoint builds perimeter from facts.get("domain"). Patch facts.
            from app import models
            from app.db import SessionLocal
            db = SessionLocal()
            rec = db.get(models.ClientRecord, cid)
            facts = json.loads(rec.footprint or "{}")
            facts["domain"] = "example.com"
            rec.footprint = json.dumps(facts)
            db.commit()
            db.close()

            r1 = c.post("/api/clients/%s/monitor/run" % cid, headers=h)
            assert r1.status_code == 200, r1.text
            run1 = r1.json()
            assert run1["score"] > 0, "first run scored nothing"
            fp1 = run1["fingerprint"]

            # Regress TLS
            state["version"] = "TLSv1.1"

            r2 = c.post("/api/clients/%s/monitor/run" % cid, headers=h)
            assert r2.status_code == 200, r2.text
            run2 = r2.json()

            # The regression must show up
            drifted = [x for x in run2["results"] if x.get("drift")]
            assert drifted, (
                "no drift detected on a PASS->FAIL regression. "
                "fingerprint1=%s fingerprint2=%s score1=%s score2=%s"
                % (fp1, run2["fingerprint"], run1["score"], run2["score"]))

            kinds = {x["drift"] for x in drifted}
            assert "regression" in kinds, kinds

            # And the check that regressed is PER-01 (TLS version)
            ids = {x["check_id"] for x in drifted}
            assert "PER-01" in ids, "expected PER-01 in drift set, got %r" % ids

            # Score must have dropped
            assert run2["score"] < run1["score"], (
                "score did not drop: %s -> %s" % (run1["score"], run2["score"]))
            return True
    finally:
        collectors_cloud.collect_perimeter = original


def test_previous_fingerprint_is_recorded():
    """Run 2's previous_fingerprint must equal run 1's fingerprint."""
    from compliance_os.checks import Observation
    from compliance_os import collectors_cloud
    from app import models
    from app.db import SessionLocal

    original = collectors_cloud.collect_perimeter
    collectors_cloud.collect_perimeter = lambda domain="", base_url="": Observation(
        source="perimeter",
        values={"tls": {"min_version": "TLSv1.3", "days_to_expiry": 90},
                "headers": {}, "dns": {}})
    try:
        with TestClient(app) as c:
            h = _register(c, "fp@acme.ma", "FP Co")
            cid = c.post("/api/clients", headers=h, json={"legal_name": "FP SARL"}).json()["id"]
            db = SessionLocal()
            rec = db.get(models.ClientRecord, cid)
            facts = json.loads(rec.footprint or "{}")
            facts["domain"] = "example.com"
            rec.footprint = json.dumps(facts)
            db.commit()
            db.close()

            a = c.post("/api/clients/%s/monitor/run" % cid, headers=h).json()
            b = c.post("/api/clients/%s/monitor/run" % cid, headers=h).json()

            db = SessionLocal()
            rows = db.query(models.MonitorRunRecord).filter_by(client_id=cid).order_by(
                models.MonitorRunRecord.started_at.asc()).all()
            assert len(rows) == 2, len(rows)
            assert rows[1].previous_fingerprint == rows[0].fingerprint, (
                "previous_fingerprint not linked: %r vs %r"
                % (rows[1].previous_fingerprint, rows[0].fingerprint))
            db.close()
            return True
    finally:
        collectors_cloud.collect_perimeter = original


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
