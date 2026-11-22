"""Evidence collectors.

Design rule, and it is a safety rule not a style preference: every collector in
this module is strictly READ-ONLY with respect to the client's environment.
Nothing writes to a client repository, cloud account, or SaaS tenant.

Collector hygiene invariants (each one has a regression test):

1. No file is created inside the target directory. Scan tools are given a
   report path inside a `tempfile.TemporaryDirectory()` that the OS cleans up.
   One older revision wrote the gitleaks report into the repository root; that
   is a read-only violation and is now tested against.
2. No raw secret material is persisted. Gitleaks runs with `--redact`, and any
   `output_excerpt` is scrubbed of likely secret values before storage.
3. A collector never decides a control is passing. It records an observation.
   A human sets the control state.

Credential handling: collectors read credentials from the process environment
only (e.g. GITHUB_TOKEN, AWS_PROFILE). They are never accepted as CLI
arguments, never written to workspace files, and never echoed in an
`EvidenceItem`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple

from compliance_os.models import EvidenceItem

# Patterns used to scrub anything that looks like a live credential out of
# stored text. Deliberately broad: a false positive costs a truncated excerpt.
_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),                        # AWS access key id
    re.compile(r"ASIA[0-9A-Z]{16}"),                        # AWS temp key id
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),              # GitHub tokens
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),            # GitHub fine-grained
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),            # Slack
    re.compile(r"sk-[A-Za-z0-9]{20,}"),                     # OpenAI-style
    re.compile(r"sk-ant-[A-Za-z0-9-]{20,}"),                # Anthropic
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),      # private keys
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWTs
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key)\s*[:=]\s*[\"']?[^\s\"',]{8,}"),
]

REDACTED = "[REDACTED]"


def redact(text: str) -> str:
    """Remove anything resembling a credential from text destined for storage."""
    if not text:
        return ""
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub(REDACTED, out)
    return out


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def which(tool: str) -> Optional[str]:
    return shutil.which(tool)


def _run(cmd: List[str], cwd: Optional[str] = None, timeout: int = 600) -> Tuple[int, str, str]:
    """Run a command and return (rc, stdout, stderr). Never raises on non-zero."""
    try:
        p = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
        )
        return p.returncode, p.stdout or "", p.stderr or ""
    except FileNotFoundError:
        return 127, "", "tool not found: %s" % cmd[0]
    except subprocess.TimeoutExpired:
        return 124, "", "timeout after %ss" % timeout


def _excerpt(text: str, limit: int = 1200) -> str:
    """Truncate AND redact. Storage must never contain raw secret material."""
    safe = redact((text or "").strip())
    if len(safe) <= limit:
        return safe
    return safe[:limit] + " ... [truncated]"


# ------------------------------------------------------------------ gitleaks
def collect_secrets(repo: str) -> EvidenceItem:
    """Detect committed credentials. Strictly read-only against `repo`.

    The gitleaks report is written to a temporary directory outside the target,
    and `--redact` prevents secret values from appearing in output at all.
    """
    exe = which("gitleaks")
    if not exe:
        return EvidenceItem(
            kind="command", status="skipped", collector="gitleaks",
            summary="gitleaks not installed; no secret scan performed",
            source=repo,
        )

    repo_abs = os.path.abspath(repo)
    if not os.path.isdir(repo_abs):
        return EvidenceItem(
            kind="command", status="failed", collector="gitleaks",
            source=repo, summary="target is not a directory: %s" % repo,
        )

    findings = 0
    rules: Dict[str, int] = {}
    files: List[str] = []
    rc = 0
    raw_err = ""

    # TemporaryDirectory is outside the target by construction.
    with tempfile.TemporaryDirectory(prefix="compliance-gitleaks-") as tmp:
        report = os.path.join(tmp, "report.json")
        cmd = [
            exe, "detect",
            "--source", repo_abs,
            "--report-format", "json",
            "--report-path", report,
            "--redact",
            "--exit-code", "0",
            "--no-banner",
        ]
        if not os.path.isdir(os.path.join(repo_abs, ".git")):
            cmd.append("--no-git")
        rc, out, err = _run(cmd, timeout=900)
        raw_err = err

        if os.path.isfile(report):
            try:
                with open(report, encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else data.get("findings", [])
                findings = len(items)
                for item in items:
                    rule = item.get("RuleID") or item.get("ruleId") or "unknown"
                    rules[rule] = rules.get(rule, 0) + 1
                    path = item.get("File") or item.get("file") or ""
                    if path and path not in files:
                        files.append(path)
            except Exception:
                pass

    # Verify the invariant every time, not just in tests.
    leaked = _files_created_by_scan(repo_abs)
    summary = "secret scan: %d potential finding(s)" % findings
    if rules:
        summary += " (" + ", ".join("%s=%d" % (k, v) for k, v in sorted(rules.items())) + ")"
    if findings == 0:
        summary += " -- NOTE: an allowlisted test key returns 0; silence is not proof"

    return EvidenceItem(
        kind="command",
        status="ok" if rc == 0 else "failed",
        collector="gitleaks",
        source=repo_abs,
        command="gitleaks detect --redact --source <target>",
        summary=summary,
        output_excerpt=_excerpt(raw_err if findings == 0 else ""),
        sha256=sha256_text(json.dumps({"findings": findings, "rules": rules}, sort_keys=True)),
        meta={
            "findings": findings,
            "rule_ids": rules,
            "files_affected": files[:50],
            "read_only_verified": not leaked,
            "returncode": rc,
        },
    )


def _files_created_by_scan(target: str) -> List[str]:
    """Return any stray report files an older implementation might have left."""
    stray = []
    for name in (".gitleaks-report.json", "gitleaks-report.json", "trivy-report.json"):
        p = os.path.join(target, name)
        if os.path.exists(p):
            stray.append(p)
    return stray


# --------------------------------------------------------------------- trivy
def collect_deps(path: str) -> EvidenceItem:
    """Known-vulnerable dependencies. Read-only; report goes to a temp dir."""
    exe = which("trivy")
    if not exe:
        return EvidenceItem(
            kind="command", status="skipped", collector="trivy",
            summary="trivy not installed; no dependency scan performed", source=path,
        )

    path_abs = os.path.abspath(path)
    counts: Dict[str, int] = {}
    total = 0
    worst = ""
    rank = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}

    with tempfile.TemporaryDirectory(prefix="compliance-trivy-") as tmp:
        out_path = os.path.join(tmp, "report.json")
        cmd = [
            exe, "fs", "--quiet", "--format", "json",
            "--scanners", "vuln", "--output", out_path, path_abs,
        ]
        rc, out, err = _run(cmd, timeout=1200)
        if os.path.isfile(out_path):
            try:
                with open(out_path, encoding="utf-8") as f:
                    data = json.load(f)
                for res in data.get("Results", []) or []:
                    for v in res.get("Vulnerabilities", []) or []:
                        total += 1
                        sev = (v.get("Severity") or "UNKNOWN").upper()
                        counts[sev] = counts.get(sev, 0) + 1
                        if not worst or rank.get(sev, 9) < rank.get(worst, 9):
                            worst = sev
            except Exception:
                pass

    summary = "dependency scan: %d vulnerable package(s)" % total
    if counts:
        summary += " (" + ", ".join("%s=%d" % (k, v) for k, v in sorted(counts.items())) + ")"

    return EvidenceItem(
        kind="command", status="ok" if rc == 0 else "failed",
        collector="trivy", source=path_abs,
        command="trivy fs --scanners vuln --format json <target>",
        summary=summary,
        output_excerpt=_excerpt(err),
        sha256=sha256_text(json.dumps({"total": total, "by_severity": counts}, sort_keys=True)),
        meta={
            "vulnerabilities": total,
            "by_severity": counts,
            "worst_severity": worst,
            "read_only_verified": not _files_created_by_scan(path_abs),
            "returncode": rc,
        },
    )


# ------------------------------------------------------------------- semgrep
def collect_code(repo: str, config: str = "p/default") -> EvidenceItem:
    """Static analysis for dangerous patterns. Read-only against the target."""
    exe = which("semgrep")
    if not exe:
        return EvidenceItem(
            kind="command", status="skipped", collector="semgrep",
            summary="semgrep not installed; no code scan performed", source=repo,
        )

    repo_abs = os.path.abspath(repo)
    with tempfile.TemporaryDirectory(prefix="compliance-semgrep-") as tmp:
        out_path = os.path.join(tmp, "report.json")
        cmd = [
            exe, "--config", config, "--json", "--quiet", "--metrics", "off",
            "--timeout", "120", "--output", out_path, repo_abs,
        ]
        rc, out, err = _run(cmd, timeout=2400)
        findings = 0
        sev: Dict[str, int] = {}
        if os.path.isfile(out_path):
            try:
                with open(out_path, encoding="utf-8") as f:
                    data = json.load(f)
                results = data.get("results", []) or []
                findings = len(results)
                for r in results:
                    s = ((r.get("extra") or {}).get("severity") or "INFO").upper()
                    sev[s] = sev.get(s, 0) + 1
            except Exception:
                pass

    summary = "code scan: %d finding(s)" % findings
    if sev:
        summary += " (" + ", ".join("%s=%d" % (k, v) for k, v in sorted(sev.items())) + ")"

    return EvidenceItem(
        kind="command", status="ok" if rc in (0, 1) else "failed",
        collector="semgrep", source=repo_abs,
        command="semgrep --config %s <target>" % config,
        summary=summary,
        output_excerpt=_excerpt(err if findings == 0 else ""),
        sha256=sha256_text(json.dumps({"findings": findings, "by_severity": sev}, sort_keys=True)),
        meta={"findings": findings, "by_severity": sev, "returncode": rc},
    )


# ---------------------------------------------------------------- file hash
def collect_file(path: str, description: str = "") -> EvidenceItem:
    """Hash a document so the evidence proves WHICH version was reviewed.

    This is the privacy-by-design primitive: we record the hash, size and path,
    never the contents. A client can prove a document existed without giving us
    its text.
    """
    if not os.path.isfile(path):
        return EvidenceItem(
            kind="file", status="failed", collector="hash", source=path,
            summary="file not found: %s" % path,
        )
    digest = sha256_file(path)
    size = os.path.getsize(path)
    return EvidenceItem(
        kind="file", status="ok", collector="hash", source=path,
        summary=redact(description) or ("hashed %s" % os.path.basename(path)),
        sha256=digest, path=os.path.abspath(path),
        meta={"bytes": size, "contents_stored": False},
    )


# ----------------------------------------------------------------- attestation
def attestation(summary: str, source: str = "", note: str = "") -> EvidenceItem:
    """A human statement with a recorded timestamp."""
    return EvidenceItem(
        kind="attestation", status="ok", collector="human",
        source=redact(source), summary=redact(summary), output_excerpt=redact(note),
    )


COLLECTORS = {
    "secrets": "detect committed credentials in a repository (read-only)",
    "deps": "detect known-vulnerable dependencies (read-only)",
    "code": "static analysis for dangerous patterns (read-only)",
    "file": "hash a document to prove which version was reviewed",
    "attestation": "record a human statement with a timestamp",
}
