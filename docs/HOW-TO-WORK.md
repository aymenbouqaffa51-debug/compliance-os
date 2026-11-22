# How to actually work with this

This is the operating manual: what you do on a Monday morning with a new client,
and what you say when they ask the awkward questions.

---

# Part 1 - Install (10 minutes, once)

```bash
cd compliance-os
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\\Scripts\\activate
pip install -e .
compliance init
```

**No install at all?** Every command also works as
`python3 -m compliance_os <command>` from inside the folder. Nothing else
to install, nothing to configure.


### If `pip install` refuses with "externally-managed-environment"

Modern Python (Debian/Ubuntu, and most 2026 distros) blocks system-wide pip
installs. That is PEP 668 working correctly. **Use a virtualenv** -- it is one
command and it is the right answer anyway:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
compliance --version
```

Inside the venv the `compliance` command works normally. Skip the venv entirely
and use `python3 -m compliance_os <command>` -- this needs **no install at all**
and behaves identically.


**Where your data lives:** `~/compliance-workspace` by default. Change it with
the `COMPLIANCE_WORKSPACE` environment variable:

```bash
export COMPLIANCE_WORKSPACE=/Users/you/clients
```

---

# Part 2 - Your first client, start to finish

The example is a 42-person Casablanca SaaS company that just got a security
questionnaire from a French client. Total time: about 3 hours of work across
two sessions.

## Step 1 - Create the workspace (2 minutes)

```bash
compliance client-new "Atlas Software SARL" \
  --sector SaaS \
  --headcount 42 \
  --contact "Yassine B." \
  --email yassine@atlas.ma \
  --export-markets France,Germany \
  --cin \
  --engagement readiness_check
```

**The flags matter.** They are how the tool knows which controls apply to this
client:

| Flag | Why you set it |
|---|---|
| `--export-markets` | Non-empty means cross-border transfer controls activate |
| `--cin` | The client processes national ID numbers -> **CNDP art.12 prior authorisation applies**. Set it honestly; getting this wrong is the most expensive error in the tool |
| `--sensitive` | Health / union / religion / ethnicity data -> art.12 also applies |
| `--public-entity` | The client is a Law 05-20 "entité" -> hosting localisation controls activate |

If you are unsure whether the client handles CIN, ask: *"do you store scans or
numbers of ID cards, for any purpose, including HR onboarding?"* Most do.

## Step 2 - Read the applicability output (5 minutes)

```bash
compliance assess atlas-software-sarl loi-09-08
```

You get three things:

1. **How many controls apply** and how many were excluded, with the reason.
2. **The full checklist** with current state per control.
3. **A live readiness percentage.**

**Read the exclusions.** They are your first insight. If `MA09-08-05`
(cross-border transfer) is excluded, the client genuinely has no foreign
transfers - good. If `MA09-08-02` (CIN authorisation) is *included*, that is
often the single most valuable finding of the engagement, because almost nobody
in Morocco has that authorisation.

## Step 3 - Interview and mark states (60-90 minutes)

Go through the controls with the client's CTO or compliance owner. For each one,
set a state and **write the note**. The note is what you sell.

```bash
# Compliant, with proof
compliance set atlas-software-sarl loi-09-08 MA09-08-01 implemented \
  --notes "Recepisse CNDP F211 no. 12345/2026, delivre le 12/03/2026" \
  --owner "Yassine B." --due 2026-12-15

# Exists but incomplete
compliance set atlas-software-sarl loi-09-08 MA09-08-05 partial \
  --notes "SCC signes avec le client francais, analyse d'impact (TIA) manquante" \
  --owner "Yassine B." --due 2026-12-31

# Missing entirely - the valuable finding
compliance set atlas-software-sarl loi-09-08 MA09-08-02 gap \
  --notes "Copies de CIN collectees a l'onboarding RH sans autorisation art.12. Delai CNDP: 2 mois. Risque: art.52 (10-100k MAD) et art.64 (doublement)."

