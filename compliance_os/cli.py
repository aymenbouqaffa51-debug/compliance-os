"""Command line interface.

Design goal: a non-developer can run this. Every command prints a clear next
step. Nothing requires a flag to do the obvious thing.
"""

from __future__ import annotations

import argparse
import os
import sys

from compliance_os import __version__
from compliance_os import cndp
from compliance_os import registry, scoring
from compliance_os.models import (
    STATE_GAP,
    STATE_IMPLEMENTED,
    STATE_NOT_APPLICABLE,
    STATE_NOT_ASSESSED,
    STATE_PARTIAL,
    STATES,
    STATE_LABEL,
    EvidenceItem,
)
from compliance_os.report import write_gap_report, write_evidence_register, write_client_summary

DEFAULT_WORKSPACE = os.environ.get(
    "COMPLIANCE_WORKSPACE", os.path.join(os.path.expanduser("~"), "compliance-workspace")
)

C = {
    "g": "\033[32m", "y": "\033[33m", "r": "\033[31m",
    "b": "\033[1m", "d": "\033[2m", "x": "\033[0m",
}


_NL = chr(10)

def _c(key, text):
    if not sys.stdout.isatty() or os.environ.get("NO_COLOR"):
        return text
    return C.get(key, "") + text + C["x"]


def _ws(args) -> registry.Workspace:
    return registry.Workspace(getattr(args, "workspace", None) or DEFAULT_WORKSPACE)


def _bar(pct, width=34):
    filled = int(round(width * pct / 100.0))
    return "[" + "#" * filled + "." * (width - filled) + "]"


def _state_colour(state):
    return {
        STATE_IMPLEMENTED: "g",
        STATE_PARTIAL: "y",
        STATE_GAP: "r",
        STATE_NOT_ASSESSED: "d",
        STATE_NOT_APPLICABLE: "d",
    }.get(state, "d")


# ===================================================================== init
def cmd_init(args):
    ws = _ws(args)
    ws.init()
    print(_c("g", "Workspace ready: ") + ws.root)
    print()
    print("Frameworks available:")
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        print("  %-18s %-52s %3d controls" % (fid, fw.name[:52], len(fw.controls)))
    print()
    print(_c("b", "Next:") + " compliance client-new \"Acme SARL\" --sector SaaS --headcount 40")
    return 0


# =============================================================== frameworks
def cmd_frameworks(args):
    print(_c("b", "%-18s %-56s %s" % ("ID", "NAME", "CONTROLS")))
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        print("%-18s %-56s %3d" % (fid, fw.name[:56], len(fw.controls)))
    return 0


def cmd_show(args):
    fw = registry.load_framework(args.framework)
    print(_c("b", fw.name))
    print("Version %s - locale %s" % (fw.version, fw.locale))
    print("Authority: %s" % fw.authority)
    if fw.source_url:
        print("Source: %s" % fw.source_url)
    print()
    if fw.disclaimer:
        for line in fw.disclaimer.strip().splitlines():
            print(_c("y", "! ") + line.strip())
        print()
    theme = None
    for c in fw.controls:
        if c.theme != theme:
            theme = c.theme
            print(_c("b", "\n== %s ==" % theme))
        print("  %-12s %-58s w=%.1f" % (c.id, c.title[:58], c.weight))
        if c.applicability == "conditional":
            print("               " + _c("d", "conditional: " + c.condition))
    return 0


# ================================================================== clients
def cmd_client_new(args):
    ws = _ws(args)
    ws.init()
    markets = [m.strip() for m in (args.export_markets or "").split(",") if m.strip()]
    try:
        client = ws.create_client(
            legal_name=args.name,
            slug=args.slug,
            sector=args.sector or "",
            headcount=args.headcount or "",
            contact_name=args.contact or "",
            contact_email=args.email or "",
            export_markets=markets,
            handles_sensitive_data=bool(args.sensitive),
            handles_cin=bool(args.cin),
            is_public_entity=bool(args.public_entity),
            engagement=args.engagement or "readiness_check",
            rc=getattr(args, "rc", "") or "",
            ice=getattr(args, "ice", "") or "",
            if_number=getattr(args, "if_number", "") or "",
            address=getattr(args, "address", "") or "",
            signatory_title=getattr(args, "signatory_title", "") or "",
            hosting_region=getattr(args, "hosting_region", "") or "eu-west-3",
            hosting_country=getattr(args, "hosting_country", "") or "France",
            is_iiv=bool(getattr(args, "iiv", False)),
        )
    except registry.ComplianceError as exc:
        print(_c("r", "error: ") + str(exc))
        return 2
    print(_c("g", "Created client ") + client.slug)
    print("  %s" % ws.client_file(client.slug))
    print()
    print(_c("b", "Next:") + " compliance assess %s iso-27001-2022" % client.slug)
    return 0


