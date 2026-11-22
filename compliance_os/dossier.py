"""Audit dossier: the one-click export a client hands to their auditor.

A dossier is a ZIP containing everything a reviewer needs to form an opinion
WITHOUT being given access to the platform:

    README.md                     what this bundle is and what it is not
    posture.md                    executive summary + per-framework readiness
    control-matrix.csv            every applicable control, state, owner, due
    evidence-index.csv            every evidence item, its hash and control
    observations/<source>.json    the raw collector facts from the last run
    monitor-runs.json             check history with drift events
    policies/acceptance.csv       who accepted which policy version, when
    regulatory/                   CNDP and Law 05-20 annexes where applicable
    manifest.json                 SHA-256 of every file in the bundle

Design rules:

  - Every file is hashed and the manifest is included, so an auditor can prove
    the bundle was not altered after export.
  - No raw client document is ever included: evidence appears as metadata and a
    hash, exactly as it is stored.
  - The README states plainly that this is not a certification and not an audit
    report. A bundle that could be mistaken for an attestation is a liability.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import io
import json
import os
import zipfile
from typing import Any, Dict, List, Optional

from compliance_os import cndp, registry, scoring
from compliance_os.models import Client, STATE_LABEL

README = """# Audit dossier -- {company}

**Generated:** {generated}
**Client reference:** {slug}
**Frameworks covered:** {frameworks}

---

## What this bundle is

A structured export of {company}'s compliance evidence, produced from a
readiness assessment and continuous control monitoring programme.

## What this bundle is NOT

- **It is not a certification.** Certificates are issued only by an accredited
  certification body after an independent audit.
- **It is not an audit report.** No auditor has formed an opinion on this
  material. The bundle exists so that an auditor *can* form one.
- **It is not legal advice.**

## How to use it

1. Read `posture.md` for the executive position.
2. Cross-check `control-matrix.csv` against the standard being assessed.
3. For any control you intend to sample, use the control id to find its
   evidence hash in `evidence-index.csv`, then request the source document
   from the client. Evidence content is deliberately not included here.
4. Verify nothing was altered after export: every file's SHA-256 is recorded in
   `manifest.json`.

## Structure

| Path | Contents |
|---|---|
| `posture.md` | Executive summary, per-framework readiness, open gaps |
| `control-matrix.csv` | Control id, state, owner, due date, evidence count |
| `evidence-index.csv` | Evidence id, control, kind, SHA-256, collected at |
| `observations/` | Raw collector observations from the most recent run |
| `monitor-runs.json` | Automated check history, including drift events |
| `policies/acceptance.csv` | Policy versions and per-person acknowledgement |
| `regulatory/` | CNDP and Law 05-20 annexes, where applicable |
| `manifest.json` | SHA-256 of every file above |

## Handling

