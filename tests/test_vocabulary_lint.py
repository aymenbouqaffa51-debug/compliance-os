"""Vocabulary lint: the Law 05-20 art. 49 guardrail as an automated test.

Law 05-20 art. 49 makes unqualified provision of "prestations de cybersecurite"
or of sensitive-system audit services a 200,000-400,000 MAD offence. The words
"audit", "pentest" and "cybersecurity service" therefore must not appear as a
description of what this product does.

They MAY legitimately appear:
  - inside a disclaimer (negating them explicitly)
  - inside a legal-reference context (quoting the law)
  - in a code comment explaining the restriction
  - in this test file itself

This test scans every shipped string (Python, YAML, Markdown templates, docs)
and fails if a forbidden term appears outside an allowed context. It is the
cheapest way to keep a salesperson from writing "we audit your systems" into a
proposal six months from now.
"""

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Terms that must not be used to DESCRIBE our own service.
FORBIDDEN = [
    r"\bauditons\b",
    r"\bnous\s+auditons\b",
    r"\bpentest\b",
    r"\bpenetration\s+test",
    r"\bprestations?\s+de\s+cybersecurite\b",
    r"\bprestations?\s+de\s+cybers\u00e9curit\u00e9\b",
    r"\bSOC\s*2\s+certification\b",
    r"\bISO\s*27001\s+certification\b",
    r"\bnous\s+certifions\b",
    r"\bwe\s+certify\b",
    r"\bwe\s+audit\b",
    r"\bwe\s+issue\s+SOC\s*2\b",
    r"\bwe\s+perform\s+an?\s+audit\b",
]

# A line containing any of these is treated as an allowed legal/disclaimer
# context and is skipped.
ALLOW_CONTEXT = [
    "art. 49",
    "article 49",
    "art.49",
    "loi 05-20",
    "law 05-20",
    "NEVER",
    "never",
    "interdit",
    "forbidden",
    "disclaimer",
    "avertissement",
    "not an audit",
    "n'est pas un audit",
    "ne constitue pas",
    "ne constitue ni",
    "is not legal advice",
    "200,000",
    "200 000",
    "400,000",
    "400 000",
    "DGSSI qualification",
    "qualification DGSSI",
    "sanction",
    "fine",
    "amende",
    "#",
    '"""',
    "'''",
]

# Files allowed to mention the terms freely.
SKIP_FILES = {
    "test_vocabulary_lint.py",
    "MOROCCO-RULES.md",
    "01-morocco-regulation.md",
    "02-morocco-entity-tax.md",
    "04-oss-stack.md",
    "06-market-recovered.md",
    "09-vanta-partner-terms.md",
}

# Directory names to skip entirely.
SKIP_DIRS = {
    "__pycache__", ".git", ".venv", "venv", "node_modules",
    "dist", "build", ".pytest_cache", "_raw", ".mypy_cache",
    ".ruff_cache", "htmlcov", ".eggs",
}

SCAN_EXT = (".py", ".yaml", ".yml", ".md", ".txt", ".toml", ".sh")


def _iter_files():
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(SCAN_EXT):
                continue
            if fn in SKIP_FILES:
                continue
            if fn.endswith(".min.js") or fn.endswith(".lock"):
                continue
            yield os.path.join(dirpath, fn)


def _allowed(line: str) -> bool:
    return any(marker in line for marker in ALLOW_CONTEXT)


def scan():
    violations = []
    for path in _iter_files():
        try:
            text = open(path, encoding="utf-8", errors="ignore").read()
        except Exception:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or _allowed(line):
                continue
            for pattern in FORBIDDEN:
                if re.search(pattern, line, re.IGNORECASE):
                    violations.append(
                        (os.path.relpath(path, ROOT), lineno, stripped[:120])
                    )
                    break
    return violations


def test_no_forbidden_vocabulary():
    violations = scan()
    if violations:
        msg = ["Forbidden art.49-adjacent vocabulary found in shipped strings:"]
        for f, n, s in violations[:40]:
            msg.append("  %s:%d  %s" % (f, n, s))
        if len(violations) > 40:
            msg.append("  ... and %d more" % (len(violations) - 40))
        msg.append("")
        msg.append(
            "Say 'readiness assessment', 'gap assessment', "
            "'evidence automation', 'continuous control monitoring' instead."
        )
        msg.append("See docs/MOROCCO-RULES.md.")
        raise AssertionError("\n".join(msg))
    return True


def test_lint_detects_a_seeded_violation():
    """Prove the lint actually fires, so a silent pass means something."""
    bad = "Nous realisons un pentest complet et un penetration test de vos systemes."
    hits = [p for p in FORBIDDEN if re.search(p, bad, re.IGNORECASE)]
    assert hits, "the lint failed to flag a clearly forbidden sentence"
    return True


def test_allowed_context_is_not_flagged():
    """A disclaimer line must not trip the lint."""
    ok = "This is not an audit and not a pentest, per law 05-20 art. 49."
    assert _allowed(ok), "a legitimate disclaimer line was not recognised as allowed"
    return True


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
            print("  FAIL  %s" % name)
            print(exc)
            failed += 1
    print()
    print("%d passed, %d failed, %d total" % (passed, failed, len(tests)))
    raise SystemExit(0 if failed == 0 else 1)
