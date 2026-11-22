#!/bin/bash
# demo.sh - a complete walkthrough in about 20 seconds.
# Run:  bash demo.sh
set -e

export COMPLIANCE_WORKSPACE=/tmp/compliance-demo
export NO_COLOR=1
rm -rf "$COMPLIANCE_WORKSPACE"

CMD="python3 -m compliance_os"
if command -v compliance >/dev/null 2>&1; then CMD=compliance; fi

echo "== 1. Workspace and frameworks =="
$CMD init
echo
echo "== 2. Create a client that processes ID-card numbers =="
$CMD client-new "Atlas Software SARL" \
  --sector SaaS --headcount 42 \
  --contact "Yassine B." --email yassine@atlas.ma \
  --export-markets France,Germany --cin
echo
echo "== 3. The CNDP checklist. Note which controls apply. =="
$CMD assess atlas-software-sarl loi-09-08
echo
echo "== 4. Record findings =="
$CMD set atlas-software-sarl loi-09-08 MA09-08-01 implemented --notes "Recepisse CNDP F211 no. 12345/2026 du 12/03/2026"
$CMD set atlas-software-sarl loi-09-08 MA09-08-02 gap --notes "Autorisation art.12 absente alors que des copies de CIN sont collectees" --due 2026-12-01
$CMD set atlas-software-sarl loi-09-08 MA09-08-03 implemented
$CMD set atlas-software-sarl loi-09-08 MA09-08-05 partial --notes "SCC signes, TIA manquante"
echo
echo "== 5. Attach evidence =="
$CMD collect atlas-software-sarl loi-09-08 MA09-08-07 attestation --summary "Purge manuelle confirmee par le CTO le 12/11/2026" --target "Entretien CTO"
echo
echo "== 6. Score =="
$CMD score atlas-software-sarl
echo
echo "== 7. Generate the client deliverable =="
$CMD report atlas-software-sarl --framework loi-09-08 --kind gap --lang fr
echo
echo "== 8. Generate the legal pack =="
$CMD template dpa --client atlas-software-sarl --provider "YOUR COMPANY SARL" --rc "RC-12345" --ice "001234567000001" --region "eu-west-3 (France)" --country France --output "$COMPLIANCE_WORKSPACE/DPA.md"
echo
echo "Done. Open the report:"
ls -1 "$COMPLIANCE_WORKSPACE"/clients/atlas-software-sarl/reports/