def cmd_clients(args):
    ws = _ws(args)
    slugs = ws.list_clients()
    if not slugs:
        print("No clients yet. Create one: compliance client-new \"Name\"")
        return 0
    print(_c("b", "%-24s %-34s %-8s %s" % ("SLUG", "LEGAL NAME", "HC", "ASSESSMENTS")))
    for s in slugs:
        try:
            c = ws.load_client(s)
        except registry.ComplianceError:
            continue
        print("%-24s %-34s %-8s %s" % (
            s, c.legal_name[:34], c.headcount or "-",
            ", ".join(ws.list_assessments(s)) or "-"))
    return 0


# ================================================================== assess
def cmd_assess(args):
    ws = _ws(args)
    client = ws.load_client(args.client)
    fw = registry.load_framework(args.framework)
    a = ws.load_assessment(client.slug, fw.id)
    if args.assessor:
        a.assessor = args.assessor
    ws.save_assessment(a)
    ws.reports_dir(client.slug) and os.makedirs(ws.reports_dir(client.slug), exist_ok=True)

    resolved = scoring.resolve(fw, client)
    applicable = [r for r in resolved if r["applies"]]
    excluded = [r for r in resolved if not r["applies"]]

    print(_c("b", "%s  vs  %s" % (client.legal_name, fw.name)))
    print("%d controls, %d applicable to this client, %d excluded by condition" % (
        len(fw.controls), len(applicable), len(excluded)))
    print()

    if excluded:
        print(_c("d", "Excluded (not applicable to this client):"))
        for r in excluded:
            print(_c("d", "  - %-12s %-50s %s" % (r["control"].id, r["control"].title[:50], r["reason"])))
        print()

    theme = None
    for r in applicable:
        c = r["control"]
        row = a.rows.get(c.id)
        state = row.state if row else STATE_NOT_ASSESSED
        if c.theme != theme:
            theme = c.theme
            print(_c("b", "\n== %s ==" % theme))
        print("  %-12s [%s] %s" % (
            c.id, _c(_state_colour(state), STATE_LABEL.get(state, state)[:12].ljust(12)),
            c.title[:64]))

    s = scoring.score(fw, client, a)
    print()
    print(_c("b", "Readiness: ") + _bar(s.pct) + " %5.1f%%  (%s)" % (
        s.pct, scoring.readiness_verdict(s.pct)))
    print("  %d assessed, %d gaps, %d partial, %d not assessed" % (
        s.applicable - len(s.unassessed), len(s.gaps), len(s.partials), len(s.unassessed)))
    print()
    print(_c("b", "Next:") + " compliance set %s %s <CONTROL_ID> implemented" % (client.slug, fw.id))
    return 0


def cmd_set(args):
    ws = _ws(args)
    client = ws.load_client(args.client)
    fw = registry.load_framework(args.framework)
    state = args.state
    if state not in STATES:
        print(_c("r", "error: ") + "state must be one of: " + ", ".join(STATES))
        return 2
    c = fw.by_id(args.control)
    if c is None:
        print(_c("r", "error: ") + "no control %r in %s" % (args.control, fw.id))
        close = [x.id for x in fw.controls if args.control.lower() in x.id.lower() or args.control.lower() in x.title.lower()]
        if close:
            print("Did you mean: " + ", ".join(close[:6]))
        return 2
    a = ws.load_assessment(client.slug, fw.id)
    row = a.row(c.id)
    row.state = state
    if args.notes is not None:
        row.notes = args.notes
    if args.owner is not None:
        row.owner = args.owner
    if args.due is not None:
        row.due = args.due
    import datetime as _dt
    row.assessed_at = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ws.save_assessment(a)
    s = scoring.score(fw, client, a)
    print("%s -> %s   %s %5.1f%%" % (
        c.id, _c(_state_colour(state), STATE_LABEL[state]), _bar(s.pct, 20), s.pct))
    return 0


def cmd_evidence(args):
    ws = _ws(args)
    client = ws.load_client(args.client)
    fw = registry.load_framework(args.framework)
    c = fw.by_id(args.control)
    if c is None:
        print(_c("r", "error: ") + "no control %r in %s" % (args.control, fw.id))
        return 2
    a = ws.load_assessment(client.slug, fw.id)
    row = a.row(c.id)
    item = EvidenceItem(
        kind=args.kind or "manual",
        source=args.source or "",
        summary=args.summary or "",
        sha256=args.sha256 or "",
        path=args.path or "",
        command=args.command or "",
        collector="cli",
        status="ok",
    )
    row.evidence.append(item)
    if args.also_state:
        row.state = args.also_state
    ws.save_assessment(a)
    print(_c("g", "Evidence recorded") + " on %s (%d item%s now)" % (
        c.id, len(row.evidence), "" if len(row.evidence) == 1 else "s"))
    print("  kind=%s collected_at=%s" % (item.kind, item.collected_at))
    return 0


