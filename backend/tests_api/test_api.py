"""API integration tests. Run with: python3 tests_api/test_api.py"""

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

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402


def _client():
    return TestClient(app)


def _register(c, email, tenant="Acme Consulting"):
    r = c.post("/api/auth/register", json={
        "tenant_name": tenant, "email": email, "password": "averylongpassword123"})
    assert r.status_code == 201, r.text
    body = r.json()
    return {"Authorization": "Bearer " + body["access_token"]}, body


def test_health():
    with _client() as c:
        r = c.get("/api/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_register_login_me():
    with _client() as c:
        h, body = _register(c, "reg1@acme.ma")
        assert body["role"] == "platform_admin"

        r = c.get("/api/auth/me", headers=h)
        assert r.status_code == 200
        assert r.json()["email"] == "reg1@acme.ma"

        r = c.post("/api/auth/login", json={
            "email": "reg1@acme.ma", "password": "averylongpassword123"})
        assert r.status_code == 200
        assert r.json()["access_token"]


def test_login_wrong_password_is_401():
    with _client() as c:
        _register(c, "reg2@acme.ma")
        r = c.post("/api/auth/login", json={
            "email": "reg2@acme.ma", "password": "wrongpassword123"})
        assert r.status_code == 401
        # Same message as unknown user: no account enumeration.
        assert r.json()["detail"] == "invalid credentials"


def test_duplicate_email_is_409():
    with _client() as c:
        _register(c, "dup@acme.ma", "First Co")
        r = c.post("/api/auth/register", json={
            "tenant_name": "Second Co", "email": "dup@acme.ma",
            "password": "averylongpassword123"})
        assert r.status_code == 409


def test_unauthenticated_is_401():
    with _client() as c:
        assert c.get("/api/frameworks").status_code == 401
        assert c.get("/api/clients").status_code == 401


def test_token_tampering_rejected():
    with _client() as c:
        h, _ = _register(c, "tamper@acme.ma")
        tok = h["Authorization"].split(" ", 1)[1]
        head, payload, sig = tok.split(".")
        bad = head + "." + payload + "." + ("A" * len(sig))
        r = c.get("/api/auth/me", headers={"Authorization": "Bearer " + bad})
        assert r.status_code == 401


def test_frameworks_and_controls():
    with _client() as c:
        h, _ = _register(c, "fw@acme.ma")
        r = c.get("/api/frameworks", headers=h)
        assert r.status_code == 200
        fws = r.json()
        assert len(fws) == 4
        total = sum(f["control_count"] for f in fws)
        assert total >= 120, total

        r = c.get("/api/frameworks/iso-27001-2022/controls", headers=h)
        assert r.status_code == 200
        assert len(r.json()) >= 60


def test_client_crud_and_scoring():
    with _client() as c:
        h, _ = _register(c, "crud@acme.ma")
        r = c.post("/api/clients", headers=h, json={
            "legal_name": "Atlas Software SARL", "sector": "SaaS",
            "headcount": "42", "rc": "RC-123", "handles_cin": True})
        assert r.status_code == 201, r.text
        cid = r.json()["id"]
        assert r.json()["slug"] == "atlas-software-sarl"

        r = c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15" % cid,
                  headers=h, json={"state": "implemented", "notes": "policy v3"})
        assert r.status_code == 200
        assert r.json()["state"] == "implemented"
        assert r.json()["signed_off_by"] == "crud@acme.ma"

        r = c.get("/api/clients/%s/score" % cid, headers=h)
        assert r.status_code == 200
        iso = [s for s in r.json() if s["framework_id"] == "iso-27001-2022"][0]
        assert iso["pct"] > 0
        return True


def test_invalid_control_state_is_400():
    with _client() as c:
        h, _ = _register(c, "badstate@acme.ma")
        cid = c.post("/api/clients", headers=h, json={"legal_name": "Bad State SARL"}).json()["id"]
        r = c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15" % cid,
                  headers=h, json={"state": "totally-made-up"})
        assert r.status_code == 400


def test_unknown_control_is_404():
    with _client() as c:
        h, _ = _register(c, "unknown@acme.ma")
        cid = c.post("/api/clients", headers=h, json={"legal_name": "Unknown SARL"}).json()["id"]
        r = c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/ZZZ.99" % cid,
                  headers=h, json={"state": "implemented"})
        assert r.status_code == 404


def test_tenant_isolation():
    """A client created in tenant A must be invisible to tenant B."""
    with _client() as c:
        h1, _ = _register(c, "iso-a@acme.ma", "Tenant A")
        h2, _ = _register(c, "iso-b@other.ma", "Tenant B")

        cid = c.post("/api/clients", headers=h1, json={"legal_name": "Secret Client SARL"}).json()["id"]

        # Tenant B cannot read it, and must not learn it exists (404, not 403).
        assert c.get("/api/clients/%s" % cid, headers=h2).status_code == 404
        assert c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15" % cid,
                     headers=h2, json={"state": "implemented"}).status_code == 404
        # Tenant B's list does not contain it
        names = [x["slug"] for x in c.get("/api/clients", headers=h2).json()]
        assert "secret-client-sarl" not in names


