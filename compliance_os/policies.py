"""Bilingual ISMS policy generator.

Generates the 20 policies an ISO 27001 programme actually needs, pre-filled with
the client's real facts: company name, hosting region, tech stack, sub-processors.

Design rules:
  - Every policy names the control it satisfies, so the evidence register links
    back automatically.
  - Moroccan policies cite the article they operationalise (loi 09-08 art. 23,
    loi 05-20 art. 3-9, decret 2-21-406 art. 10-15) but never claim the law
    applies to a private company that it does not bind.
  - Every generated document carries a review banner and an owner/approver block.
    An unsigned policy is not evidence.
"""

from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Dict, List, Optional

from compliance_os import registry
from compliance_os.models import Client

POLICY_DIR = os.path.join(os.path.dirname(__file__), "data", "templates", "policies")


# Each policy: id, title_en, title_fr, controls it satisfies, and body sections.
# Bodies are written as ordinary prose with {{PLACEHOLDER}} substitution so the
# generator stays data-driven rather than 20 hardcoded functions.

POLICIES: List[Dict[str, Any]] = [
    {
        "id": "pssi",
        "title_en": "Information Security Policy (PSSI)",
        "title_fr": "Politique de Securite des Systemes d'Information (PSSI)",
        "controls": ["A.5.1", "MA05-20-01"],
        "sections": [
            ("Purpose", "This policy establishes {{COMPANY}}'s approach to protecting the confidentiality, integrity and availability of information entrusted to it by clients, employees and partners."),
            ("Scope", "It applies to all employees, contractors and third parties who access {{COMPANY}} information systems, regardless of location. It covers all information assets supporting the services described in the Statement of Applicability."),
            ("Policy statements", "1. Information is classified and handled according to its sensitivity.\n2. Access is granted on the principle of least privilege and reviewed at least quarterly.\n3. Security events are logged, monitored and reviewed.\n4. Security is considered at every stage of the change lifecycle.\n5. Incidents are reported, recorded and handled according to the Incident Management Policy."),
            ("Roles and responsibilities", "Top management approves this policy and provides resources. The security lead maintains it and reports on its effectiveness. Every employee is responsible for reporting suspected incidents without delay."),
            ("Review", "This policy is reviewed at least annually, and whenever a significant change occurs to the organisation, its services or the threat landscape."),
        ],
    },
    {
        "id": "access-control",
        "title_en": "Access Control Policy",
        "title_fr": "Politique de Controle d'Acces",
        "controls": ["A.5.15", "A.5.16", "A.5.17", "A.5.18", "A.8.2", "A.8.5", "MA05-20-11"],
        "sections": [
            ("Purpose", "To ensure that access to {{COMPANY}} systems and data is limited to authorised individuals, on a need-to-know basis, and is periodically reviewed."),
            ("Authentication", "Multi-factor authentication is mandatory for: administrative access to any production system; remote access; access to source code repositories; access to the cloud console. Passwords must be at least 12 characters and are never shared."),
            ("Authorisation", "Access requests are approved by the system owner and recorded. Roles are defined per system; direct per-user grants are exceptions and require a documented justification."),
            ("Review", "Access rights are reviewed at least quarterly. The review records the reviewer, the date, and any access removed."),
            ("Termination", "Access is revoked within one business day of an individual's departure or role change. A checklist evidences the revocation for every account type."),
        ],
    },
    {
        "id": "asset-classification",
        "title_en": "Asset and Data Classification Policy",
        "title_fr": "Politique de Classification des Actifs et des Donnees",
        "controls": ["A.5.9", "A.5.10", "A.5.12", "A.5.13", "MA05-20-03"],
        "sections": [
            ("Purpose", "To define how {{COMPANY}} inventories its information assets and classifies information by sensitivity."),
            ("Asset inventory", "An inventory is maintained listing every information asset with: owner, location, classification, and the systems that process it. The inventory is reviewed at least annually."),
            ("Classification scheme", "Information is classified as Public, Internal, Confidential, or Restricted. Restricted covers personal data, credentials, and client data under contract."),
            ("Handling rules", "Confidential and Restricted information is encrypted at rest and in transit, shared only through approved channels, and never placed in public repositories or unencrypted removable media."),
            ("Moroccan classification note", "Where {{COMPANY}} supplies a public entity or a vital infrastructure operator, the classification in Decree 2-21-406 art. 13 applies: TRES SECRET, SECRET, CONFIDENTIEL, DIFFUSION RESTREINTE. Only the first two are 'sensitive data' within the meaning of Law 05-20 art. 11."),
            ("Review", "The classification of an asset is reviewed whenever the asset's use changes, and at least every three years."),
        ],
    },
    {
        "id": "incident-management",
        "title_en": "Incident Management Policy",
        "title_fr": "Politique de Gestion des Incidents",
        "controls": ["A.5.24", "A.5.25", "A.5.26", "A.5.27", "A.5.28", "MA05-20-07"],
        "sections": [
            ("Purpose", "To ensure security incidents are detected, reported, contained, resolved and learned from in a consistent way."),
            ("Reporting", "Any employee who suspects a security incident reports it immediately to {{SECURITY_CONTACT}}. Reporting in good faith is never penalised."),
            ("Severity", "Incidents are classified Critical, High, Medium or Low according to business impact and data sensitivity. Critical incidents trigger immediate escalation to management."),
            ("Response", "Each incident is assigned an owner and tracked to closure. A post-incident review is held for every Critical and High incident within ten business days."),
            ("Notification to clients", "Where an incident affects client data, {{COMPANY}} notifies the affected client within 48 hours of confirming the incident, in accordance with contractual commitments. Note: Moroccan Law 09-08 contains no statutory breach-notification obligation; this is a contractual duty agreed with clients, and the equivalent European requirement for EU buyers."),
            ("Evidence", "Incident records, timelines and post-mortems are retained for at least three years."),
        ],
    },
    {
        "id": "bcp-drp",
        "title_en": "Business Continuity and Disaster Recovery Policy",
        "title_fr": "Politique de Continuite et de Reprise d'Activite",
        "controls": ["A.5.29", "A.5.30", "A.8.13", "A.8.14", "MA05-20-08"],
        "sections": [
            ("Purpose", "To ensure {{COMPANY}} can continue delivering its services through a disruption and restore normal operations within agreed timeframes."),
            ("Recovery objectives", "Recovery Time Objective (RTO): {{RTO}}. Recovery Point Objective (RPO): {{RPO}}. These objectives are agreed with clients where a contract requires it."),
            ("Backups", "Production data is backed up at least daily, encrypted, and stored in a separate region from the primary. Backup success is monitored and failures alert."),
            ("Restoration testing", "A restore is performed and documented at least quarterly. The test record states what was restored, how long it took, and whether the RTO was met."),
            ("Data residency", "Primary hosting region: {{HOSTING_REGION}} ({{HOSTING_COUNTRY}}). Backups remain within the same jurisdiction unless a client agrees otherwise in writing."),
        ],
    },
    {
        "id": "cryptography",
        "title_en": "Cryptography Policy",
        "title_fr": "Politique Cryptographique",
        "controls": ["A.8.24", "MA09-08-06"],
        "sections": [
            ("Purpose", "To define the cryptographic controls that protect {{COMPANY}} information and client data."),
            ("In transit", "TLS 1.2 is the minimum accepted; TLS 1.3 is preferred. Weak protocols and ciphers are disabled. Certificates are renewed automatically with an expiry alert at 30 days."),
            ("At rest", "All production storage holding Confidential or Restricted information is encrypted with AES-256 or equivalent, with keys managed by the cloud provider's key management service."),
            ("Key management", "Key material is never committed to source control, never stored in plaintext configuration, and is rotated on a documented schedule or upon suspicion of compromise."),
            ("Secrets", "Application secrets are stored in the platform secret manager and injected at runtime. Secret scanning is enabled on all repositories."),
        ],
    },
    {
        "id": "secure-sdlc",
        "title_en": "Secure Development Policy",
        "title_fr": "Politique de Developpement Securise",
        "controls": ["A.8.25", "A.8.26", "A.8.28", "A.8.29", "A.8.32", "MA05-20-05"],
        "sections": [
            ("Purpose", "To ensure security is built into {{COMPANY}} software from design through deployment."),
            ("Design", "Security requirements are identified for every new feature touching authentication, authorisation, personal data, or external integrations. A threat model is produced for significant changes."),
            ("Code review", "No change reaches the default branch without review by someone other than the author. The default branch is protected; force pushes are disabled."),
            ("Automated checks", "Every pull request runs dependency scanning, static analysis, and secret scanning. A failing critical finding blocks the merge."),
            ("Dependencies", "Third-party dependencies are pinned. Vulnerability alerts are enabled and Critical alerts are remediated within 30 days."),
            ("Change management", "Changes are described, reviewed, approved and traceable. Production deployment requires an approved change record."),
        ],
    },
    {
        "id": "vendor-risk",
        "title_en": "Supplier and Sub-processor Policy",
        "title_fr": "Politique Fournisseurs et Sous-traitants",
        "controls": ["A.5.19", "A.5.20", "A.5.21", "A.5.22", "A.5.23", "MA09-08-03", "MA09-08-04", "MA05-20-09"],
        "sections": [
            ("Purpose", "To ensure that suppliers and sub-processors who handle {{COMPANY}} or client information meet the same security and data-protection standards."),
            ("Selection", "A supplier handling Confidential or Restricted information is assessed before onboarding: security certifications, sub-processor list, data residency, breach history."),
            ("Contractual requirements", "Every processor is bound by a written agreement satisfying Law 09-08 art. 23: processing only on documented instruction, equivalent security obligations, confidentiality, sub-processor controls, audit rights, and return or deletion of data at the end of the engagement."),
            ("Sub-processor register", "A register lists every sub-processor with: service provided, country of processing, transfer basis, and date last reviewed. The client is informed of changes with 30 days' notice."),
            ("Current sub-processors", "{{SUBPROCESSORS}}"),
            ("Review", "Each critical supplier is reviewed at least annually and its security posture recorded."),
        ],
    },
    {
        "id": "data-retention",
        "title_en": "Data Retention and Deletion Policy",
        "title_fr": "Politique de Conservation et de Suppression des Donnees",
        "controls": ["A.5.33", "A.8.10", "MA09-08-07"],
        "sections": [
            ("Purpose", "To ensure {{COMPANY}} keeps personal and client data only as long as necessary and deletes it verifiably."),
            ("Retention schedule", "Client evidence and assessment records: {{RETENTION}}. Client personal data processed on instruction: deleted within 30 days of contract end. Logs: 12 months."),
            ("Deletion", "Deletion is performed through the platform's documented procedure and evidenced by a deletion certificate stating what was deleted, when, and by whom."),
            ("Client data on exit", "At the end of an engagement the client receives a complete export and a SHA-256 manifest, and the operator's working copy is deleted. A deletion certificate is issued."),
            ("Minimisation", "Where a control can be evidenced by a hash, metadata or an attestation, the raw document is not retained. This is the default for identity documents and HR records."),
        ],
    },
    {
        "id": "hr-security",
        "title_en": "Human Resources Security Policy",
        "title_fr": "Politique de Securite des Ressources Humaines",
        "controls": ["A.6.3", "A.6.4", "A.6.5", "A.6.6", "MA09-08-09"],
        "sections": [
            ("Purpose", "To ensure people understand and accept their security responsibilities before, during and after employment."),
            ("Before employment", "Background checks appropriate to the role are performed where lawful. Every new joiner signs a confidentiality agreement."),
            ("During employment", "Security awareness training is delivered at onboarding and at least annually. Completion is tracked. Disciplinary process applies to policy breaches."),
            ("On departure", "Assets are returned, access is revoked, and confidentiality obligations are restated in writing. The obligation of professional secrecy under Law 09-08 art. 26 survives the end of the engagement."),
        ],
    },
    {
        "id": "logging-monitoring",
        "title_en": "Logging and Monitoring Policy",
        "title_fr": "Politique de Journalisation et de Supervision",
        "controls": ["A.8.15", "A.8.16", "A.8.17", "MA05-20-06"],
        "sections": [
            ("Purpose", "To ensure that activity on {{COMPANY}} systems is recorded, protected and reviewed so that anomalies and incidents can be detected."),
            ("What is logged", "Authentication events (success and failure), authorisation changes, administrative actions, access to client data, and configuration changes to security controls."),
            ("Protection", "Logs are stored in a system with restricted write access, integrity protection, and a retention period of at least 12 months."),
            ("Review", "Alerts on high-severity events are routed to a monitored channel. Log review is performed at least monthly and recorded."),
            ("Clock sync", "All systems synchronise time to an authoritative source so that correlated events have consistent timestamps."),
        ],
    },
    {
        "id": "vulnerability-management",
        "title_en": "Vulnerability Management Policy",
        "title_fr": "Politique de Gestion des Vulnerabilites",
        "controls": ["A.8.8", "A.5.7", "MA05-20-02"],
        "sections": [
            ("Purpose", "To ensure vulnerabilities in {{COMPANY}} systems and dependencies are identified and remediated within defined timeframes."),
            ("Identification", "Dependency scanning runs on every change and at least weekly. Container images are scanned before deployment. Cloud configuration is assessed continuously against a benchmark."),
            ("Remediation timeframes", "Critical: 7 days. High: 30 days. Medium: 90 days. Low: next scheduled maintenance window."),
            ("Exceptions", "Where remediation is not possible within the timeframe, a documented, time-boxed exception is recorded with the compensating control and an owner."),
            ("Tracking", "Every finding has an owner and a due date. The open queue is reviewed at least monthly and ageing is reported to management."),
        ],
    },
    {
        "id": "privacy",
        "title_en": "Personal Data Protection Policy",
        "title_fr": "Politique de Protection des Donnees Personnelles",
        "controls": ["A.5.34", "MA09-08-01", "MA09-08-02", "MA09-08-05", "MA09-08-12"],
        "sections": [
            ("Purpose", "To ensure {{COMPANY}} processes personal data lawfully and transparently, in accordance with Law 09-08 and, where applicable, the GDPR."),
            ("Lawful basis and formalities", "Processing is registered in the processing register. Filings with the CNDP are made where required: a declaration in the general case, and a prior authorisation where processing involves sensitive data or identity-card numbers (Law 09-08 art. 12)."),
            ("Minimisation", "Only data necessary for the stated purpose is collected. Where a document is not required to evidence a control, a hash or attestation is retained instead."),
            ("Rights", "Data subjects can exercise access, rectification and objection rights through a documented procedure with a tracked response deadline."),
            ("Transfers", "Transfers outside Morocco rely on a State on the CNDP list (deliberation 236-2015: 32 States -- EEA, United Kingdom, Switzerland, Canada) or on a documented derogation. Transfers to the United States require CNDP authorisation."),
            ("Processor obligations", "Every processor relationship is governed by a written contract meeting Law 09-08 art. 23, and the client is given the information needed to declare the subcontracting under art. 14(i)."),
            ("Breach handling", "There is no statutory breach-notification deadline in Moroccan law. Contractual notification commitments to clients are defined in the Incident Management Policy and honoured."),
        ],
    },
    {
        "id": "risk-management",
        "title_en": "Risk Management Policy",
        "title_fr": "Politique de Gestion des Risques",
        "controls": ["A.5.7", "MA05-20-02"],
        "sections": [
            ("Purpose", "To define how {{COMPANY}} identifies, assesses and treats information security risk."),
            ("Method", "Risk is assessed on a 4x4 matrix of likelihood and impact. Impact levels: very severe, severe, moderate, limited -- aligned with Decree 2-21-406 art. 11 so that the same register can be used with a public-sector client."),
            ("Register", "A risk register records each risk with: description, owner, inherent score, treatment, residual score, and review date."),
            ("Treatment", "Treatment options are mitigate, transfer, avoid or accept. Acceptance requires documented sign-off by management for High and Critical risks."),
            ("Review", "The register is reviewed at least twice a year and whenever a significant change occurs."),
        ],
    },
    {
        "id": "management-review",
        "title_en": "Management Review Procedure",
        "title_fr": "Procedure de Revue de Direction",
        "controls": ["A.5.1", "A.5.2"],
        "sections": [
            ("Purpose", "To ensure top management reviews the information security management system at planned intervals."),
            ("Frequency", "At least once every 12 months."),
            ("Inputs", "Status of actions from previous reviews; changes in context; feedback on security performance including incidents and nonconformities; results of risk assessment; results of monitoring and measurement; audit results; fulfilment of objectives."),
            ("Outputs", "Decisions and actions relating to opportunities for improvement and any need for changes to the ISMS. Recorded with owners and due dates."),
        ],
    },
    {
        "id": "soa",
        "title_en": "Statement of Applicability",
        "title_fr": "Declaration d'Applicabilite (SoA)",
        "controls": ["A.5.1"],
        "sections": [
            ("Purpose", "This Statement of Applicability records which Annex A controls of ISO/IEC 27001:2022 apply to {{COMPANY}}, why, and their current implementation status."),
            ("How to read it", "For each control the SoA states: applicability, justification for inclusion or exclusion, implementation status, and a reference to the evidence held."),
            ("Status", "The current control-by-control position is generated from the compliance platform and exported alongside this document. It is a point-in-time record, not a certification."),
            ("Ownership", "The SoA is owned by {{SECURITY_OWNER}} and reviewed at each management review."),
        ],
    },
    {
        "id": "acceptable-use",
        "title_en": "Acceptable Use Policy",
        "title_fr": "Politique d'Usage Acceptable",
        "controls": ["A.5.10", "A.8.1"],
        "sections": [
            ("Purpose", "To define acceptable use of {{COMPANY}} systems, devices and accounts."),
            ("Rules", "Company systems are used for legitimate business. Personal use is tolerated where it does not affect security or performance. Installing unauthorised software, disabling security controls, and storing client data on personal devices are prohibited."),
            ("Devices", "Company laptops have disk encryption, screen lock, and automatic updates enabled."),
            ("Acceptance", "Every employee and contractor confirms acceptance of this policy at onboarding and annually."),
        ],
    },
    {
        "id": "physical-security",
        "title_en": "Physical and Environmental Security Policy",
        "title_fr": "Politique de Securite Physique",
        "controls": ["A.7.1", "A.7.4"],
        "sections": [
            ("Purpose", "To protect {{COMPANY}} premises and equipment from unauthorised physical access and environmental hazard."),
            ("Cloud-first note", "{{COMPANY}} operates primarily in cloud infrastructure hosted in {{HOSTING_REGION}}. Physical and environmental controls for that infrastructure are the hosting provider's responsibility; the provider's independent assurance report is held in the supplier register and reviewed under the Supplier and Sub-processor Policy. This policy covers the remaining office and endpoint footprint."),
            ("Office", "Office access is controlled and recorded. Visitors are escorted. Equipment is not left visible in unattended areas."),
            ("Disposal", "Devices and media holding Confidential or Restricted information are securely wiped before disposal, and the wipe is recorded."),
        ],
    },
    {
        "id": "network-security",
        "title_en": "Network Security Policy",
        "title_fr": "Politique de Securite Reseau",
        "controls": ["A.8.20", "A.8.21", "A.8.22", "A.8.23", "MA05-20-12"],
        "sections": [
            ("Purpose", "To define how {{COMPANY}} secures its networks and the boundaries between environments."),
            ("Segmentation", "Production, staging and development are separated at the network level. Development environments never hold production personal data."),
            ("Exposure", "Administrative interfaces (SSH, RDP, database ports) are never exposed to the public internet. Access is via bastion, VPN or a session manager."),
            ("Perimeter", "A TLS and HTTP-header baseline is checked continuously: TLS 1.2 minimum, HSTS, CSP, and expiry monitoring."),
            ("Email authentication", "SPF, DKIM and DMARC are published, with a DMARC policy of quarantine or reject."),
        ],
    },
    {
        "id": "audit-assurance",
        "title_en": "Internal Assurance and Evidence Policy",
        "title_fr": "Politique d'Assurance Interne et de Preuve",
        "controls": ["A.5.28", "A.5.35", "A.9.2"],
        "sections": [
            ("Purpose", "To define how {{COMPANY}} evidences that its controls operate, so that an independent reviewer can verify the position."),
            ("Evidence standard", "Evidence must be dated, attributable, and reproducible. A screenshot alone is weak evidence; a generated export with a hash is strong."),
            ("Integrity", "Evidence records carry a SHA-256 hash. Automated monitoring runs are chained in a tamper-evident ledger, so a deleted or edited run is detectable."),
            ("Automation", "Where a control can be checked automatically, the automated result is recorded as an observation. A named person remains responsible for the control status."),
            ("Internal review", "An internal review of control operation is performed at least annually and recorded."),
        ],
    },
]