# ================================================================== report
def cmd_report(args):
    ws = _ws(args)
    client = ws.load_client(args.client)
    fw = registry.load_framework(args.framework)
    a = ws.load_assessment(client.slug, fw.id)
    os.makedirs(ws.reports_dir(client.slug), exist_ok=True)
    if args.kind == "gap":
        path = write_gap_report(ws, client, fw, a, lang=args.lang)
    elif args.kind == "register":
        path = write_evidence_register(ws, client, fw, a, lang=args.lang)
    else:
        path = write_client_summary(ws, client, lang=args.lang)
    print(_c("g", "Report written: ") + path)
    return 0


# ==================================================================== score
def cmd_score(args):
    ws = _ws(args)
    client = ws.load_client(args.client)
    if args.framework:
        fids = [args.framework]
    else:
        fids = ws.list_assessments(client.slug) or ["iso-27001-2022"]
    print(_c("b", client.legal_name))
    for fid in fids:
        fw = registry.load_framework(fid)
        a = ws.load_assessment(client.slug, fid)
        s = scoring.score(fw, client, a)
        print("  %-18s %s %5.1f%%  %s" % (
            fid, _bar(s.pct, 20), s.pct, scoring.readiness_verdict(s.pct)))
        print("      gaps=%d partial=%d unassessed=%d excluded=%d" % (
            len(s.gaps), len(s.partials), len(s.unassessed),
            s.by_state.get(STATE_NOT_APPLICABLE, 0)))
    return 0


# ==================================================================== search
def cmd_search(args):
    needle = args.term.lower()
    for fid in registry.framework_ids():
        fw = registry.load_framework(fid)
        hits = [c for c in fw.controls
                if needle in c.id.lower() or needle in c.title.lower()
                or needle in c.objective.lower()
                or any(needle in m.lower() for m in c.maps_to)]
        if hits:
            print(_c("b", "SEP%s (%s)" % (fw.name, fid)).replace("SEP", chr(10) + "") if False else _c("b", _NL + fw.name + " (" + fid + ")"))
            for c in hits:
                print("  %-12s %s" % (c.id, c.title[:70]))
                if c.maps_to:
                    print(_c("d", "               maps_to: " + ", ".join(c.maps_to)))
    return 0



def cmd_collect(args):
    """Run a read-only collector and attach the result as evidence."""
    from compliance_os import collector
    ws = _ws(args)
    client = ws.load_client(args.client)
    fw = registry.load_framework(args.framework)
    c = fw.by_id(args.control)
    if c is None:
        print(_c("r", "error: ") + "no control %r in %s" % (args.control, fw.id))
        return 2

    kind = args.collector
    if kind == "secrets":
        item = collector.collect_secrets(args.target)
    elif kind == "deps":
        item = collector.collect_deps(args.target)
    elif kind == "code":
        item = collector.collect_code(args.target)
    elif kind == "file":
        item = collector.collect_file(args.target, args.summary or "")
    else:
        item = collector.attestation(args.summary or "attestation", source=args.target or "")

    a = ws.load_assessment(client.slug, fw.id)
    row = a.row(c.id)
    row.evidence.append(item)
    ws.save_assessment(a)

    status_colour = "g" if item.status == "ok" else ("y" if item.status == "skipped" else "r")
    print(_c(status_colour, "[%s]" % item.status) + " " + item.summary)
    if item.stderr_hint if hasattr(item, "stderr_hint") else False:
        pass
    print("  attached to %s (%d item%s now)" % (
        c.id, len(row.evidence), "" if len(row.evidence) == 1 else "s"))
    print()
    print(_c("b", "Remember:") + " a collector records an observation. A human sets the control state.")
    print("  compliance set %s %s %s <implemented|partial|gap>" % (client.slug, fw.id, c.id))
    return 0