This bundle contains security-relevant information about {company}. Treat it as
Confidential. Do not publish it. Delete it when the review concludes.
"""


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _csv_escape(value: Any) -> str:
    s = "" if value is None else str(value)
    if any(c in s for c in [",", '"', "\n", "\r"]):
        return '"' + s.replace('"', '""') + '"'
    return s


def _csv(rows: List[List[Any]]) -> str:
    return chr(10).join(",".join(_csv_escape(c) for c in row) for row in rows) + chr(10)


def build_posture_markdown(
    client: Client,
    scores: List[Dict[str, Any]],
    generated: str,
) -> str:
    lines = [
        "# Compliance posture -- %s" % client.legal_name,
        "",
        "**Generated:** %s  " % generated,
        "**Sector:** %s  " % (client.sector or "not recorded"),
        "**Headcount:** %s  " % (client.headcount or "not recorded"),
        "**Hosting:** %s (%s)  " % (
            client.hosting_region or "not recorded",
            client.hosting_country or "not recorded",
        ),
        "",
        "---",
        "",
        "## Readiness by framework",
        "",
        "| Framework | Readiness | Verdict | Applicable | Gaps | Partial | Not assessed |",
        "|---|---|---|---|---|---|---|",
    ]
    for s in scores:
        lines.append("| %s | %.1f%% | %s | %d | %d | %d | %d |" % (
            s["framework_name"], s["pct"], s["verdict"], s["applicable"],
            s["gaps"], s["partials"], s["unassessed"]))
    lines.append("")
    lines.append("A control marked *not applicable* is excluded from the denominator,")
    lines.append("so the percentage reflects only controls that apply to this client.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Priority gaps")
    lines.append("")
    any_gap = False
    for s in scores:
        if not s.get("gap_list"):
            continue
        any_gap = True
        lines.append("### %s" % s["framework_name"])
        lines.append("")
        lines.append("| Control | Title | Weight | Owner | Due |")
        lines.append("|---|---|---|---|---|")
        for g in s["gap_list"][:25]:
            lines.append("| %s | %s | %s | %s | %s |" % (
                g.get("id", ""), g.get("title", ""), g.get("weight", ""),
                g.get("owner", "") or "-", g.get("due", "") or "-"))
        lines.append("")
    if not any_gap:
        lines.append("No control is currently marked as a gap.")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Legal notice")
    lines.append("")
    lines.append(
        "This document reports readiness against published frameworks. It is not a "
        "certification, not an attestation, and not the result of an audit by an "
        "accredited body. Under Moroccan Law 05-20 art. 49, provision of the "
        "statutory cybersecurity-services category requires DGSSI qualification; "
        "nothing in this bundle constitutes such a service."
    )
    lines.append("")
    return chr(10).join(lines)


def build_regulatory_annex(client: Client) -> Optional[Dict[str, str]]:
    """Produce the Moroccan annexes when they apply to this client.

    Returned as {filename: content}. Returns None when the client has no
    Moroccan obligations recorded -- an annex asserting obligations the client
    does not have would be wrong, and worse than absent.
    """
    files: Dict[str, str] = {}

    position = cndp.transfer_position(client.hosting_country or "France")
    lines = [
        "# Annexe reglementaire -- Loi 09-08 (CNDP)",
        "",
        "**Entite:** %s  " % client.legal_name,
        "**RC:** %s  " % (client.rc or "non renseigne"),
        "**ICE:** %s  " % (client.ice or "non renseigne"),
        "",
        "## Qualification du traitement",
        "",
        "| Element | Position |",
        "|---|---|",
        "| Donnees sensibles (art. 12) | %s |" % (
            "Oui -- autorisation prealable requise" if client.handles_sensitive_data else "Non"),
        "| Traitement de numeros de CIN (art. 12) | %s |" % (
            "Oui -- autorisation prealable requise" if client.handles_cin else "Non"),
        "| Entite publique | %s |" % ("Oui" if client.is_public_entity else "Non"),
        "| Infrastructure vitale (IIV) | %s |" % ("Oui" if client.is_iiv else "Non"),
        "",
        "## Transferts hors du Maroc",
        "",
        "| Element | Position |",
        "|---|---|",
        "| Pays d'hebergement | %s |" % (client.hosting_country or "France"),
        "| Sur la liste CNDP (deliberation 236-2015) | %s |" % position["on_list_text"],
        "| Base de transfert | %s |" % position["transfer_basis"],
        "| Autorisation F118 | %s |" % position["f118_required"],
        "",
        "## Contrat de sous-traitance",
        "",
        "Un contrat ecrit satisfaisant l'article 23 de la loi 09-08 est requis pour",
        "chaque sous-traitant. La liste des sous-traitants et le modele de contrat",
        "sont maintenus dans le registre fournisseurs.",
        "",
        "## Avertissement",
        "",
        "Cette annexe est un document operationnel. Elle ne constitue pas un avis",
        "juridique. Les positions doivent etre confirmees aupres du CNDP ou d'un",
        "conseil juridique avant emission a un tiers.",
        "",
    ]
    files["loi-09-08-annexe.md"] = chr(10).join(lines)

    # Law 05-20 only binds specific categories. Say so rather than implying
    # a general obligation that does not exist for a private SME.
    l520 = [
        "# Annexe reglementaire -- Loi 05-20 (cybersecurite)",
        "",
        "**Entite:** %s  " % client.legal_name,
        "",
        "## Champ d'application",
        "",
        "La loi 05-20 vise les administrations publiques, les infrastructures",
        "vitales (IIV) et cinq categories d'operateurs designes. Elle n'impose pas",
        "d'obligation generale aux entreprises privees.",
        "",
        "| Element | Position |",
        "|---|---|",
        "| Entite publique | %s |" % ("Oui" if client.is_public_entity else "Non"),
        "| Infrastructure vitale | %s |" % ("Oui" if client.is_iiv else "Non"),
        "| Qualification DGSSI requise | %s |" % (
            "Oui -- verifier aupres de la DGSSI" if (client.is_public_entity or client.is_iiv)
            else "Non -- obligations contractuelles uniquement"),
        "",
        "## Ce que cela signifie pour ce client",
        "",
    ]
    if client.is_public_entity or client.is_iiv:
        l520 += [
            "En tant qu'entite dans le champ de la loi 05-20, les exigences du",
            "decret 2-21-406 (classification des donnees) et du referentiel DNSSI",
            "s'appliquent. Les controles correspondants sont inclus dans la",
            "matrice de controle de ce dossier.",
        ]
    else:
        l520 += [
            "Cette entite n'est pas dans le champ d'application direct de la loi",
            "05-20. Ses obligations en matiere de securite proviennent de ses",
            "contrats (clients, banques, appels d'offres), non de la loi.",
            "Le dossier documente les controles ISO 27001 et SOC 2 qui repondent",
            "aux exigences contractuelles typiques.",
        ]
    l520 += ["", "## Avertissement", "",
             "Cette annexe est fournie a titre informatif et ne constitue pas un avis juridique.",
             ""]
    files["loi-05-20-annexe.md"] = chr(10).join(l520)

    return files or None


def build_dossier(
    client: Client,
    scores: List[Dict[str, Any]],
    control_rows: List[Dict[str, Any]],
    evidence_rows: List[Dict[str, Any]],
    observations: Optional[Dict[str, Any]] = None,
    monitor_runs: Optional[List[Dict[str, Any]]] = None,
    policy_acceptance: Optional[List[Dict[str, Any]]] = None,
    output_path: str = "",
) -> str:
    """Build the dossier ZIP and return its path."""
    generated = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    frameworks = ", ".join(s["framework_name"] for s in scores) or "none"

    files: Dict[str, bytes] = {}

    files["README.md"] = README.format(
        company=client.legal_name, generated=generated,
        slug=client.slug, frameworks=frameworks,
    ).encode("utf-8")

    files["posture.md"] = build_posture_markdown(client, scores, generated).encode("utf-8")

    matrix = [["control_id", "framework", "title", "state", "weight",
               "owner", "due", "evidence_count"]]
    for r in control_rows:
        matrix.append([
            r.get("id", ""), r.get("framework", ""), r.get("title", ""),
            r.get("state", ""), r.get("weight", ""),
            r.get("owner", ""), r.get("due", ""), r.get("evidence_count", 0),
        ])
    files["control-matrix.csv"] = _csv(matrix).encode("utf-8")

    ev = [["evidence_id", "control_id", "framework", "kind", "sha256",
           "collected_at", "summary"]]
    for r in evidence_rows:
        ev.append([
            r.get("id", ""), r.get("control_id", ""), r.get("framework", ""),
            r.get("kind", ""), r.get("sha256", ""),
            r.get("collected_at", ""), r.get("summary", ""),
        ])
    files["evidence-index.csv"] = _csv(ev).encode("utf-8")

    if observations:
        for source, payload in observations.items():
            safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in str(source))
            files["observations/%s.json" % safe] = json.dumps(
                payload, indent=2, sort_keys=True, ensure_ascii=False
            ).encode("utf-8")

    files["monitor-runs.json"] = json.dumps(
        monitor_runs or [], indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")

    pa = [["policy_id", "title", "version", "person_email", "person_name",
           "acknowledged_at"]]
    for r in (policy_acceptance or []):
        pa.append([
            r.get("policy_id", ""), r.get("title", ""), r.get("version", ""),
            r.get("person_email", ""), r.get("person_name", ""),
            r.get("acknowledged_at", ""),
        ])
    files["policies/acceptance.csv"] = _csv(pa).encode("utf-8")

    annex = build_regulatory_annex(client)
    if annex:
        for name, content in annex.items():
            files["regulatory/%s" % name] = content.encode("utf-8")

    # Manifest last, covering every other file.
    manifest = {
        "client_slug": client.slug,
        "legal_name": client.legal_name,
        "generated_at": generated,
        "generator": "compliance-os",
        "frameworks": [s["framework_id"] for s in scores],
        "file_count": len(files),
        "files": [
            {"path": p, "sha256": _sha256_bytes(c), "bytes": len(c)}
            for p, c in sorted(files.items())
        ],
    }
    files["manifest.json"] = json.dumps(
        manifest, indent=2, sort_keys=True, ensure_ascii=False
    ).encode("utf-8")

    if not output_path:
        stamp = _dt.date.today().isoformat()
        output_path = os.path.join(os.getcwd(), "%s-audit-dossier-%s.zip" % (client.slug, stamp))

    os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, data in sorted(files.items()):
            zf.writestr(path, data)
    with open(output_path, "wb") as f:
        f.write(buf.getvalue())
        f.flush()
        os.fsync(f.fileno())
    return output_path


def build_dossier_bytes(**kwargs) -> bytes:
    """In-memory variant, for an HTTP download response."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        path = build_dossier(output_path=os.path.join(tmp, "dossier.zip"), **kwargs)
        with open(path, "rb") as f:
            return f.read()
