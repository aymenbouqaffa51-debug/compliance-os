"""Security regression tests.

Each test here corresponds to a defect that was real in an earlier revision.
They exist so the defect cannot come back silently.

Run: python3 tests/test_security.py
     or: python3 -m pytest tests/test_security.py -v
"""

import os
import shutil
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from compliance_os import collector
from compliance_os.safe_eval import ConditionError, compile_condition, evaluate


# =====================================================================
# 1. eval() replacement: the AST evaluator must reject everything unsafe
# =====================================================================

ALLOWED_CASES = [
    ("client.handles_cin", {"handles_cin": True}, True),
    ("client.handles_cin", {"handles_cin": False}, False),
    ("client.handles_cin or client.handles_sensitive_data", {"handles_cin": False, "handles_sensitive_data": True}, True),
    ("client.handles_cin or client.handles_sensitive_data", {"handles_cin": False, "handles_sensitive_data": False}, False),
    ("not client.is_iiv", {"is_iiv": False}, True),
    ("client.headcount_num >= 50", {"headcount_num": 50}, True),
    ("client.headcount_num >= 50", {"headcount_num": 49}, False),
    ("client.headcount_num > 10 and client.has_cloud", {"headcount_num": 42, "has_cloud": True}, True),
    ("len(client.export_markets) > 0", {"export_markets": ["France"]}, True),
    ("len(client.export_markets) > 0", {"export_markets": []}, False),
    ("client.engagement in ('readiness_program', 'retainer')", {"engagement": "retainer"}, True),
    ("client.sector == 'SaaS'", {"sector": "SaaS"}, True),
    ("bool(client.notes)", {"notes": ""}, False),
]

REJECTED_CASES = [
    "__import__('os').system('echo pwned')",       # arbitrary import
    "client.__class__",                              # dunder attribute
    "client.__dict__",                               # dunder attribute
    "().__class__.__bases__",                        # traversal
    "open('/etc/passwd').read()",                    # arbitrary call
    "eval('1+1')",                                   # recursive eval
    "exec('x=1')",                                   # exec
    "[x for x in range(10)]",                        # comprehension
    "lambda: 1",                                     # lambda
    "client[0]",                                     # subscript
    "client.export_markets[0]",                      # subscript on attribute
    "os.system('id')",                               # bare name call
    "len",                                           # bare name, not called
    "f'{1}'",                                        # f-string
    "client.handles_cin if True else False",         # ifexp
    "getattr(client, 'handles_cin')",                # getattr not whitelisted
    "client.handles_cin; 1",                         # multiple statements
    "",                                              # empty
    "   ",                                            # whitespace only
    "client.handles_cin =",                          # syntax error
]


def test_allowed_conditions_evaluate_correctly():
    for expr, data, expected in ALLOWED_CASES:
        got = evaluate(expr, data)
        assert got is expected, "%r with %r -> %r, expected %r" % (expr, data, got, expected)
    return True


def test_unsafe_conditions_are_rejected():
    failures = []
    for expr in REJECTED_CASES:
        try:
            evaluate(expr, {"handles_cin": True, "notes": ""})
            failures.append(expr)
        except ConditionError:
            pass
        except Exception as exc:
            # Any other exception type means the guard did not do its job
            failures.append("%s (raised %s instead of ConditionError)" % (expr, type(exc).__name__))
    assert not failures, "these expressions were not rejected safely: %r" % failures
    return True


def test_missing_client_attribute_resolves_false_not_raise():
    """A typo in a framework file must degrade, not crash an assessment."""
    assert evaluate("client.this_field_does_not_exist", {}) is False
    return True


def test_compile_condition_returns_ast():
    tree = compile_condition("client.handles_cin")
    assert type(tree).__name__ == "Expression"
    return True


# =====================================================================
# 2. Collector hygiene: gitleaks/trivy/semgrep must not write to the target
# =====================================================================

