# The Moroccan rules this tool encodes

Every claim below was checked against primary legal texts on **21 November 2026**.
Confidence labels: **VERIFIED** (read in the citing text), **LIKELY** (consistent
secondary sources, primary not read), **UNVERIFIED** (could not confirm).

If you change a YAML control because of something in this file, change it here
too, and record the date.

---

## 1. Law 05-20 (cybersecurity) - scope and the art. 49 trap

**VERIFIED - it does not bind ordinary private companies.** Art. 1 defines three
addressees: (a) "entités" = State administrations, territorial collectivities,
public establishments and enterprises and any other public-law legal person;
(b) infrastructures d'importance vitale (IIV); (c) "opérateurs" = public telecom
operators, ISPs, cybersecurity service providers, digital service providers,
internet platform publishers. **There is no general private-sector category.**

**VERIFIED - art. 49 carries 200,000-400,000 MAD** for, among others:
- providing sensitive-system audit services to IIVs without DGSSI qualification
- **providing "prestations de cybersécurité" without DGSSI qualification**

**AMBIGUOUS - the second limb is drafted broadly.** Art. 2 defines "service de
cybersécurité" narrowly (detection/diagnosis of incidents, strengthening system
security, delivered *to an entity or IIV*), so private-company readiness work
falls outside it on its face. But Moroccan commentary itself notes the exact
scope is unsettled. **Get a lawyer's written opinion before your first paid
engagement.**

**VERIFIED - DGSSI qualification is out of reach at zero capital.** Audit
providers (decree 2-21-406 arts. 20, 23) need a Moroccan company with an
organisation *dedicated exclusively* to SI security audit, qualified in at least
three audit domains with one auditor each, and Moroccan-majority capital for
CLASSE A. Cybersecurity providers (arts. 34, 37) need at least three specialists
and **hosting, processing, operation and administration exclusively in Morocco**.
PASSI accreditation takes about six months; only about seven firms held it.

**VERIFIED - it has been operative since 2021.** Art. 53 made entry into force
conditional on implementing texts; decree 2-21-406 of 15 July 2021 supplied them.

**VERIFIED - the 2026 revision is announced, not drafted.** A ministerial
statement of 16 Nov 2026 only. No bill text, no timetable. Do not build a product
or a price list on a law that does not exist.

---

## 2. Law 09-08 (personal data) - the part that actually binds you

**VERIFIED - art. 23 requires a written processor contract.** The processor acts
only on the controller's sole instruction and carries the same security
obligations. This is a mandatory DPA, not a nice-to-have. It is the first document
a European client's lawyer reads.

**VERIFIED - art. 12 requires PRIOR AUTHORISATION, not mere declaration,** where
processing involves:
- sensitive data (health incl. genetic, racial/ethnic origin, political opinions,
  religious/philosophical convictions, union membership)
- **data containing the national identity card (CIN) number**
- use of data for purposes other than those collected
- genetic data; data on offences/convictions/security measures
- interconnection of files of different legal persons with differing purposes

That is why `MA09-08-02` exists and is conditional on `handles_cin` /
`handles_sensitive_data`. Onboarding-evidence collection routinely ingests CIN
copies and sick-leave records. Decision windows: declaration gets a récépissé in
24 hours (art. 19); authorisation is decided within 2 months, extendable once.

**VERIFIED - art. 14(i) forces YOUR CLIENT to declare the subcontracting.** The
declaration must list "les recoupements, les interconnexions, ou toutes autres
formes de rapprochement des données ainsi que leur cession, sous-traitance, sous
toute forme, à des tiers". You therefore owe the client the facts. That is what
`template pack-declarez-moi` produces.

**VERIFIED - the CNDP adequacy list has exactly 32 States and excludes the USA.**
Délibération n° 236-2015 of 18 December 2015: Germany, Austria, Belgium,
Bulgaria, Canada, Cyprus, Denmark, Spain, Estonia, Finland, France, Greece,
Hungary, Ireland, Iceland, Italy, Latvia, Liechtenstein, Lithuania, Luxembourg,
Malta, Norway, Netherlands, Poland, Portugal, Czech Republic, Romania,
**United Kingdom**, Slovakia, Slovenia, Sweden, Switzerland.
**Not on the list: USA, India, Japan, Korea, UAE, Singapore, Israel, Brazil,
China.** Transfers under art. 44 need express consent, contractual necessity,
or an express reasoned CNDP authorisation (form F118), and the transfer
authorisation is only granted if the underlying processing was declared/authorised.

**VERIFIED NEGATIVE - there is no breach-notification duty in Law 09-08.** The
full 67-article text was read; Chapter VII runs arts. 51-66 with no notification
obligation. **Do not sell "72-hour breach notification" as Moroccan law.** The DPA
template states the 48-hour duty is contractual, expressly and in the document.

**VERIFIED - the sanction regime is criminal and doubles for legal persons.**
Art. 52 (processing without required declaration/authorisation): 10,000-100,000 MAD.
Arts. 54-56, 58, 60: 3 months-1 year and/or 20,000-200,000 MAD.
Art. 57 (sensitive data without express consent): 50,000-300,000 MAD.
**Art. 64: fines doubled for legal persons, plus partial confiscation or closure
of the establishment.** Art. 65 doubles on recidivism within one year.