def test_audit_log_is_chained():
    with _client() as c:
        h, _ = _register(c, "audit@acme.ma")
        c.post("/api/clients", headers=h, json={"legal_name": "Audit SARL"})
        r = c.get("/api/audit-log", headers=h)
        assert r.status_code == 200
        actions = [x["action"] for x in r.json()]
        assert "auth.register" in actions
        assert "client.create" in actions


def test_evidence_stores_hash_not_content():
    with _client() as c:
        h, _ = _register(c, "ev@acme.ma")
        cid = c.post("/api/clients", headers=h, json={"legal_name": "Evidence SARL"}).json()["id"]
        r = c.post("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15/evidence" % cid,
                   headers=h, json={"kind": "attestation",
                                    "summary": "Politique approuvee",
                                    "source": "sharepoint"})
        assert r.status_code == 201
        body = r.json()
        assert len(body["sha256"]) == 64
        assert "Politique approuvee" in body["summary"]


def test_integration_secret_never_returned():
    with _client() as c:
        h, _ = _register(c, "int@acme.ma")
        cid = c.post("/api/clients", headers=h, json={"legal_name": "Integ SARL"}).json()["id"]
        secret = "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        r = c.post("/api/clients/%s/integrations" % cid, headers=h,
                   json={"provider": "github", "secret": secret, "config": {"org": "acme"}})
        assert r.status_code == 201
        assert secret not in r.text

        r = c.get("/api/clients/%s/integrations" % cid, headers=h)
        assert r.status_code == 200
        assert secret not in r.text
        assert r.json()[0]["config"]["org"] == "acme"


def test_trust_centre_is_public():
    with _client() as c:
        h, body = _register(c, "trust@acme.ma", "Trust Co")
        tenant_slug = "trust-co"
        cid = c.post("/api/clients", headers=h, json={"legal_name": "Trust Client SARL"}).json()["id"]
        c.put("/api/clients/%s/frameworks/loi-09-08/controls/MA09-08-01" % cid,
              headers=h, json={"state": "implemented"})

        r = c.get("/api/trust/%s/trust-client-sarl" % tenant_slug)
        assert r.status_code == 200
        data = r.json()
        assert data["client"]["name"] == "Trust Client SARL"
        assert any(f["readiness_pct"] > 0 for f in data["frameworks"])
        assert "not a certification" in data["disclaimer"]


def test_auditor_share_expiry_and_readonly():
    with _client() as c:
        h, _ = _register(c, "aud@acme.ma", "Auditor Co")
        cid = c.post("/api/clients", headers=h, json={"legal_name": "Audited SARL"}).json()["id"]
        r = c.post("/api/clients/%s/auditor-shares" % cid, headers=h,
                   json={"label": "ISO auditor", "hours": 48})
        assert r.status_code == 201
        token = r.json()["token"]

        r = c.get("/api/auditor/%s" % token)
        assert r.status_code == 200
        assert r.json()["client"] == "Audited SARL"

        # Invalid token
        assert c.get("/api/auditor/not-a-real-token").status_code == 404


def test_mfa_setup_and_verification():
    from app import security
    with _client() as c:
        h, _ = _register(c, "mfa@acme.ma")
        r = c.post("/api/auth/totp/setup", headers=h)
        assert r.status_code == 200
        secret = r.json()["secret"]
        assert r.json()["uri"].startswith("otpauth://totp/")

        code = security.totp_now(secret)
        r = c.post("/api/auth/totp/verify", headers=h, json={"code": code})
        assert r.status_code == 200
        assert r.json()["totp_enabled"] is True

        # Login now requires the code
        r = c.post("/api/auth/login", json={"email": "mfa@acme.ma",
                                            "password": "averylongpassword123"})
        assert r.status_code == 401
        assert r.headers.get("x-totp-required") == "1"

        r = c.post("/api/auth/login", json={"email": "mfa@acme.ma",
                                            "password": "averylongpassword123",
                                            "totp_code": security.totp_now(secret)})
        assert r.status_code == 200


def test_password_too_short_rejected():
    with _client() as c:
        r = c.post("/api/auth/register", json={
            "tenant_name": "Short Co", "email": "short@acme.ma", "password": "abc"})
        assert r.status_code == 422


def test_security_headers_present():
    with _client() as c:
        r = c.get("/api/health")
        assert r.headers["X-Content-Type-Options"] == "nosniff"
        assert r.headers["X-Frame-Options"] == "DENY"


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