def cmd_template(args):
    """Render a legal template with this client's facts prefilled."""
    import re as _re
    tpl_dir = os.path.join(os.path.dirname(__file__), "data", "templates")
    name = args.template
    if not name.endswith(".md"):
        name = name + "-fr.md"
    src = os.path.join(tpl_dir, name)
    if not os.path.isfile(src):
        avail = sorted(f for f in os.listdir(tpl_dir) if f.endswith(".md")) if os.path.isdir(tpl_dir) else []
        print(_c("r", "error: ") + "no template %r. Available: %s" % (name, ", ".join(avail)))
        return 2
    body = open(src, encoding="utf-8").read()

    ws = _ws(args)
    values = dict(PROVIDER_LEGAL_NAME=args.provider or "[VOTRE SOCIETE]",
                  PROVIDER_RC=args.rc or "[RC]",
                  PROVIDER_ICE=args.ice or "[ICE]",
                  PROVIDER_IF=args.if_number or "[IF]",
                  PROVIDER_ADDRESS=args.address or "[ADRESSE]",
                  PROVIDER_SIGNATORY=args.signatory or "[REPRESENTANT]",
                  PROVIDER_CONTACT=args.email or "[EMAIL]",
                  HOSTING_REGION=args.region or "eu-west-3 (France)",
                  HOSTING_COUNTRY=args.country or "France",
                  ON_CNDP_LIST=args.country_on_cndp_list if hasattr(args, "country_on_cndp_list") else cndp.transfer_position(args.country or "France")["on_list_text"],
                  SIGNATURE_DATE=__import__("datetime").date.today().isoformat())

    if args.client:
        try:
            client = ws.load_client(args.client)
        except registry.ComplianceError as exc:
            print(_c("y", "warning: ") + str(exc) + " -- rendering with blanks")
            client = None
        if client is not None:
            values.update(
                CLIENT_LEGAL_NAME=client.legal_name,
                # Pull real identity from the client record. Falling back to a
                # placeholder is correct only when the field genuinely is empty;
                # hardcoding the placeholder made --final fail on every
                # client that HAD provided the value.
                CLIENT_RC=client.rc or "[RC]",
                CLIENT_ADDRESS=client.address or "[ADRESSE]",
                CLIENT_SIGNATORY=(client.contact_name or "[REPRESENTANT]"),
                CLIENT_SIGNATORY_TITLE=(client.signatory_title or "[QUALITE]"),
                CLIENT_LEGAL_NAME_FULL=client.legal_name,
                CLIENT_IF=(client.if_number or "[IF]"),
                CLIENT_ICE=(client.ice or "[ICE]"),
                DATA_SUBJECTS=args.data_subjects or "Salaries et candidats",
                DATA_CATEGORIES=args.data_categories or "Donnees d'identification, donnees de contact professionnelles",
                SENSITIVE_DATA="Oui" if client.handles_sensitive_data else "Non",
                PROCESSES_CIN="Oui" if client.handles_cin else "Non",
                CNDP_AUTHORISATION="Requise (art. 12)" if (client.handles_sensitive_data or client.handles_cin) else "Non requise",
                PURPOSE=args.purpose or "Collecte et conservation de preuves de conformite",
                RETENTION=args.retention or "36 mois",
                LIABILITY_CAP=args.liability_cap or "[MONTANT]",
                JURISDICTION=args.jurisdiction or "Casablanca",
                HOSTING_REGION=args.region or (client.hosting_region or "eu-west-3"),
                HOSTING_COUNTRY=args.country or (client.hosting_country or "France"),
                SERVICE_DESCRIPTION=getattr(args, "service", None) or "Prestation de preparation a la certification et de collecte de preuves de conformite",
                SUBPROCESSORS=getattr(args, "subprocessors", None) or "| [A completer] | [Service] | [Pays] | [Base] |",
                SUBPROCESSORS_TABLE=getattr(args, "subprocessors", None) or "| [A completer] | [Service] | [Pays] | [Base de transfert] |",
                SUBPROCESSORS_LIST=getattr(args, "subprocessors", None) or "[A completer]",
                EXPORTER_NAME=getattr(args, "exporter", None) or "[CLIENT EUROPEEN]",
                EXPORTER_ADDRESS="[ADRESSE]", EXPORTER_CONTACT="[CONTACT]",
                TRANSFER_FREQUENCY=getattr(args, "frequency", None) or "Continue",
                TIA_DATA_NATURE=getattr(args, "tia_nature", None) or "Donnees d'identification et de contact professionnelles, necessaires a la fourniture du service.",
                TIA_CONCLUSION=getattr(args, "tia_conclusion", None) or "Les mesures de l'annexe II, combinees aux garanties contractuelles, assurent un niveau de protection substantiellement equivalent. A valider par l'exportateur.",
            )

    # Cross-border transfer position, computed from ONE canonical source.
    #
    # This used to be duplicated: an inline tuple above that included Croatia,
    # and a _CNDP_STATES set here that omitted it. For a Croatian hosting
    # country the rendered pack said ON_CNDP_LIST=Oui and F118_REQUIRED=Oui in
    # the same document. compliance_os.cndp is now the only definition.
    _country = (values.get("HOSTING_COUNTRY") or "France").strip()
    _position = cndp.transfer_position(_country)

    # The explicit flags win if the operator supplied them; otherwise the
    # canonical computation fills them. Never leave a contradictory pair.
    if not (hasattr(args, "country_on_cndp_list") and args.country_on_cndp_list):
        values["ON_CNDP_LIST"] = _position["on_list_text"]
    values.setdefault("TRANSFER_BASIS", _position["transfer_basis"])
    values.setdefault("F118_REQUIRED", _position["f118_required"])

    if not _position["known"] and not args.final:
        print(_c("y", "warning: ") + "%r is not a recognised country; the transfer" % _country)
        print("  basis is marked A VERIFIER in the output. Confirm its CNDP status")
        print("  before issuing the document, or pass --transfer-basis explicitly.")

    out = body
    for k, v in values.items():
        out = out.replace("{{%s}}" % k, str(v))
    leftovers = sorted(set(_re.findall(r"\{\{([A-Z0-9_]+)\}\}", out)))

    if getattr(args, "final", False):
        from compliance_os import ops as _ops
        try:
            out = _ops.finalise_template(out, strict=True)
        except ValueError as exc:
            print(_c("r", "error: ") + str(exc))
            print()
            print("Fill the missing fields with the matching --flag, or drop --final to")
            print("write a draft with placeholders intact.")
            return 2

    dest = args.output or os.path.join(os.getcwd(), name.replace("-fr.md", "-%s.md" % (args.client or "draft")))
    from compliance_os import registry as _reg
    _reg.atomic_write_text(dest, out)
    print(_c("g", "Template rendered: ") + dest)
    if leftovers:
        print(_c("y", "Still to fill in: ") + ", ".join(leftovers))
    return 0



