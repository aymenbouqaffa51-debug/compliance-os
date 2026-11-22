# Compliance OS

**Compliance evidence automation for Moroccan companies selling to Europe.**

ISO 27001 / SOC 2 readiness, with a native Moroccan regulatory layer
(Loi 09-08 / CNDP, Loi 05-20, DNSSI) already modelled as controls and
cross-mapped.

This is not a Vanta clone. Vanta sells to companies that already know they must
be compliant and can afford USD 7,500-25,000/year. This sells to the Moroccan
company that just received a 120-question security questionnaire from a French
client and has two weeks to answer it.

---

## Why this exists

Three facts drove the design:

1. **No Moroccan law forces private companies to buy compliance.** Law 05-20
   binds public entities, vital infrastructures (IIV) and five operator
   categories -- not ordinary private SMEs. The demand is **contractual**: an
   EU client's questionnaire, a bank's vendor file, a public tender.
2. **The vocabulary is legally load-bearing.** Law 05-20 art. 49 fines
   unqualified provision of the statutory category of cybersecurity services, or
   of IIV sensitive-system review work, at **200,000-400,000 MAD**. So this tool
   says *readiness*, *gap assessment*, *evidence programme* -- never the
   regulated terms. See docs/MOROCCO-RULES.md for the exact wording of the
   statute and the vocabulary that is safe to use.
3. **The Moroccan layer is the moat.** A foreign platform will never model CNDP
   forms, DGSSI qualification levels, or the TRES SECRET / SECRET classification.

---

## Install

Requires **Python 3.9+**. Nothing else. No database, no Docker, no account.

```bash
cd compliance-os
python3 -m venv .venv
source .venv/bin/activate
pip install -e .            # installs the `compliance` command
```

**Or skip the install entirely** -- everything works as
`python3 -m compliance_os <command>` from inside the folder.

Verify:

```bash
compliance init
```

That creates `~/compliance-workspace` and lists the frameworks.

**Optional** collectors (the tool works fine without them; they just add
automated evidence):

```bash
# none required. If present, `compliance collect` uses them:
#   gitleaks  - committed secrets
#   trivy     - vulnerable dependencies
#   semgrep   - dangerous code patterns
```

---

## The 60-second tour

```bash
# 1. Create a client. Flags change which controls apply.
compliance client-new "Atlas Software SARL" \
  --sector SaaS --headcount 42 \
  --contact "Yassine B." --email yassine@atlas.ma \
  --export-markets France,Germany \
  --cin

# 2. See the working checklist. Controls that don't apply are excluded
#    automatically -- and the reason is printed.
compliance assess atlas-software-sarl loi-09-08

# 3. Work through it.
compliance set atlas-software-sarl loi-09-08 MA09-08-01 implemented \
  --notes "Recepisse CNDP no. 12345/2026 du 12/03/2026" \
  --owner Yassine --due 2026-12-15

compliance set atlas-software-sarl loi-09-08 MA09-08-02 gap \
  --notes "Autorisation art.12 absente alors que des copies de CIN sont collectees"

# 4. Attach evidence.
compliance evidence atlas-software-sarl loi-09-08 MA09-08-01 \
  --kind attestation --summary "Recepisse CNDP F211 delivre" \
  --source "Registre national CNDP"

# 5. Produce the deliverable you send the client.
compliance report atlas-software-sarl --framework loi-09-08 --kind gap --lang fr
```

The report lands in
`~/compliance-workspace/clients/<slug>/reports/gap-loi-09-08-<date>.md`.

---

## What's inside

### Four frameworks

| ID | Framework | Controls | Language |
|---|---|---|---|
| `iso-27001-2022` | ISO/IEC 27001:2022 Annex A (operational selection) | 47 | EN |
| `loi-09-08` | Loi 09-08 -- protection des donnees personnelles (CNDP) | 12 | FR |
| `loi-05-20` | Loi 05-20 -- cybersecurite (DGSSI), as good practice | 12 | FR |
| `soc2-tsc` | SOC 2 Trust Services Criteria (operational selection) | 33 | EN |

**104 controls, cross-mapped.** Every ISO control that has a Moroccan analogue
carries `maps_to: [MA09-08-xx, MA05-20-xx]`, so one evidence-collection pass
satisfies both an ISO auditor and a CNDP form.

### Conditional controls

A control only appears when it applies to that client. `MA09-08-02` (CNDP prior
authorisation under art. 12) is excluded for a client that does not process the
national ID number, and included the moment you pass `--cin`. The exclusion
reason is always printed, so the client can see *why* something is out of scope.

### Scoring that survives an auditor

- `not_applicable` is **excluded from the denominator**, not scored zero. A
  client who legitimately excludes a control is not punished for it.
- Controls are **weighted** (1.0-3.0). Losing a weight-3 control costs more than
  losing a weight-1 one, so the gap list is a genuine priority order.
