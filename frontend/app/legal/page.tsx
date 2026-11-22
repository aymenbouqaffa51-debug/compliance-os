import { MarketingNav } from "@/components/MarketingNav";
import { MarketingFooter } from "@/components/MarketingFooter";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 border-t border-line py-12 first:border-t-0 first:pt-0">
      <h2 className="text-[20px] font-semibold tracking-tight">{title}</h2>
      <div className="mt-4 space-y-3 text-[13.5px] leading-relaxed text-dim">{children}</div>
    </section>
  );
}

export default function LegalPage() {
  return (
    <main>
      <MarketingNav />

      <div className="shell py-16">
        <div className="rounded-[14px] border border-[rgba(245,181,68,.3)] bg-[rgba(245,181,68,.08)] px-5 py-4 text-[13px] leading-relaxed text-warn">
          <strong>Draft — not yet reviewed by counsel.</strong> These pages are
          placeholders written to show the structure a Moroccan compliance SaaS
          needs. Replace every bracketed field and have a Moroccan lawyer review
          all four sections — especially the CNDP declaration status and the
          Law 05-20 positioning — before this page goes live for real customers.
        </div>

        <h1 className="mt-8 text-3xl font-semibold tracking-tight">Legal</h1>
        <p className="mt-2 text-[13.5px] text-dim">
          Mentions légales, privacy policy, terms of service and our security
          posture, in one place.
        </p>

        <Section id="mentions" title="Mentions légales">
          <p>
            <strong>Raison sociale :</strong> [Nom de la société] SARL<br />
            <strong>Capital social :</strong> [montant] MAD<br />
            <strong>RC :</strong> [numéro], Tribunal de commerce de [ville]<br />
            <strong>ICE :</strong> [numéro]<br />
            <strong>IF :</strong> [numéro]<br />
            <strong>Siège social :</strong> [adresse], Maroc<br />
            <strong>Directeur de la publication :</strong> [nom]<br />
            <strong>Hébergement :</strong> [hébergeur, adresse]
          </p>
          <p>
            Compliance OS n&rsquo;est pas un prestataire de services de cybersécurité
            qualifié par la DGSSI au sens de la loi 05-20. Le site propose des
            outils d&rsquo;auto-évaluation et d&rsquo;automatisation de preuves de conformité.
          </p>
        </Section>

        <Section id="privacy" title="Privacy policy">
          <p>
            We process the personal data you provide (account email, organisation
            name, and — once you use the product — the client and evidence data
            you enter) to operate the service. [Company name] is the data
            controller.
          </p>
          <p>
            <strong>CNDP registration:</strong> [état de votre déclaration —
            récépissé n° ____, daté du ____, ou "déclaration en cours"]. The
            national register is public; a client is entitled to verify this.
          </p>
          <p>
            <strong>Hosting and transfers:</strong> data is hosted in [region —
            e.g. the EU]. Morocco has no EU adequacy decision, so where we send
            personal data between the EU and Morocco we rely on [standard
            contractual clauses / consent / contractual necessity — specify].
          </p>
          <p>
            <strong>Retention, access and deletion requests:</strong> [describe
            your process and contact address].
          </p>
          <p>
            There is no statutory breach-notification duty under Law 09-08. Any
            breach-notification commitment we make is contractual, not a legal
            requirement, and will be stated explicitly where it applies.
          </p>
        </Section>

        <Section id="terms" title="Terms of service">
          <p>
            [Describe the service, acceptable use, account responsibilities,
            fees and billing terms, termination, limitation of liability, and
            governing law/jurisdiction — typically Moroccan law and the
            competent courts of [city].]
          </p>
          <p>
            Compliance OS is a readiness-assessment and evidence-automation tool.
            It does not issue certifications, does not perform the role of an
            accredited auditor, and is not legal advice.
          </p>
        </Section>

        <Section id="security" title="Security">
          <p>
            [Describe your own security practices as the vendor: encryption in
            transit/at rest, access controls, backup policy, incident response
            contact, and — once you have one — your own CNDP declaration and any
            certifications you hold.]
          </p>
          <p>
            To report a security issue, contact [security@yourdomain.ma].
          </p>
        </Section>
      </div>

      <MarketingFooter />
    </main>
  );
}
