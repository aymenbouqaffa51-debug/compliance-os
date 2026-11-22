"""Workspace lifecycle operations: doctor, offboard, template finalisation.

`doctor`        - verify the environment before a client engagement
`offboard`      - produce a handover archive + deletion certificate
`finalise`      - refuse to render a legal template with placeholders left

These live in their own module so the CLI stays readable and each one can be
tested without argparse.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import re
import shutil
import sys
import tempfile
import zipfile
from typing import Dict, List, Tuple

from compliance_os import registry
from compliance_os.models import SCHEMA_VERSION


# --------------------------------------------------------------------- doctor
MIN_PYTHON = (3, 10)

REQUIRED_DEPS = {"yaml": "PyYAML"}

OPTIONAL_TOOLS = {
    "gitleaks": "secret scanning (ISO A.8.24)",
    "trivy": "dependency scanning (ISO A.8.8)",
    "semgrep": "static analysis (ISO A.8.25)",
    "prowler": "cloud posture (ISO A.8.8)",
}


def doctor(workspace_root: str) -> Tuple[bool, List[str]]:
    """Return (ok, lines). Never raises."""
    lines: List[str] = []
    ok = True

    # --- python
    v = sys.version_info
    vstr = "%d.%d.%d" % (v.major, v.minor, v.micro)
    if (v.major, v.minor) >= MIN_PYTHON:
        lines.append("[ok]      Python %s (>= %d.%d required)" % (vstr, *MIN_PYTHON))
    else:
        lines.append("[FAIL]    Python %s (>= %d.%d required)" % (vstr, *MIN_PYTHON))
        ok = False

    lines.append("[ok]      Platform %s %s" % (platform.system(), platform.release()))

    # --- dependencies
    for mod, dist in REQUIRED_DEPS.items():
        try:
            __import__(mod)
            lines.append("[ok]      dependency %s" % dist)
        except ImportError:
            lines.append("[FAIL]    dependency %s is missing (pip install %s)" % (dist, dist))
            ok = False

    # --- optional scanners
    for tool, purpose in OPTIONAL_TOOLS.items():
        path = shutil.which(tool)
        if path:
            lines.append("[ok]      %-9s %s" % (tool, purpose))
        else:
            lines.append("[optional] %-8s not installed - %s unavailable" % (tool, purpose))

    # --- workspace
    ws = registry.Workspace(workspace_root)
    if os.path.isdir(ws.root):
        lines.append("[ok]      workspace %s" % ws.root)
        try:
            os.makedirs(ws.root, exist_ok=True)
            probe = os.path.join(ws.root, ".doctor-probe")
            registry.atomic_write_text(probe, "ok")
            os.remove(probe)
            lines.append("[ok]      workspace is writable")
        except Exception as exc:
            lines.append("[FAIL]    workspace not writable: %s" % exc)
            ok = False
    else:
        lines.append("[warn]    workspace %s does not exist yet (compliance init)" % ws.root)

    # --- frameworks
    try:
        ids = registry.framework_ids()
        if ids:
            total = sum(len(registry.load_framework(f).controls) for f in ids)
            lines.append("[ok]      %d frameworks, %d controls" % (len(ids), total))
        else:
            lines.append("[FAIL]    no frameworks found")
            ok = False
    except Exception as exc:
        lines.append("[FAIL]    frameworks could not load: %s" % exc)
        ok = False

    # --- client integrity
    broken = []
    for slug in ws.list_clients():
        try:
            ws.load_client(slug)
        except Exception as exc:
            broken.append("%s (%s)" % (slug, exc))
    if broken:
        lines.append("[FAIL]    unreadable client workspaces: %s" % "; ".join(broken))
        ok = False
    elif ws.list_clients():
        lines.append("[ok]      %d client workspaces readable (schema %d)" % (
            len(ws.list_clients()), SCHEMA_VERSION))

    return ok, lines


# ------------------------------------------------------------------- offboard
class OffboardError(Exception):
    pass


def offboard(workspace_root: str, slug: str, output_dir: str = "", keep_local: bool = False) -> Dict[str, str]:
    """Archive a client workspace, hash every file, and delete it.

    Produces:
      <slug>-offboard-<date>.zip    the full workspace
      <slug>-manifest-<date>.json   sha256 of every file inside the zip
      <slug>-deletion-certificate-<date>.md

    The certificate is the artefact a client's procurement team will ask for,
    because it is the evidence that you honour the deletion duty.
    """
    ws = registry.Workspace(workspace_root)
    registry.validate_slug(slug)
    client_dir = ws.client_dir(slug)
    if not os.path.isdir(client_dir):
        raise OffboardError("unknown client %r" % slug)

    client = ws.load_client(slug)
    stamp = _dt.date.today().isoformat()
    out = output_dir or os.getcwd()
    os.makedirs(out, exist_ok=True)

    zip_path = os.path.join(out, "%s-offboard-%s.zip" % (slug, stamp))
    manifest_path = os.path.join(out, "%s-manifest-%s.json" % (slug, stamp))
    cert_path = os.path.join(out, "%s-deletion-certificate-%s.md" % (slug, stamp))

    # Collect files + hashes BEFORE zipping, so the manifest describes exactly
    # what the recipient receives.
    entries: List[Dict[str, str]] = []
    for dirpath, _dirnames, filenames in os.walk(client_dir):
        for fn in sorted(filenames):
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, client_dir)
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            entries.append({"path": rel, "sha256": h.hexdigest(), "bytes": os.path.getsize(full)})

    manifest = {
        "client_slug": slug,
        "legal_name": client.legal_name,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "schema_version": SCHEMA_VERSION,
        "file_count": len(entries),
        "files": entries,
    }

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, _dirnames, filenames in os.walk(client_dir):
            for fn in sorted(filenames):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, client_dir)
                zf.write(full, os.path.join(slug, rel))

    registry.atomic_write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    zip_digest = hashlib.sha256()
    with open(zip_path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            zip_digest.update(chunk)

    cert = """# Certificate of deletion

