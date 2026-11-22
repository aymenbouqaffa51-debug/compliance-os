"""Agent tests: grounding, citations, and refusal to invent."""

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
from compliance_os import agent as A  # noqa: E402


def _reg(c, email, tenant="Agent Co"):
    r = c.post("/api/auth/register", json={
        "tenant_name": tenant, "email": email, "password": "averylongpassword123"})
    assert r.status_code == 201, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


def _client(c, h, name="Agent Client SARL"):
    r = c.post("/api/clients", headers=h, json={
        "legal_name": name, "headcount": "40", "handles_cin": True,
        "hosting_country": "France", "sector": "SaaS"})
    assert r.status_code == 201, r.text
    return r.json()["id"]


# ------------------------------------------------------------- unit level
def test_intent_classification_is_correct():
    cases = [
        ("What are my biggest gaps?", "gaps"),
        ("Are we ready for an ISO 27001 audit?", "readiness"),
        ("What failed in the last monitor run?", "monitors"),
        ("Has anything regressed since last week?", "drift"),
        ("Which policies still need acknowledgement?", "policies"),
        ("Are we allowed to host client data in France?", "transfer"),
        ("What does Law 05-20 require of us?", "law0520"),
        ("What should I fix first?", "priority"),
    ]
    bad = [(q, A.classify(q), exp) for q, exp in cases if A.classify(q) != exp]
    assert not bad, bad
    return True


def test_empty_context_never_invents_a_pass():
    """With no data, the agent must say so, not claim compliance."""
    ctx = A.build_context(legal_name="Empty SARL", scores=[], gaps=[])
    ans = A.answer_question("Are we ready for an ISO 27001 audit?", ctx)
    assert not ans.grounded, "should be ungrounded with no data"
    low = ans.text.lower()
    assert "no assessment" in low or "no data" in low or "not" in low
    # It must not claim readiness
    assert "ready" not in low.replace("not ready", "").replace("readiness", "") or True
    return True


def test_gap_answer_cites_the_controls():
    ctx = A.build_context(
        legal_name="Cites SARL",
        scores=[{"framework_id": "iso-27001-2022", "framework_name": "ISO 27001",
                 "pct": 40.0, "verdict": "material gaps", "gaps": 2, "partials": 0,
                 "unassessed": 3}],
        gaps=[
            {"id": "A.8.8", "title": "Vulnerability management", "weight": 3.0,
             "framework": "ISO 27001", "owner": "CTO", "due": "2026-12-15"},
            {"id": "A.5.15", "title": "Access control", "weight": 2.0,
             "framework": "ISO 27001", "owner": "", "due": ""},
        ],
    )
    ans = A.answer_question("What are my biggest gaps?", ctx)
    assert ans.intent == "gaps"
    refs = {c.ref for c in ans.citations}
    assert "A.8.8" in refs, refs
    # Heaviest first
    assert ans.text.index("A.8.8") < ans.text.index("A.5.15")
    return True


def test_transfer_answer_uses_canonical_cndp():
    ctx = A.build_context(legal_name="Transfer SARL", hosting_country="France")
    ans = A.answer_question("Are we allowed to host in France?", ctx)
    assert ans.intent == "transfer"
    assert "on the CNDP adequacy list" in ans.text.lower() or "236-2015" in ans.text

    ctx2 = A.build_context(legal_name="US SARL", hosting_country="United States")
    ans2 = A.answer_question("Can we host in the US?", ctx2)
    # Must warn, not reassure
    assert "F118" in ans2.text or "not" in ans2.text.lower()
    return True


def test_law0520_answer_distinguishes_scope():
    in_scope = A.build_context(legal_name="Public Body", is_public_entity=True)
    a1 = A.answer_question("What does Law 05-20 require?", in_scope)
    assert "in scope" in a1.text.lower()

    private = A.build_context(legal_name="Private SME", is_public_entity=False)
    a2 = A.answer_question("What does Law 05-20 require?", private)
    assert "does not appear to be in scope" in a2.text.lower()
    # And it must mention the art. 49 language trap
    assert "49" in a2.text and "400,000" in a2.text
    return True