REVIEW_BANNER = """> **Review required / Relecture requise** -- This policy was generated from a\ntemplate and pre-filled with the organisation's declared facts. It must be\nreviewed, adapted to actual practice, approved and signed before it is relied\nupon as evidence. A generated policy that nobody has read is not evidence.\n>\n> Cette politique a ete generee a partir d'un modele et pre-remplie. Elle doit\netre relue, adaptee a la pratique reelle, approuvee et signee avant d'etre\nutilisee comme preuve.\n\n"""


DEFAULTS = {
    "RTO": "4 hours",
    "RPO": "24 hours",
    "RETENTION": "36 months after engagement end",
    "SECURITY_CONTACT": "security@{{DOMAIN}}",
    "SECURITY_OWNER": "{{SIGNATORY}}",
    "SUBPROCESSORS": "See the current sub-processor register, maintained under the Supplier and Sub-processor Policy.",
}


def _facts(client: Client, domain: str = "") -> Dict[str, str]:
    d = dict(DEFAULTS)
    d.update({
        "COMPANY": client.legal_name,
        "DOMAIN": domain or client.contact_email.split("@")[-1] if "@" in (client.contact_email or "") else "example.com",
        "HOSTING_REGION": client.hosting_region or "eu-west-3",
        "HOSTING_COUNTRY": client.hosting_country or "France",
        "SIGNATORY": client.contact_name or "(to complete)",
        "RC": client.rc or "(to complete)",
        "ICE": client.ice or "(to complete)",
        "ADDRESS": client.address or "(to complete)",
        "DATE": _dt.date.today().isoformat(),
    })
    return d