# Legitimately out of scope - document WHY
compliance set atlas-software-sarl loi-09-08 MA09-08-11 not_applicable \
  --notes "Effectif 42, pas de donnees sensibles. A revisiter au-dela de 50."
```

**The discipline that makes you credible:** never write "OK" or "done". Write
the *evidence reference* — a number, a date, a document name. If you cannot cite
something, it is `partial`, not `implemented`.

## Step 4 - Attach evidence (20 minutes)

Two ways.

**Manual** (an attestation or a document you reviewed):

```bash
compliance evidence atlas-software-sarl loi-09-08 MA09-08-01 \
  --kind attestation \
  --summary "Recepisse CNDP F211 delivre" \
  --source "Registre national CNDP"
```

**Automated** (if the tool is installed):

```bash
# Committed secrets in their repo
compliance collect atlas-software-sarl iso-27001-2022 A.8.24 secrets --target /path/to/their/repo

# Vulnerable dependencies
compliance collect atlas-software-sarl iso-27001-2022 A.8.8 deps --target /path/to/their/repo

# Dangerous code patterns
compliance collect atlas-software-sarl iso-27001-2022 A.8.25 code --target /path/to/their/repo

# Prove which version of a policy you reviewed
compliance collect atlas-software-sarl loi-09-08 MA09-08-12 file \
  --target /path/to/politique-confidentialite.pdf \
  --summary "Politique revue le 20/11/2026"
```

**Important:** `collect` records an *observation*, never a pass. A scan finding
9 CVEs does not tell you the control fails — you decide that, based on their
remediation SLA. This is deliberate: an auditor will ask who judged the control,
and the answer must be a person.

**If a collector is not installed**, it prints `[skipped]` and records that. It
does not fail. Never present a skipped scan as a clean result.

## Step 5 - Produce the deliverable (2 minutes)

```bash
compliance report atlas-software-sarl --framework loi-09-08 --kind gap --lang fr
```

Output: `~/compliance-workspace/clients/atlas-software-sarl/reports/gap-loi-09-08-2026-11-22.md`

The report contains:
- Header with client facts and the framework's legal disclaimer
- Readiness percentage with a plain-language verdict
- Counts: applicable, excluded, gaps, partial, unassessed, evidence items
- **A specific recommended next step, computed from the heaviest gap**
- Every gap in priority order, with its legal reference, control objective,
  expected evidence, owner, due date, and your note
- The method section with the scope limitation and disclaimer

That last section is not decoration. It is what stops the report being mistaken
for an audit.

Also produce the register:

```bash
compliance report atlas-software-sarl --framework loi-09-08 --kind register --lang fr
```

## Step 6 - The legal pack

```bash
# The processor contract (Law 09-08 art. 23) - mandatory
compliance template dpa --client atlas-software-sarl \
  --provider "YOUR COMPANY SARL" --rc "RC-12345" --ice "001234567000001" \
  --region "eu-west-3 (France)" --country France \
  --output pack/DPA-atlas.md

# What the client must declare about you (art. 14(i))
compliance template pack-declarez-moi --client atlas-software-sarl \
  --provider "YOUR COMPANY SARL" --rc "RC-12345" --ice "001234567000001" \
  --region "eu-west-3 (France)" --country France

# EU transfer clauses + impact assessment (because Morocco has no adequacy decision)
compliance template scc-tia --client atlas-software-sarl \
  --provider "YOUR COMPANY SARL" --exporter "Client FR SAS" \
  --region "eu-west-3 (France)" --country France
```

Each one lists **what is still blank** at the end. Fill those, do not ship it
half-done.

---

# Part 3 - Running a retainer

Once a client is on the monthly plan, the loop is:

```bash
# Start of month: re-run the collectors
compliance collect <client> iso-27001-2022 A.8.24 secrets --target <repo>
compliance collect <client> iso-27001-2022 A.8.8 deps --target <repo>