**Client:** {legal_name} (`{slug}`)  
**Date:** {date}  
**Files in archive:** {count}

## What was handed over

- Archive: `{zip_name}`
- Archive SHA-256: `{zip_sha}`
- Manifest: `{manifest_name}` (SHA-256 of every file inside the archive)

## What was deleted

The client workspace directory was removed from the operator's system after the
archive above was written and its hash recorded. It is no longer present in the
workspace `{root}`.

## Legal basis

This deletion implements:

- **Loi 09-08, art. 23** -- the processor acts on the controller's instruction and
  returns or deletes the data at the end of the engagement.
- **Loi 09-08, arts. 54-56** -- retention beyond the declared purpose is
  sanctioned; deleting on exit is how retention is actually respected.
- **The CNDP data-minimisation expectation** that a processor holds no more than
  the client's instruction requires.

This certificate is an operational record. It is not a legal opinion and does
not replace the controller's own records.

## Signature

_______________________
{signer}
""".format(
        legal_name=client.legal_name,
        slug=slug,
        date=stamp,
        count=len(entries),
        zip_name=os.path.basename(zip_path),
        zip_sha=zip_digest.hexdigest(),
        manifest_name=os.path.basename(manifest_path),
        root=ws.root,
        signer=client.contact_name or "(operator)",
    )
    registry.atomic_write_text(cert_path, cert)

    deleted = False
    if not keep_local:
        shutil.rmtree(client_dir)
        deleted = not os.path.isdir(client_dir)

    return {
        "zip": zip_path,
        "manifest": manifest_path,
        "certificate": cert_path,
        "zip_sha256": zip_digest.hexdigest(),
        "files": str(len(entries)),
        "deleted": str(deleted),
    }


# ----------------------------------------------------------- template finalise
_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
_UNFILLED_RE = re.compile(r"\[A compl[ée]ter\]|\[COMPL[EÉ]TER\]|\[TODO\]", re.IGNORECASE)

LEGAL_BANNER = (
    "> **AVERTISSEMENT / DISCLAIMER** -- Ce document est un modele operationnel "
    "fourni a titre d'aide a la redaction. Il ne constitue pas un avis juridique et "
    "doit etre revu par un avocat avant signature. Les mentions relatives a la loi "
    "09-08 et a la loi 05-20 sont fournies a titre informatif.\n"
    "> This document is an operational template. It is not legal advice and must be "
    "reviewed by a lawyer before signature.\n"
)


def audit_template(text: str) -> Dict[str, List[str]]:
    """Return the placeholders and unfilled markers still present."""
    return {
        "placeholders": sorted(set(_PLACEHOLDER_RE.findall(text))),
        "unfilled": sorted(set(m.group(0) for m in _UNFILLED_RE.finditer(text))),
    }


def finalise_template(text: str, strict: bool = True) -> str:
    """Stamp the legal banner and, in strict mode, refuse unfinished output."""
    report = audit_template(text)
    if strict and (report["placeholders"] or report["unfilled"]):
        problems = []
        if report["placeholders"]:
            problems.append("placeholders: %s" % ", ".join(report["placeholders"]))
        if report["unfilled"]:
            problems.append("unfilled markers: %s" % ", ".join(report["unfilled"]))
        raise ValueError("--final refused: template is incomplete (%s)" % "; ".join(problems))
    if "AVERTISSEMENT / DISCLAIMER" not in text:
        text = LEGAL_BANNER + "\n" + text
    return text