def cmd_doctor(args):
    from compliance_os import ops
    ws = _ws(args)
    ok, lines = ops.doctor(ws.root)
    print(_c("b", "compliance doctor"))
    print()
    for line in lines:
        print("  " + line)
    print()
    if ok:
        print(_c("g", "Environment is ready."))
    else:
        print(_c("r", "Environment is NOT ready. Fix the [FAIL] lines above."))
    return 0 if ok else 1


def cmd_offboard(args):
    from compliance_os import ops
    ws = _ws(args)
    try:
        res = ops.offboard(
            ws.root, args.client,
            output_dir=args.output or "",
            keep_local=bool(args.keep_local),
        )
    except ops.OffboardError as exc:
        print(_c("r", "error: ") + str(exc))
        return 2
    print(_c("g", "Offboarded ") + args.client)
    print("  archive     " + res["zip"])
    print("  manifest    " + res["manifest"])
    print("  certificate " + res["certificate"])
    print("  files       " + res["files"])
    print("  sha256      " + res["zip_sha256"])
    print("  deleted     " + res["deleted"])
    if res["deleted"] != "True":
        print(_c("y", "  local workspace kept (--keep-local); delete it once the client confirms receipt"))
    return 0



def cmd_monitor(args):
    """Run read-only collectors, evaluate checks, persist the run."""
    from compliance_os import monitor as mon
    ws = _ws(args)
    client = ws.load_client(args.client)

    domain = args.domain or ""
    org = args.org or ""
    collectors = mon.build_collectors_from_env(domain=domain, org=org)

    if not collectors:
        print(_c("y", "No collector is configured.") + " Set at least one of:")
        print("  PERIMETER_DOMAIN=example.com     (no credentials needed)")
        print("  GITHUB_ORG=my-org  GITHUB_TOKEN=...")
        print("  AWS_PROFILE=...  or AWS_ACCESS_KEY_ID=...")
        print("  WORKSPACE_DOMAIN=example.com")
        print()
        print("Running anyway records every check as NOT_APPLICABLE, which is")
        print("honest but not useful. Nothing was written.")
        return 2

    print(_c("b", client.legal_name) + " -- running %d collector(s): %s" % (
        len(collectors), ", ".join(sorted(collectors))))
    print()

    run = mon.run_monitors(ws, client.slug, collectors=collectors)

    for source in sorted(set(r.source for r in run.results)):
        rows = [r for r in run.results if r.source == source]
        passed = sum(1 for r in rows if r.outcome == "PASS")
        failed = [r for r in rows if r.outcome == "FAIL"]
        na = sum(1 for r in rows if r.outcome == "NOT_APPLICABLE")
        print("  %-10s %d checks  %s%d passed%s  %s%d failed%s  %d n/a" % (
            source, len(rows),
            _c("g", ""), passed, _c("x", ""),
            _c("r" if failed else "d", ""), len(failed), _c("x", ""), na))
        for r in failed:
            print("      " + _c("r", "FAIL") + " %-8s %s" % (r.check_id, r.title[:56]))
            if r.observed is not None:
                print("             observed: %r" % (r.observed,))

    print()
    counts = run.counts()
    print(_c("b", "Score: ") + "%.1f%% across %d decisive checks" % (
        run.score(), counts.get("PASS", 0) + counts.get("FAIL", 0)))

    drift = [r for r in run.results if r.drift]
    if drift:
        print()
        print(_c("r", "DRIFT since the previous run:"))
        for r in drift:
            print("  [%s] %s %s (was %s)" % (r.drift, r.check_id, r.title[:50], r.previous_outcome))

    print()
    print("  fingerprint  " + run.fingerprint[:16] + "...")
    print("  stored       " + mon.runs_path(ws, client.slug))
    print()
    print(_c("b", "Next:") + " compliance set %s <framework> <CONTROL> implemented" % client.slug)
    print("      A check result is an observation. The control state is your call.")
    return 0