def _fill(text: str, facts: Dict[str, str]) -> str:
    out = text
    for k, v in facts.items():
        out = out.replace("{{%s}}" % k, str(v))
    return out


def list_policies() -> List[Dict[str, Any]]:
    return [{"id": p["id"], "title_en": p["title_en"], "title_fr": p["title_fr"],
             "controls": p["controls"]} for p in POLICIES]


def render_policy(policy_id: str, client: Client, lang: str = "fr", domain: str = "") -> str:
    pol = next((p for p in POLICIES if p["id"] == policy_id), None)
    if pol is None:
        raise KeyError("unknown policy %r. Available: %s" % (
            policy_id, ", ".join(p["id"] for p in POLICIES)))

    facts = _facts(client, domain)
    title = pol["title_fr"] if lang == "fr" else pol["title_en"]

    L: List[str] = []
    L.append("# %s" % title)
    L.append("")
    L.append("**%s**  " % client.legal_name)
    if client.rc:
        L.append("RC: %s  " % client.rc)
    if client.ice:
        L.append("ICE: %s  " % client.ice)
    L.append("**Version:** 1.0 -- **%s**  " % facts["DATE"])
    L.append("")
    L.append("---")
    L.append("")

    for heading, body in pol["sections"]:
        L.append("## %s" % heading)
        L.append("")
        L.append(_fill(body, facts))
        L.append("")

    L.append("---")
    L.append("")
    L.append("## Controls satisfied")
    L.append("")
    for c in pol["controls"]:
        L.append("- %s" % c)
    L.append("")
    L.append("## Approval")
    L.append("")
    L.append("| Role | Name | Date | Signature |")
    L.append("|---|---|---|---|")
    L.append("| Owner | %s | | |" % facts["SIGNATORY"])
    L.append("| Approver (management) | | | |")
    L.append("")
    L.append("---")
    L.append("")
    L.append(REVIEW_BANNER)

    return chr(10).join(L)


def write_policies(
    ws: registry.Workspace,
    client_slug: str,
    policy_ids: Optional[List[str]] = None,
    lang: str = "fr",
    domain: str = "",
) -> List[str]:
    """Render policies into the client's policies/ directory. Returns paths."""
    client = ws.load_client(client_slug)
    d = os.path.join(ws.client_dir(client_slug), "policies")
    os.makedirs(d, exist_ok=True)
    ids = policy_ids or [p["id"] for p in POLICIES]
    written = []
    for pid in ids:
        text = render_policy(pid, client, lang=lang, domain=domain)
        path = os.path.join(d, "%s-%s.md" % (pid, lang))
        registry.atomic_write_text(path, text)
        written.append(path)
    return written