# Review what changed, update states where remediation happened
compliance set <client> iso-27001-2022 A.8.8 partial --notes "9 CVE, 4 corriges, 5 restants - echeance 15/12"

# Regenerate the report as the monthly deliverable
compliance report <client> --framework iso-27001-2022 --kind gap --lang fr
```

Takes 30-60 minutes per client per month. That is the entire economics of the
retainer.

---

# Part 4 - The questions clients will ask

**"Are you going to certify us?"**
No, and nobody can except an accredited certification body. I prepare you for
their audit. Never let a client believe you issue a certificate.

**"Is this an audit?"**
No. It is a readiness assessment. This is not pedantry: Law 05-20 art. 49 makes
unqualified provision of the statutory cybersecurity-services category, or of
IIV sensitive-system review work, a 200,000-400,000 MAD offence. Say
*readiness*, *gap assessment*, *evidence programme* -- never the regulated terms.
The exact statutory wording is in docs/MOROCCO-RULES.md, which is exempt from
this lint precisely because it must quote the law.

**"Do we legally have to do this?"**
Probably not, and say so. Law 05-20 binds public entities, IIVs and five
operator categories — not ordinary private companies. What you *do* have is a
contractual deadline: your French client's questionnaire, your bank's vendor
file, your tender requirement. That is a real deadline and it is the one we are
solving.

**"Can you host our data in Morocco?"**
Yes, at roughly 12x the cost (genious.ma Casablanca is ~999 MAD/month vs ~79 MAD
for OVH France). For most private clients EU hosting is both cheaper and
CNDP-clean, because France, Germany and Finland are all on the 32-state adequacy
list. Moroccan residency is the right answer when the client is a public entity,
an IIV, or sells to one — that is a premium SKU, not your default.

**"Our client wants SOC 2. Can you give us SOC 2?"**
We prepare you for a SOC 2 examination. The report itself is issued by a
licensed CPA firm under AICPA standards, and you should always name the firm. A
self-issued "SOC 2 badge" is worthless and AICPA actively pursues sellers who
do that.

**"Is there a breach-notification duty in Moroccan law?"**
No. Law 09-08 has no breach-notification obligation — I checked all 67 articles.
Do not sell it as Moroccan law. Sell it as: *this is what your European client
will contractually require*, and *this is what becomes mandatory if the 09-08
reform passes*.

**"What happens to our data when we stop working together?"**
You zip the client folder, hand it over, and delete it. Say that in the contract
and then actually do it — that is what makes the data-minimisation claim real.

---

# Part 5 - Where this breaks

Be honest with yourself about these:

1. **It does not monitor automatically.** You re-run collectors and review.
   There is no real-time drift detection. Do not sell "continuous automated
   monitoring" until you have built it.
2. **The Moroccan control content is a reviewed synthesis, not the law.** Every
   framework file carries a disclaimer. Update the YAML when the law changes,
   and get a lawyer to review before you rely on it contractually.
3. **`loi-05-20` is a good-practice reference for private clients**, not a legal
   obligation. The framework header says so. Repeat it to clients.
4. **Conditions are simple boolean expressions.** If a client's situation is
   genuinely ambiguous, mark the control manually with a note rather than
   contorting the condition.
5. **No multi-user access control.** It is a single-operator CLI. Protect the
   workspace folder with filesystem permissions. Do not put it on a shared
   server without adding authentication.

---

# Part 6 - Five-minute smoke test

Before you trust any of this, run it:

```bash
export COMPLIANCE_WORKSPACE=/tmp/demo
compliance init
compliance client-new "Demo SARL" --headcount 30 --cin
compliance assess demo-sarl loi-09-08
compliance set demo-sarl loi-09-08 MA09-08-02 gap --notes "test"
compliance score demo-sarl
compliance report demo-sarl --framework loi-09-08 --kind gap --lang fr
cat /tmp/demo/clients/demo-sarl/reports/gap-loi-09-08-*.md
```

If all seven commands work and the report contains `MA09-08-02`, the tool is
healthy.