def cmd_monitor_status(args):
    """Show the latest run and verify the ledger chain."""
    from compliance_os import monitor as mon
    ws = _ws(args)
    client = ws.load_client(args.client)

    runs = mon.load_runs(ws, client.slug)
    if not runs:
        print("No monitoring runs yet. Run: compliance monitor %s --domain example.com" % client.slug)
        return 0

    last = runs[-1]
    print(_c("b", client.legal_name))
    print("  runs recorded   %d" % len(runs))
    print("  last run        %s" % last.get("finished_at", ""))
    print("  score           %.1f%%" % last.get("score", 0.0))
    counts = last.get("counts", {})
    print("  pass/fail/n-a   %d / %d / %d" % (
        counts.get("PASS", 0), counts.get("FAIL", 0), counts.get("NOT_APPLICABLE", 0)))
    print("  fingerprint     " + (last.get("fingerprint", "")[:32] or "-"))

    drift = [r for r in last.get("results", []) if r.get("drift")]
    if drift:
        print()
        print(_c("r", "  open drift (%d):" % len(drift)))
        for r in drift:
            print("    [%s] %s %s" % (r.get("drift"), r.get("check_id"), r.get("title", "")[:48]))

    v = mon.verify_ledger(ws, client.slug)
    print()
    if v["ok"]:
        print(_c("g", "  ledger intact") + " (%d records, hash chain verified)" % v["records"])
    else:
        print(_c("r", "  LEDGER BROKEN") + " at record %s: %s" % (v["broken_at"], v["reason"]))
    return 0 if v["ok"] else 1


def cmd_checks(args):
    """List the automated checks and their control mappings."""
    from compliance_os import checks as check_engine
    pool = check_engine.load_checks()
    if args.source:
        pool = [c for c in pool if c.source == args.source]
    print(_c("b", "%-9s %-9s %-9s %-58s %s" % ("SOURCE", "ID", "SEVERITY", "TITLE", "CONTROLS")))
    for c in pool:
        print("%-9s %-9s %-9s %-58s %s" % (
            c.source, c.id, c.severity, c.title[:58], ",".join(c.controls[:3])))
    print()
    print("%d checks" % len(pool))
    return 0



def cmd_questionnaire(args):
    """Parse a buyer questionnaire and draft grounded answers."""
    from compliance_os import questionnaire as Q
    ws = _ws(args)
    client = ws.load_client(args.client)

    if not os.path.isfile(args.file):
        print(_c("r", "error: ") + "file not found: %s" % args.file)
        return 2

    try:
        questions = Q.parse_questionnaire(args.file, sheet=args.sheet)
    except RuntimeError as exc:
        print(_c("r", "error: ") + str(exc))
        return 2

    if not questions:
        print(_c("y", "No questions found.") + " The parser looks for a column named")
        print("question / requirement / control / description. Open the file and check.")
        return 2

    print(_c("b", client.legal_name) + " -- %d questions parsed" % len(questions))
    result = Q.answer_questionnaire(
        ws, client.slug, questions, source_file=os.path.basename(args.file)
    )

    counts = result.counts()
    print()
    print("  high confidence   %d" % counts["high"])
    print("  verify first      %d" % counts["medium"])
    print("  low confidence    %d" % counts["low"])
    print(_c("y" if counts["needs_review"] else "g",
             "  needs review      %d" % counts["needs_review"]))
    print("  unmatched         %d" % counts["unmatched"])

    outdir = args.output or os.path.join(ws.reports_dir(client.slug))
    os.makedirs(outdir, exist_ok=True)
    base = os.path.splitext(os.path.basename(args.file))[0]
    md = Q.write_markdown(result, os.path.join(outdir, "questionnaire-%s.md" % base), client.legal_name)
    csvp = Q.write_csv(result, os.path.join(outdir, "questionnaire-%s.csv" % base))

    print()
    print(_c("g", "Pack written:"))
    print("  " + md)
    print("  " + csvp)
    print()
    if counts["needs_review"]:
        print(_c("y", "%d row(s) need a human decision before sending.") % counts["needs_review"])
        print("  A gap or unassessed control is never drafted as a yes. That is deliberate.")
    return 0


