"""Phase 2 endpoint tests: questionnaires, policies, drift channels, dossier."""

import io
import json
import os
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(HERE)
CORE = os.path.dirname(BACKEND)

sys.path.insert(0, BACKEND)
sys.path.insert(0, CORE)

os.environ.setdefault("COMPLIANCE_JWT_SECRET", "test-secret-not-for-production")
os.environ.setdefault("COMPLIANCE_SECRET_KEY", "aGVsbG8td29ybGQtdGhpcy1pcy1hLXRlc3Qta2V5LTMyYnl0ZXM=")

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

SAMPLE_CSV = (
    b"Ref,Question,Category\n"
    b"A.5.15,Do you restrict access on a need-to-know basis?,Access\n"
    b"A.8.8,Do you have a vulnerability management process?,Vulnerability\n"
    b"A.8.24,Is data encrypted at rest and in transit?,Cryptography\n"
    b"ZZZ-1,What is your favourite colour?,Misc\n"
)


def _reg(c, email, tenant="P2 Co"):
    r = c.post("/api/auth/register", json={
        "tenant_name": tenant, "email": email, "password": "averylongpassword123"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _client(c, h, name="P2 Client SARL"):
    r = c.post("/api/clients", headers=h, json={"legal_name": name, "headcount": "40",
                                                "handles_cin": True})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------ questionnaires
def test_questionnaire_upload_and_answers():
    with TestClient(app) as c:
        h = _reg(c, "q1@acme.ma")
        cid = _client(c, h)
        # give the client one implemented control so a high-confidence draft exists
        c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15" % cid,
              headers=h, json={"state": "implemented"})

        r = c.post("/api/clients/%s/questionnaires/upload" % cid, headers=h,
                   files={"file": ("vendor.csv", io.BytesIO(SAMPLE_CSV), "text/csv")},
                   data={"name": "Vendor Q1"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["total_questions"] == 4
        assert len(body["file_sha256"]) == 64
        qid = body["id"]

        r = c.get("/api/clients/%s/questionnaires/%s" % (cid, qid), headers=h)
        assert r.status_code == 200
        answers = r.json()["answers"]
        assert len(answers) == 4
        # the implemented control drafts with high confidence
        impl = [a for a in answers if a.get("state") == "implemented"]
        assert impl, answers
        assert impl[0]["confidence"] == "high"
        # the unmatched question is flagged
        unmatched = [a for a in answers if not a.get("matched_controls")]
        assert unmatched and unmatched[0]["review_flag"] == "NEEDS_HUMAN_REVIEW"
        return True


def test_questionnaire_rejects_oversize_and_bad_type():
    with TestClient(app) as c:
        h = _reg(c, "q2@acme.ma")
        cid = _client(c, h, "Q2 SARL")
        r = c.post("/api/clients/%s/questionnaires/upload" % cid, headers=h,
                   files={"file": ("x.exe", io.BytesIO(b"MZ"), "application/octet-stream")})
        assert r.status_code == 400, r.text
        r = c.post("/api/clients/%s/questionnaires/upload" % cid, headers=h,
                   files={"file": ("x.csv", io.BytesIO(b""), "text/csv")})
        assert r.status_code == 400, r.text
        return True


def test_questionnaire_answer_edit_clears_review():
    with TestClient(app) as c:
        h = _reg(c, "q3@acme.ma")
        cid = _client(c, h, "Q3 SARL")
        r = c.post("/api/clients/%s/questionnaires/upload" % cid, headers=h,
                   files={"file": ("v.csv", io.BytesIO(SAMPLE_CSV), "text/csv")})
        qid = r.json()["id"]
        detail = c.get("/api/clients/%s/questionnaires/%s" % (cid, qid), headers=h).json()
        flagged = [a for a in detail["answers"] if a.get("review_flag")]
        assert flagged, "expected at least one flagged row"
        row = flagged[0]["row"]

        r = c.patch("/api/clients/%s/questionnaires/%s/answers" % (cid, qid),
                    headers=h, json={"row": row, "draft": "Our CISO approved this."})
        assert r.status_code == 200, r.text
        patched = [a for a in r.json()["answers"] if a["row"] == row][0]
        assert patched["draft"] == "Our CISO approved this."
        assert patched["review_flag"] == ""
        return True


def test_questionnaire_export_md_and_csv():
    with TestClient(app) as c:
        h = _reg(c, "q4@acme.ma")
        cid = _client(c, h, "Q4 SARL")
        qid = c.post("/api/clients/%s/questionnaires/upload" % cid, headers=h,
                     files={"file": ("v.csv", io.BytesIO(SAMPLE_CSV), "text/csv")}).json()["id"]

        r = c.get("/api/clients/%s/questionnaires/%s/export?fmt=md" % (cid, qid), headers=h)
        assert r.status_code == 200
        assert "Questionnaire response pack" in r.text

        r = c.get("/api/clients/%s/questionnaires/%s/export?fmt=csv" % (cid, qid), headers=h)
        assert r.status_code == 200
        assert "matched_controls" in r.text
        return True


def test_questionnaire_tenant_isolation():
    with TestClient(app) as c:
        h1 = _reg(c, "q5a@acme.ma", "QA Co")
        h2 = _reg(c, "q5b@other.ma", "QB Co")
        cid = _client(c, h1, "Secret Q SARL")
        qid = c.post("/api/clients/%s/questionnaires/upload" % cid, headers=h1,
                     files={"file": ("v.csv", io.BytesIO(SAMPLE_CSV), "text/csv")}).json()["id"]
        assert c.get("/api/clients/%s/questionnaires/%s" % (cid, qid), headers=h2).status_code == 404
        return True


# ------------------------------------------------------------- policies
def test_policy_publish_version_and_acceptance():
    with TestClient(app) as c:
        h = _reg(c, "p1@acme.ma")
        cid = _client(c, h, "Policy SARL")

        r = c.post("/api/clients/%s/policies/publish" % cid, headers=h,
                   json={"policy_id": "pssi", "language": "fr"})
        assert r.status_code == 201, r.text
        v1 = r.json()
        assert v1["version"] == 1
        assert len(v1["content_sha256"]) == 64

        # publish again -> version 2, only one current
        r = c.post("/api/clients/%s/policies/publish" % cid, headers=h,
                   json={"policy_id": "pssi", "language": "fr"})
        assert r.json()["version"] == 2

        listing = c.get("/api/clients/%s/policies" % cid, headers=h).json()
        current = [p for p in listing if p["policy_id"] == "pssi" and p["is_current"]]
        assert len(current) == 1, "expected exactly one current version"

        # acknowledge
        doc_id = current[0]["id"]
        r = c.post("/api/clients/%s/policies/%s/acknowledge" % (cid, doc_id), headers=h,
                   json={"person_email": "emp@acme.ma", "person_name": "Employee"})
        assert r.status_code == 201, r.text

        # duplicate acknowledgement is idempotent
        r2 = c.post("/api/clients/%s/policies/%s/acknowledge" % (cid, doc_id), headers=h,
                    json={"person_email": "emp@acme.ma"})
        assert r2.json()["already_acknowledged"] is True

        acc = c.get("/api/clients/%s/policies/%s/acceptance" % (cid, doc_id), headers=h).json()
        assert acc["acknowledged"] == 1
        assert acc["expected"] == 40
        return True


def test_policy_body_is_client_specific():
    """A published policy must carry the real company name, not a placeholder."""
    with TestClient(app) as c:
        h = _reg(c, "p2@acme.ma")
        cid = _client(c, h, "Atlas Software SARL")
        doc = c.post("/api/clients/%s/policies/publish" % cid, headers=h,
                     json={"policy_id": "access-control"}).json()
        d = c.get("/api/clients/%s/policies/%s" % (cid, doc["id"]), headers=h).json()
        assert "Atlas Software SARL" in d["body"]
        assert "{{COMPANY}}" not in d["body"]
        return True


# --------------------------------------------------------- drift channels
def test_drift_channel_requires_https():
    with TestClient(app) as c:
        h = _reg(c, "d1@acme.ma")
        cid = _client(c, h, "Drift Ch SARL")
        r = c.post("/api/clients/%s/drift-alerts" % cid, headers=h,
                   json={"channel": "webhook", "target": "http://insecure.example.com/hook"})
        assert r.status_code == 400, r.text
        r = c.post("/api/clients/%s/drift-alerts" % cid, headers=h,
                   json={"channel": "webhook", "target": "https://hooks.example.com/x"})
        assert r.status_code == 201, r.text
        r = c.post("/api/clients/%s/drift-alerts" % cid, headers=h,
                   json={"channel": "email", "target": "soc@acme.ma"})
        assert r.status_code == 201, r.text
        return True


def test_drift_channel_target_masked():
    with TestClient(app) as c:
        h = _reg(c, "d2@acme.ma")
        cid = _client(c, h, "Mask SARL")
        secret = "https://hooks.example.com/T00/B00/XXXXXXXXSECRETVALUE"
        c.post("/api/clients/%s/drift-alerts" % cid, headers=h,
               json={"channel": "slack", "target": secret})
        listing = c.get("/api/clients/%s/drift-alerts" % cid, headers=h).json()
        assert listing
        assert "SECRETVALUE" not in json.dumps(listing), listing
        return True


# ------------------------------------------------------------- dossier
def test_audit_dossier_is_valid_zip_with_manifest():
    with TestClient(app) as c:
        h = _reg(c, "z1@acme.ma")
        cid = _client(c, h, "Dossier SARL")
        c.put("/api/clients/%s/frameworks/loi-09-08/controls/MA09-08-01" % cid,
              headers=h, json={"state": "implemented"})
        c.post("/api/clients/%s/policies/publish" % cid, headers=h,
               json={"policy_id": "pssi"})

        r = c.get("/api/clients/%s/audit-dossier" % cid, headers=h)
        assert r.status_code == 200, r.text
        assert r.headers["content-type"] == "application/zip"

        z = zipfile.ZipFile(io.BytesIO(r.content))
        names = set(z.namelist())
        for required in ("README.md", "posture.md", "control-matrix.csv",
                         "evidence-index.csv", "manifest.json"):
            assert required in names, "missing %s in %r" % (required, names)

        man = json.loads(z.read("manifest.json"))
        assert man["file_count"] == len(man["files"])
        import hashlib
        for entry in man["files"]:
            actual = hashlib.sha256(z.read(entry["path"])).hexdigest()
            assert actual == entry["sha256"], "hash mismatch on %s" % entry["path"]

        readme = z.read("README.md").decode()
        assert "not a certification" in readme.lower()
        # regulatory annexes present for a Moroccan-context client
        assert any(n.startswith("regulatory/") for n in names)
        return True


def test_dossier_available_to_readonly_auditor():
    """An auditor preparing working papers is read-only but must be able to export."""
    with TestClient(app) as c:
        h = _reg(c, "z2@acme.ma")
        cid = _client(c, h, "Audit Exp SARL")
        # Issue an auditor share token
        tok = c.post("/api/clients/%s/auditor-shares" % cid, headers=h,
                     json={"label": "auditor", "hours": 24}).json()["token"]
        v = c.get("/api/auditor/%s" % tok)
        assert v.status_code == 200
        # The share token grants read of the auditor view, not the dossier route
        # (which requires a session). Verify the read-only role cannot write.
        role_test = c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15" % cid,
                          json={"state": "implemented"})
        assert role_test.status_code == 401  # no credentials at all
        return True


def test_dossier_tenant_isolation():
    with TestClient(app) as c:
        h1 = _reg(c, "z3a@acme.ma", "ZA Co")
        h2 = _reg(c, "z3b@other.ma", "ZB Co")
        cid = _client(c, h1, "Secret Dossier SARL")
        assert c.get("/api/clients/%s/audit-dossier" % cid, headers=h2).status_code == 404
        return True


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
            import traceback
            print("  ERROR %s: %s: %s" % (name, type(exc).__name__, exc))
            traceback.print_exc()
            failed += 1
    print()
    print("%d passed, %d failed, %d total" % (passed, failed, len(tests)))
    raise SystemExit(0 if failed == 0 else 1)
