"""Report generation.

The gap report is the product you sell. It has to be honest, specific, and
have a clear next action on every line -- a client who reads it should know
exactly what to do on Monday morning.

Language: French by default. The buyer is Moroccan or francophone European, and
the Moroccan legal vocabulary only exists properly in French.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Dict, List

from compliance_os import scoring
from compliance_os.models import (
    STATE_NOT_APPLICABLE,
    STATE_LABEL,
    Assessment,
    Client,
    Framework,
)

TXT = {
    "fr": {
        "gap_title": "Rapport d'écart (gap assessment)",
        "evidence_title": "Registre des preuves",
        "summary_title": "Synthèse de conformité",
        "client": "Client",
        "sector": "Secteur",
        "headcount": "Effectif",
        "contact": "Contact",
        "markets": "Marchés à l'export",
        "framework": "Référentiel",
        "generated": "Généré le",
        "assessor": "Évaluateur",
        "readiness": "Niveau de préparation",
        "controls_total": "Contrôles du référentiel",
        "controls_applicable": "Contrôles applicables",
        "excluded": "Exclus (non applicables)",
        "gaps": "Écarts à traiter",
        "partials": "Partiellement mis en oeuvre",
        "unassessed": "Non évalués",
        "evidence_items": "Éléments de preuve",
        "priority": "Ordre de priorité",
        "objective": "Objectif du contrôle",
        "evidence_expected": "Preuves attendues",
        "owner": "Responsable",
        "due": "Échéance",
        "notes": "Observations",
        "none": "aucun",
        "verdict_audit_ready": "Prêt pour l'audit",
        "verdict_near": "Proche de la maturité",
        "verdict_material": "Écarts matériels",
        "verdict_early": "Phase initiale",
        "disclaimer": (
            "Ce rapport est une évaluation de préparation. Il ne constitue ni une "
            "certification, ni un audit au sens de la loi 05-20, ni un avis juridique. "
            "La certification ISO/IEC 27001 est délivrée par un organisme de "
            "certification indépendant et accrédité. Un rapport SOC 2 est une "
            "attestation délivrée par un cabinet CPA licencié."
        ),
        "next_step": "Prochaine étape recommandée",
        "method": "Méthode",
        "scope_note": (
            "Les contrôles marocains sont fournis comme référentiel de bonnes pratiques. "
            "La loi 05-20 ne crée pas d'obligation générale pour les sociétés privées "
            "ordinaires ; elle vise les entités publiques, les infrastructures "
            "d'importance vitale et certaines catégories d'opérateurs."
        ),
    },
    "en": {
        "gap_title": "Gap assessment report",
        "evidence_title": "Evidence register",
        "summary_title": "Compliance summary",
        "client": "Client",
        "sector": "Sector",
        "headcount": "Headcount",
        "contact": "Contact",
        "markets": "Export markets",
        "framework": "Framework",
        "generated": "Generated",
        "assessor": "Assessor",
        "readiness": "Readiness",
        "controls_total": "Framework controls",
        "controls_applicable": "Applicable controls",
        "excluded": "Excluded (not applicable)",
        "gaps": "Gaps to remediate",
        "partials": "Partially implemented",
        "unassessed": "Not assessed",
        "evidence_items": "Evidence items",
        "priority": "Priority order",
        "objective": "Control objective",
        "evidence_expected": "Evidence expected",
        "owner": "Owner",
        "due": "Due",
        "notes": "Notes",
        "none": "none",
        "verdict_audit_ready": "Audit-ready",
        "verdict_near": "Near-ready",
        "verdict_material": "Material gaps",
        "verdict_early": "Early stage",
        "disclaimer": (
            "This report is a readiness assessment. It is not a certification, nor an "
            "audit within the meaning of Law 05-20, nor legal advice. ISO/IEC 27001 "
            "certification is issued by an independent accredited certification body. "
            "A SOC 2 report is an attestation issued by a licensed CPA firm."
        ),
        "next_step": "Recommended next step",
        "method": "Method",
        "scope_note": (
            "Moroccan controls are provided as a good-practice reference. Law 05-20 "
            "does not create a general duty for ordinary private companies; it covers "
            "public entities, vital infrastructures and certain operator categories."
        ),
    },
}

VERDICT_KEY = {
    "audit-ready": "verdict_audit_ready",
    "near-ready": "verdict_near",
    "material gaps": "verdict_material",
    "early stage": "verdict_early",
}


def _stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _bar(pct: float, width: int = 30) -> str:
    filled = int(round(width * pct / 100.0))
    return "`" + "#" * filled + "." * (width - filled) + "`"


def _next_step(s: scoring.Score, lang: str) -> str:
    if s.gaps:
        top = s.gaps[0]
        if lang == "fr":
            return (
                "Traiter en premier **%s — %s** (poids %.1f). C'est l'écart qui coûte "
                "le plus cher en crédibilité face à un acheteur. Cible : 30 jours."
                % (top["id"], top["title"], top["weight"])
            )
        return (
            "Start with **%s — %s** (weight %.1f). It is the gap that costs the most "
            "credibility with a buyer. Target: 30 days."
            % (top["id"], top["title"], top["weight"])
        )
    if s.partials:
        top = s.partials[0]
        if lang == "fr":
            return (
                "Finaliser **%s — %s**, déjà partiellement en place. Il manque "
                "généralement la preuve documentée, pas le contrôle lui-même."
                % (top["id"], top["title"])
            )
        return (
            "Finish **%s — %s**, which is already partly in place. What is usually "
            "missing is the documented evidence, not the control itself."
            % (top["id"], top["title"])
        )
    if s.unassessed:
        top = s.unassessed[0]
        if lang == "fr":
            return "Évaluer **%s — %s** : c'est le contrôle non évalué au poids le plus élevé." % (
                top["id"], top["title"])
        return "Assess **%s — %s**: the highest-weight control not yet evaluated." % (
            top["id"], top["title"])
    if lang == "fr":
        return "Aucun écart ouvert. Programmer la revue trimestrielle et revérifier les preuves."
    return "No open gaps. Schedule the quarterly review and re-verify evidence."


def _header(t: Dict[str, str], client: Client, fw: Framework, lang: str) -> List[str]:
    out = []
    out.append("# %s" % t["gap_title"])
    out.append("")
    out.append("**%s :** %s  " % (t["client"], client.legal_name))
    if client.sector:
        out.append("**%s :** %s  " % (t["sector"], client.sector))
    if client.headcount:
        out.append("**%s :** %s  " % (t["headcount"], client.headcount))
    if client.export_markets:
        out.append("**%s :** %s  " % (t["markets"], ", ".join(client.export_markets)))
    out.append("**%s :** %s (%s)  " % (t["framework"], fw.name, fw.version))
    out.append("**%s :** %s  " % (t["generated"], _stamp()))
    if client.contact_name:
        out.append("**%s :** %s  " % (t["contact"], client.contact_name))
    out.append("")
    return out


def write_gap_report(ws, client: Client, fw: Framework, a: Assessment, lang: str = "fr") -> str:
    t = TXT.get(lang, TXT["fr"])
    s = scoring.score(fw, client, a)
    L: List[str] = []
    L += _header(t, client, fw, lang)
    L.append("---")
    L.append("")
    L.append("## %s" % t["readiness"])
    L.append("")
    L.append("### %s" % _bar(s.pct))
    L.append("")
    L.append("**%.1f%%** — %s" % (s.pct, t[VERDICT_KEY[scoring.readiness_verdict(s.pct)]]))
    L.append("")
    L.append("| | |")
    L.append("|---|---|")
    L.append("| %s | %d |" % (t["controls_total"], s.total))
    L.append("| %s | %d |" % (t["controls_applicable"], s.applicable))
    L.append("| %s | %d |" % (t["excluded"], s.by_state.get(STATE_NOT_APPLICABLE, 0)))
    L.append("| %s | **%d** |" % (t["gaps"], len(s.gaps)))
    L.append("| %s | %d |" % (t["partials"], len(s.partials)))
    L.append("| %s | %d |" % (t["unassessed"], len(s.unassessed)))
    total_ev = sum(len(r.evidence) for r in a.rows.values())
    L.append("| %s | %d |" % (t["evidence_items"], total_ev))
    L.append("")
    L.append("> **%s :** %s" % (t["next_step"], _next_step(s, lang)))
    L.append("")

    if s.gaps:
        L.append("---")
        L.append("")
        L.append("## %s (%d)" % (t["gaps"], len(s.gaps)))
        L.append("")
        L.append("| # | ID | " + t["objective"][:40] + " | Poids |")
        L.append("|---|---|---|---|")
        for i, g in enumerate(s.gaps, 1):
            L.append("| %d | **%s** | %s | %.1f |" % (i, g["id"], g["title"], g["weight"]))
        L.append("")
        for i, g in enumerate(s.gaps, 1):
            L.append("### %d. %s — %s" % (i, g["id"], g["title"]))
            L.append("")
            if g["ref"]:
                L.append("*Réf. %s*" % g["ref"])
                L.append("")
            if g["objective"]:
                L.append("**%s :** %s" % (t["objective"], g["objective"].strip()))
                L.append("")
            if g["evidence_expected"]:
                L.append("**%s :**" % t["evidence_expected"])
                L.append("")
                for e in g["evidence_expected"]:
                    L.append("- %s" % e)
                L.append("")
            meta = []
            if g["owner"]:
                meta.append("%s : %s" % (t["owner"], g["owner"]))
            if g["due"]:
                meta.append("%s : %s" % (t["due"], g["due"]))
            if meta:
                L.append("*" + " · ".join(meta) + "*")
                L.append("")
            if g["notes"]:
                L.append("> %s" % g["notes"])
                L.append("")

    if s.partials:
        L.append("---")
        L.append("")
        L.append("## %s (%d)" % (t["partials"], len(s.partials)))
        L.append("")
        L.append("| ID | Contrôle | Poids | Preuves |")
        L.append("|---|---|---|---|")
        for p in s.partials:
            L.append("| **%s** | %s | %.1f | %d |" % (p["id"], p["title"], p["weight"], p["evidence_count"]))
        L.append("")

    if s.unassessed:
        L.append("---")
        L.append("")
        L.append("## %s (%d)" % (t["unassessed"], len(s.unassessed)))
        L.append("")
        L.append("| ID | Contrôle | Poids |")
        L.append("|---|---|---|")
        for u in s.unassessed:
            L.append("| **%s** | %s | %.1f |" % (u["id"], u["title"], u["weight"]))
        L.append("")

    L.append("---")
    L.append("")
    L.append("## %s" % t["method"])
    L.append("")
    L.append("- %s" % t["scope_note"])
    L.append("- %s" % t["disclaimer"])
    if fw.source_url:
        L.append("- Source du référentiel : %s" % fw.source_url)
    L.append("")

    path = os.path.join(ws.reports_dir(client.slug),
                        "gap-%s-%s.md" % (fw.id, _dt.date.today().isoformat()))
    with open(path, "w", encoding="utf-8") as f:
        f.write(chr(10).join(L))
    return path


def write_evidence_register(ws, client: Client, fw: Framework, a: Assessment, lang: str = "fr") -> str:
    t = TXT.get(lang, TXT["fr"])
    s = scoring.score(fw, client, a)
    L: List[str] = []
    L.append("# %s" % t["evidence_title"])
    L.append("")
    L.append("**%s :** %s  " % (t["client"], client.legal_name))
    L.append("**%s :** %s  " % (t["framework"], fw.name))
    L.append("**%s :** %s" % (t["generated"], _stamp()))
    L.append("")
    L.append("---")
    L.append("")
    L.append("| Contrôle | État | Élément | Type | Collecté | Source | Empreinte |")
    L.append("|---|---|---|---|---|---|---|")
    rows = 0
    for c in fw.controls:
        row = a.rows.get(c.id)
        if not row or not row.evidence:
            continue
        for e in row.evidence:
            rows += 1
            L.append("| **%s** | %s | %s | %s | %s | %s | %s |" % (
                c.id,
                STATE_LABEL.get(row.state, row.state),
                (e.summary or "-")[:60],
                e.kind,
                e.collected_at,
                (e.source or "-")[:28],
                (e.sha256[:12] + "...") if e.sha256 else "-",
            ))
    if rows == 0:
        L.append("| *%s* | | | | | | |" % t["none"])
    L.append("")
    L.append("**%d %s**" % (rows, t["evidence_items"].lower()))
    L.append("")
    L.append("> %s" % t["disclaimer"])
    L.append("")
    path = os.path.join(ws.reports_dir(client.slug),
                        "evidence-register-%s-%s.md" % (fw.id, _dt.date.today().isoformat()))
    with open(path, "w", encoding="utf-8") as f:
        f.write(chr(10).join(L))
    return path


def write_client_summary(ws, client: Client, lang: str = "fr") -> str:
    t = TXT.get(lang, TXT["fr"])
    L: List[str] = []
    L.append("# %s" % t["summary_title"])
    L.append("")
    L.append("**%s :** %s  " % (t["client"], client.legal_name))
    L.append("**%s :** %s" % (t["generated"], _stamp()))
    L.append("")
    L.append("| %s | Score | Écarts | Partiels | Non évalués |" % t["framework"])
    L.append("|---|---|---|---|---|")
    for fid in ws.list_assessments(client.slug):
        fw = __import__("compliance_os.registry", fromlist=["load_framework"]).load_framework(fid)
        a = ws.load_assessment(client.slug, fid)
        s = scoring.score(fw, client, a)
        L.append("| %s | **%.1f%%** | %d | %d | %d |" % (fid, s.pct, len(s.gaps), len(s.partials), len(s.unassessed)))
    L.append("")
    L.append("**%s**" % t["scope_note"])
    L.append("")
    path = os.path.join(ws.reports_dir(client.slug),
                        "summary-%s.md" % _dt.date.today().isoformat())
    with open(path, "w", encoding="utf-8") as f:
        f.write(chr(10).join(L))
    return path