def cmd_policies(args):
    """Generate the ISMS policy suite for a client."""
    from compliance_os import policies as P
    ws = _ws(args)
    client = ws.load_client(args.client)

    if args.list:
        print(_c("b", "%-24s %-54s %s" % ("ID", "TITLE", "CONTROLS")))
        for pol in P.list_policies():
            print("%-24s %-54s %s" % (pol["id"], pol["title_en"][:54], ",".join(pol["controls"][:2])))
        print()
        print("%d policies. Generate all with: compliance policies %s" % (
            len(P.list_policies()), args.client))
        return 0

    ids = [args.only] if args.only else None
    if ids and ids[0] not in [p["id"] for p in P.list_policies()]:
        print(_c("r", "error: ") + "unknown policy %r. Run: compliance policies %s --list" % (
            ids[0], args.client))
        return 2

    try:
        paths = P.write_policies(ws, client.slug, policy_ids=ids, lang=args.lang,
                                 domain=args.domain or "")
    except KeyError as exc:
        print(_c("r", "error: ") + str(exc))
        return 2

    print(_c("g", "%d polic%s generated") % (len(paths), "y" if len(paths) == 1 else "ies"))
    for path in paths:
        print("  " + path)
    print()
    print(_c("y", "Every policy needs review, adaptation and signature.") + " A generated")
    print("policy nobody has read is not evidence.")
    return 0