**VERIFIED - the national register is public (arts. 45-46).** A client can check
your CNDP status. An unregistered processor is unsellable to a European security
team. Register yourself before your first client.

**VERIFIED - Morocco has no EU adequacy decision.** The European Commission's
published adequacy list omits Morocco. Your EU clients need SCCs plus a transfer
impact assessment to send you HR data. That is what `template scc-tia` is for.

---

## 3. Cloud and data localisation

**VERIFIED - art. 11 of Law 05-20 (sensitive data hosted exclusively in Morocco)
applies to entities and IIVs, and is extended to IIVs by art. 14.** It is not a
general rule for private companies.

**VERIFIED - "données sensibles" for localisation means only two classes.**
Decree 2-21-406 art. 13 defines TRÈS SECRET / SECRET / CONFIDENTIEL / DIFFUSION
RESTREINTE; **only TRÈS SECRET and SECRET count.** Classification must be reviewed
at least every 3 years (art. 15).

**VERIFIED - decree 2-24-921 of 22 October 2024 governs cloud qualification.**
Level 1 to host/manage/operate sensitive information systems; **level 2 to
process/operate/store sensitive data.** Level 2 requires Moroccan-majority capital,
processing and storage exclusively on national territory, management and
supervision exclusively from Morocco, no third-party access without client
agreement, and Moroccan-national operating staff. Qualification validity up to 5
years. Non-compliance goes formal notice -> suspension -> withdrawal.

**LIKELY - the compliance deadline is 21 August 2027.** The arrêté fixing the
requirements referential (n° 3-17-25 of 1 August 2025, BO 7432 of 21 August 2025)
is the trigger that put the decree into force, and entities already in the cloud
had 24 months. This is arithmetic inference from verified dates, not a quoted
deadline.

**UNVERIFIED - the current list of DGSSI-qualified cloud providers.** Decree
2-24-921 art. 12 requires publication in the Bulletin Officiel and on
dgssi.gov.ma, but the DGSSI site was unreachable and no BO list was retrieved.
**Do not tell a client which providers are qualified until you have read that
list.**

---

## 4. What a Moroccan company can actually show a buyer

**VERIFIED - ISO 27001 certificates come from independent certification bodies,
not from ISO, and accreditation is not compulsory** - but a certificate is only
verifiable through IAF CertSearch (now under Global ACI, the renamed IAF).

**VERIFIED (with a caveat) - Morocco's accreditation body is SEMAC**, a division
of the Ministry of Industry and Commerce. Its published NM ISO/CEI 17021-1 list
contains **exactly one body: IMANOR, accreditation AC 01/2016 dated 14/07/2016.**

**CAVEAT THAT MATTERS:** the list version retrieved is dated 04/12/2020 and prints
an expiry of 13 July 2021 as "Active" - it is stale and internally inconsistent.
Obtain the current SEMAC list before asserting anything. And this does **not**
mean only IMANOR can certify Moroccan companies: international bodies (Bureau
Veritas, TÜV, BSI) certify under their own foreign accreditation
(COFRAC/DAkkS/UKAS), which is normal and widely accepted. Also note IMANOR is
both the national standards body and an accredited certifier - a structural
conflict a procurement team may notice.

**INFERRED - SOC 2 has no nationality requirement on the audited entity.** SOC 2
is a CPA-firm attestation under AICPA professional standards; the constraint is on
*who performs the examination*, not where the client sits. AICPA is actively
pursuing unlicensed or peer-review-less SOC resellers, so always name the firm.

---

## 5. What could not be verified

Be careful with these. Do not present them as fact.

| # | Unverified item | What would close it |
|---|---|---|
| 1 | Any draft text or timetable for the 2026 revision of Law 05-20 | Bulletin Officiel; DGSSI announcements |
| 2 | The three DGSSI qualification lists (cloud, audit, cybersecurity providers) | dgssi.gov.ma opened manually in a browser |
| 3 | The DNSSI 2023 full text (reported 104 rules / 14 chapters) | DGSSI DNSSI page; circular 02/2023 |
| 4 | Whether a GRC SaaS is a "prestataire de services numériques" under art. 2 | **Written DGSSI position.** If yes: arts. 32-34 duties + DGSSI audits at your cost |
| 5 | Whether art. 49's "prestations de cybersécurité" could capture readiness consulting | Lawyer + DGSSI position in writing |
| 6 | The exact text of arrêté 3-17-25 / BO 7432 (14-15 domain referential) | Download the BO PDF from sgg.gov.ma |
| 7 | Whether the CNDP has adopted model contractual clauses | CNDP enquiry |
| 8 | Whether authorities have ever enforced 09-08 against a small processor | CNDP annual reports; practitioner interviews |
| 9 | Morocco's New York Convention status (enforcement of foreign arbitral awards) | Verify the ratification instrument |

---

## 6. The two things to do before your first paid client

1. **Send the lawyer and DGSSI questions.** The ready-to-send French letters are
   in your research pack (`01-morocco-regulation.md` sections 4.1 and 4.3).
2. **File your own CNDP declaration** (form F211) and, if you will handle CIN or
   sensitive data, ask about the art. 12 authorisation. The register is public.

---

*This file is a technical reference for building the tool, not legal advice.*
*Confidence labels are honest, including the"could not verify" section.*