- A collector **never** flips a control to passing. It records an observation.
  A human sets the state. That separation is what makes the output defensible.

### Legal templates that ship with it

```bash
compliance template dpa     --client <slug>   # Law 09-08 art. 23 processor agreement
compliance template pack-declarez-moi --client <slug>   # what the client must declare (art. 14(i))
compliance template scc-tia --client <slug>   # EU transfer clauses + TIA, because Morocco has no adequacy decision
```

Each renders with the client's facts prefilled and lists what is still blank.

---

## The Moroccan rules baked into the code

These are not comments, they are behaviour:

| Rule | Where it lives |
|---|---|
| CNDP adequacy list = 32 states, **USA excluded** | The templates require an explicit transfer basis; the DPA names the hosting region |
| Art. 12 prior authorisation for CIN / sensitive data | `MA09-08-02`, conditional on `handles_cin` / `handles_sensitive_data` |
| Art. 23 mandatory written processor contract | `MA09-08-03` + the DPA template |
| Art. 14(i) forces the client to declare the subcontracting | `MA09-08-04` + the "declarez-moi" pack |
| **No** breach-notification duty in Law 09-08 | Stated in the DPA clause 7.3 and the SOC 2/Law mapping, so nobody sells it as law |
| Law 05-20 does not bind ordinary private companies | The `loi-05-20` framework header and every rendered report say so |
| Art. 49 vocabulary trap | No report, template or CLI string calls the work an audit |

---

## Commands

| Command | What it does |
|---|---|
| `init` | Create the workspace, list frameworks |
| `frameworks` | List framework IDs |
| `show <framework>` | Show every control with weight and applicability |
| `client-new <name> [flags]` | Create a client workspace |
| `clients` | List clients and their assessments |
| `assess <client> <framework>` | Working checklist with live score |
| `set <client> <fw> <control> <state>` | Set state (implemented / partial / gap / not_applicable / not_assessed) |
| `evidence <client> <fw> <control>` | Attach a manual evidence record |
| `collect <client> <fw> <control> <tool>` | Run a **read-only** collector and attach the result |
| `report <client> --kind gap\|register\|summary` | Generate a deliverable (FR or EN) |
| `score <client>` | Readiness score across frameworks |
| `search <term>` | Search controls and their cross-mappings |
| `template dpa\|pack-declarez-moi\|scc-tia` | Render a legal document |

---

## Files and privacy

Everything is plain files. A client workspace is a folder:

```
~/compliance-workspace/clients/atlas-software-sarl/
  client.json                       # profile + applicability flags
  assessments/loi-09-08.json        # states, notes, owners, evidence
  reports/                          # generated deliverables
```

That means you can **zip, back up, hand over, or delete** a client in one
command. `compliance` never phones home. There is no telemetry.

**Recommended deletion-on-exit**: when an engagement ends, zip the client folder,
hand it to the client, then delete it from your workspace. That is what makes
the CNDP data-minimisation claim true rather than aspirational.

---

## Tests

```bash
python3 tests/test_engine.py       # no pytest needed
# or
python3 -m pytest tests/ -v
```

9 tests, covering: framework loading, unique control IDs, cross-map integrity
(every ISO -> MA mapping points at a real Moroccan control), `not_applicable`
denominator behaviour, weighting, conditional applicability, partial = 50%,
report generation, and client round-trip.

---

## What this is NOT

- **Not an audit.** Certification comes from an independent accredited body.
- **Not a SOC 2 report.** That is an attestation from a licensed CPA firm.
- **Not legal advice.** Every framework carries a disclaimer.
- **Not a DGSSI qualification.** You cannot audit IIV sensitive systems without it.
- **Not a replacement for your judgement.** It organises evidence; you decide.

Read the disclaimers in each YAML file before using any of this with a client.

---

## Extending it

Add a framework by dropping a YAML file in `compliance_os/data/frameworks/`:

```yaml
id: my-framework
name: "My framework"
version: "2026"
locale: en
authority: "Whoever issues it"
disclaimer: "What this is not."
controls:
  - id: MY-01
    title: "A requirement"
    ref: "art. 1"
    theme: "Theme name"
    objective: "What it actually requires."
    weight: 2.0
    applicability: conditional        # or "all"
    condition: "client.handles_cin"   # evaluated against the client profile
    evidence:
      - "What a reviewer would accept as proof"
    maps_to: [A.5.34, MA09-08-01]
```

Conditions have access to every client field plus `headcount_num` and
`transfers_abroad`. Available helpers: `len`, `int`, `bool`, `str`, `any`,
`all`, `min`, `max`.

---

## Licence

MIT. See `LICENSE`.

Built with facts verified against primary Moroccan legal texts on 21 November
2026. See `docs/MOROCCO-RULES.md` for the source list and the claims that could
**not** be verified.