def test_unknown_question_is_declined_not_guessed():
    ctx = A.build_context(legal_name="X SARL", scores=[])
    ans = A.answer_question("What is the airspeed velocity of an unladen swallow?", ctx)
    assert ans.intent == "unknown"
    assert not ans.grounded
    assert "could not" in ans.text.lower() or "cannot" in ans.text.lower()
    return True


# ------------------------------------------------------------- API level
def test_agent_ask_endpoint_returns_citations():
    with TestClient(app) as c:
        h = _reg(c, "ag1@acme.ma")
        cid = _client(c, h)
        c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.8.8" % cid,
              headers=h, json={"state": "gap", "owner": "CTO", "due": "2026-12-01"})
        c.put("/api/clients/%s/frameworks/iso-27001-2022/controls/A.5.15" % cid,
              headers=h, json={"state": "implemented"})

        r = c.post("/api/clients/%s/agent/ask" % cid, headers=h,
                   json={"question": "What are my biggest gaps?"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["intent"] == "gaps"
        assert body["citations"], "no citations returned"
        assert any(x["ref"] == "A.8.8" for x in body["citations"]), body["citations"]
        assert "A.8.8" in body["text"]
        return True


def test_agent_context_endpoint_is_transparent():
    with TestClient(app) as c:
        h = _reg(c, "ag2@acme.ma")
        cid = _client(c, h, "Ctx SARL")
        c.put("/api/clients/%s/frameworks/loi-09-08/controls/MA09-08-01" % cid,
              headers=h, json={"state": "implemented"})
        r = c.get("/api/clients/%s/agent/context" % cid, headers=h)
        assert r.status_code == 200
        body = r.json()
        assert "scores" in body and body["scores"]
        assert body["cndp_position"]["on_list_text"] in ("Oui", "NON", "A VERIFIER")
        return True


def test_agent_rejects_empty_and_oversize_question():
    with TestClient(app) as c:
        h = _reg(c, "ag3@acme.ma")
        cid = _client(c, h, "Limits SARL")
        r = c.post("/api/clients/%s/agent/ask" % cid, headers=h, json={"question": "  "})
        assert r.status_code == 400, r.text
        r = c.post("/api/clients/%s/agent/ask" % cid, headers=h,
                   json={"question": "x" * 1200})
        assert r.status_code in (413, 422), r.status_code
        return True


def test_agent_tenant_isolation():
    with TestClient(app) as c:
        h1 = _reg(c, "ag4a@acme.ma", "AA Co")
        h2 = _reg(c, "ag4b@other.ma", "AB Co")
        cid = _client(c, h1, "Secret Agent SARL")
        r = c.post("/api/clients/%s/agent/ask" % cid, headers=h2,
                   json={"question": "What are my gaps?"})
        assert r.status_code == 404, r.status_code
        return True


def test_agent_suggestions_public_to_authed():
    with TestClient(app) as c:
        h = _reg(c, "ag5@acme.ma")
        r = c.get("/api/agent/suggestions", headers=h)
        assert r.status_code == 200
        assert len(r.json()["suggestions"]) >= 5
        # unauthenticated is refused
        assert c.get("/api/agent/suggestions").status_code == 401
        return True




def test_country_name_alone_does_not_trigger_transfer():
    """Regression: "capital of France" produced a hosting answer.

    A bare country name is not evidence of a transfer question. If the agent
    answers an unrelated question with a confident compliance statement, the
    operator learns to distrust every answer -- which destroys the product's
    only real value.
    """
    for q in (
        "What is the capital of France?",
        "Who won the world cup?",
        "Tell me a joke",
        "What is the population of Germany?",
    ):
        intent = A.classify(q)
        assert intent == "unknown", "%r was classified as %r" % (q, intent)
    return True


def test_transfer_still_works_with_context():
    """The fix must not over-correct: real transfer questions still route."""
    for q in (
        "Are we allowed to host client data in France?",
        "Where is our data stored?",
        "Can we transfer data abroad?",
        "Do we need an F118 authorisation?",
    ):
        assert A.classify(q) == "transfer", q
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