def _seed_repo(path):
    with open(os.path.join(path, "app.py"), "w", encoding="utf-8") as f:
        f.write('AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"\n')
        f.write('password = "supersecretvalue123"\n')
    with open(os.path.join(path, "requirements.txt"), "w", encoding="utf-8") as f:
        f.write("requests==2.19.1\n")


def test_gitleaks_creates_no_files_in_target():
    """The P0 defect: the gitleaks report was written into the client repo."""
    if not collector.which("gitleaks"):
        print("    (skipped: gitleaks not installed)")
        return True
    d = tempfile.mkdtemp()
    try:
        repo = os.path.join(d, "repo")
        os.makedirs(repo)
        _seed_repo(repo)
        before = set(os.listdir(repo))
        collector.collect_secrets(repo)
        after = set(os.listdir(repo))
        created = after - before
        assert not created, "collector created files in the target: %r" % created
        assert not os.path.exists(os.path.join(repo, ".gitleaks-report.json"))
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_gitleaks_succeeds_against_read_only_directory():
    """A chmod a-w target proves nothing is written into it."""
    if not collector.which("gitleaks"):
        print("    (skipped: gitleaks not installed)")
        return True
    d = tempfile.mkdtemp()
    repo = os.path.join(d, "repo")
    os.makedirs(repo)
    _seed_repo(repo)
    original = stat.S_IMODE(os.stat(repo).st_mode)
    try:
        os.chmod(repo, stat.S_IRUSR | stat.S_IXUSR)
        item = collector.collect_secrets(repo)
        assert item.status in ("ok", "failed"), item.status
        assert item.meta.get("read_only_verified") is True
        return True
    finally:
        os.chmod(repo, original)
        shutil.rmtree(d, ignore_errors=True)


# =====================================================================
# 3. Secret redaction: a seeded secret must never reach an evidence record
# =====================================================================

SEEDED_SECRETS = [
    "AKIAIOSFODNN7EXAMPLE",
    "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "supersecretvalue123",
]


def test_seeded_secret_never_appears_in_evidence():
    d = tempfile.mkdtemp()
    try:
        repo = os.path.join(d, "repo")
        os.makedirs(repo)
        _seed_repo(repo)
        item = collector.collect_secrets(repo)
        blob = "%r %r %r %r" % (item.summary, item.output_excerpt, item.command, item.meta)
        for secret in SEEDED_SECRETS:
            assert secret not in blob, "raw secret %r leaked into EvidenceItem" % secret
        return True
    finally:
        shutil.rmtree(d, ignore_errors=True)


def test_redact_helper_strips_known_shapes():
    samples = [
        "token is AKIAIOSFODNN7EXAMPLE here",
        "ghp_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "sk-ant-abcdefghijklmnopqrstuvwxyz",
        "password: hunter2hunter2",
        "api_key=abcdefgh12345678",
        "-----BEGIN RSA PRIVATE KEY-----",
    ]
    for s in samples:
        out = collector.redact(s)
        assert "[REDACTED]" in out, "no redaction applied to %r -> %r" % (s, out)
    return True


def test_excerpt_is_redacted_and_truncated():
    long_text = "AKIAIOSFODNN7EXAMPLE " * 200
    out = collector._excerpt(long_text, limit=50)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert len(out) <= 120
    return True


# =====================================================================
# 4. Privacy: file evidence stores a hash, never contents
# =====================================================================

def test_file_evidence_stores_no_contents():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "politique.pdf")
        with open(p, "w", encoding="utf-8") as f:
            f.write("CONTENU CONFIDENTIEL - NE PAS STOCKER")
        item = collector.collect_file(p, "Politique de confidentialite revue")
        assert item.status == "ok"
        assert len(item.sha256) == 64
        assert item.meta.get("contents_stored") is False
        assert "CONFIDENTIEL" not in (item.summary + item.output_excerpt)
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