# ===================================================================== main
def build_parser():
    p = argparse.ArgumentParser(
        prog="compliance",
        description="Compliance OS - evidence automation with a Moroccan regulatory layer.",
        epilog="Start here: compliance init",
    )
    p.add_argument("--version", action="version", version="compliance-os %s" % __version__)
    p.add_argument("--workspace", help="Workspace directory (default: ~/compliance-workspace)")
    sub = p.add_subparsers(dest="command")

    sub.add_parser("init", help="Create the workspace and list frameworks").set_defaults(func=cmd_init)
    sub.add_parser("frameworks", help="List frameworks").set_defaults(func=cmd_frameworks)

    sp = sub.add_parser("show", help="Show the controls in a framework")
    sp.add_argument("framework")
    sp.set_defaults(func=cmd_show)

    sp = sub.add_parser("client-new", help="Create a client workspace")
    sp.add_argument("name")
    sp.add_argument("--slug")
    sp.add_argument("--sector")
    sp.add_argument("--headcount")
    sp.add_argument("--contact")
    sp.add_argument("--email")
    sp.add_argument("--export-markets", help="Comma-separated, e.g. France,Germany")
    sp.add_argument("--sensitive", action="store_true", help="Processes sensitive data (CNDP art.1)")
    sp.add_argument("--cin", action="store_true", help="Processes ID-card numbers (triggers CNDP art.12)")
    sp.add_argument("--public-entity", action="store_true", help="Is a Law 05-20 'entite'")
    sp.add_argument("--engagement", choices=["readiness_check", "readiness_program", "retainer"])
    sp.add_argument("--rc", help="Registre de commerce number")
    sp.add_argument("--ice", help="Identifiant commun de l'entreprise")
    sp.add_argument("--if-number", dest="if_number", help="Identifiant fiscal")
    sp.add_argument("--address")
    sp.add_argument("--signatory-title", dest="signatory_title")
    sp.add_argument("--hosting-region", dest="hosting_region", help="e.g. eu-west-3")
    sp.add_argument("--hosting-country", dest="hosting_country")
    sp.add_argument("--iiv", action="store_true", help="Is a vital infrastructure (out of scope for us)")
    sp.set_defaults(func=cmd_client_new)

    sub.add_parser("clients", help="List clients").set_defaults(func=cmd_clients)

    sp = sub.add_parser("assess", help="Show the working checklist for a client")
    sp.add_argument("client")
    sp.add_argument("framework")
    sp.add_argument("--assessor")
    sp.set_defaults(func=cmd_assess)

    sp = sub.add_parser("set", help="Set a control's state")
    sp.add_argument("client")
    sp.add_argument("framework")
    sp.add_argument("control")
    sp.add_argument("state", choices=STATES)
    sp.add_argument("--notes")
    sp.add_argument("--owner")
    sp.add_argument("--due")
    sp.set_defaults(func=cmd_set)

    sp = sub.add_parser("evidence", help="Attach an evidence record to a control")
    sp.add_argument("client")
    sp.add_argument("framework")
    sp.add_argument("control")
    sp.add_argument("--kind", default="manual", choices=["manual", "command", "file", "url", "attestation"])
    sp.add_argument("--summary")
    sp.add_argument("--source")
    sp.add_argument("--sha256")
    sp.add_argument("--path")
    sp.add_argument("--command")
    sp.add_argument("--also-state", choices=STATES)
    sp.set_defaults(func=cmd_evidence)

    sp = sub.add_parser("report", help="Generate a deliverable")
    sp.add_argument("client")
    sp.add_argument("--framework")
    sp.add_argument("--kind", choices=["gap", "register", "summary"], default="gap")
    sp.add_argument("--lang", choices=["en", "fr"], default="fr")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("score", help="Readiness score for a client")
    sp.add_argument("client")
    sp.add_argument("--framework")
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("search", help="Search controls across frameworks")
    sp.add_argument("term")
    sp.set_defaults(func=cmd_search)

    sp = sub.add_parser("collect", help="Run a read-only collector and attach evidence")
    sp.add_argument("client")
    sp.add_argument("framework")
    sp.add_argument("control")
    sp.add_argument("collector", choices=["secrets", "deps", "code", "file", "attestation"])
    sp.add_argument("--target", default=".", help="Path, repo or value for the collector")
    sp.add_argument("--summary")
    sp.set_defaults(func=cmd_collect)

    sp = sub.add_parser("template", help="Render a legal template (DPA, pack, SCC/TIA)")
    sp.add_argument("template", help="dpa | pack-declarez-moi | scc-tia")
    sp.add_argument("--client")
    sp.add_argument("--provider")
    sp.add_argument("--rc")
    sp.add_argument("--ice")
    sp.add_argument("--if-number", dest="if_number")
    sp.add_argument("--address")
    sp.add_argument("--signatory")
    sp.add_argument("--email")
    sp.add_argument("--region")
    sp.add_argument("--country")
    sp.add_argument("--purpose")
    sp.add_argument("--retention")
    sp.add_argument("--data-subjects", dest="data_subjects")
    sp.add_argument("--data-categories", dest="data_categories")
    sp.add_argument("--liability-cap", dest="liability_cap")
    sp.add_argument("--jurisdiction")
    sp.add_argument("--output")
    sp.add_argument("--service")
    sp.add_argument("--subprocessors")
    sp.add_argument("--exporter")
    sp.add_argument("--frequency")
    sp.add_argument("--tia-nature", dest="tia_nature")
    sp.add_argument("--tia-conclusion", dest="tia_conclusion")
    sp.add_argument("--transfer-basis", dest="transfer_basis")
    sp.add_argument("--f118-required", dest="f118_required")
    sp.add_argument("--final", action="store_true",
                    help="Refuse to write if any placeholder or [A completer] remains")
    sp.set_defaults(func=cmd_template)

    sp = sub.add_parser("doctor", help="Check the environment is ready")
    sp.set_defaults(func=cmd_doctor)

    sp = sub.add_parser("offboard", help="Archive a client, hash it, and delete it")
    sp.add_argument("client")
    sp.add_argument("--output", help="Directory for the archive (default: cwd)")
    sp.add_argument("--keep-local", dest="keep_local", action="store_true",
                    help="Do not delete the local workspace after archiving")
    sp.set_defaults(func=cmd_offboard)

    sp = sub.add_parser("monitor", help="Run read-only collectors and evaluate checks")
    sp.add_argument("client")
    sp.add_argument("--domain", help="Perimeter domain (or set PERIMETER_DOMAIN)")
    sp.add_argument("--org", help="GitHub org (or set GITHUB_ORG)")
    sp.set_defaults(func=cmd_monitor)

    sp = sub.add_parser("monitor-status", help="Show the latest run and verify the ledger")
    sp.add_argument("client")
    sp.set_defaults(func=cmd_monitor_status)

    sp = sub.add_parser("checks", help="List the automated checks")
    sp.add_argument("--source", help="Filter by source: aws, github, perimeter")
    sp.set_defaults(func=cmd_checks)

    sp = sub.add_parser("questionnaire", help="Auto-draft answers to a buyer questionnaire (CSV/XLSX)")
    sp.add_argument("client")
    sp.add_argument("file", help="Path to the .csv or .xlsx questionnaire")
    sp.add_argument("--sheet", help="Worksheet name for .xlsx")
    sp.add_argument("--output", help="Output directory")
    sp.set_defaults(func=cmd_questionnaire)

    sp = sub.add_parser("policies", help="Generate the ISMS policy suite")
    sp.add_argument("client")
    sp.add_argument("--list", action="store_true", help="List available policies")
    sp.add_argument("--only", help="Generate a single policy by id")
    sp.add_argument("--lang", choices=["fr", "en"], default="fr")
    sp.add_argument("--domain")
    sp.set_defaults(func=cmd_policies)

    return p


def main(argv=None):
    p = build_parser()
    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    try:
        return args.func(args) or 0
    except registry.ComplianceError as exc:
        print(_c("r", "error: ") + str(exc))
        return 2
    except KeyboardInterrupt:
        print(_NL + "aborted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
