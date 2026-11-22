import Link from "next/link";
import { MarketingNav } from "@/components/MarketingNav";
import { MarketingFooter } from "@/components/MarketingFooter";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { Badge } from "@/components/ui/Badge";
import { Metric } from "@/components/ui/Metric";
import { Bar } from "@/components/ui/Bar";
import {
  IconShield, IconPulse, IconClipboard, IconDoc, IconPlug,
  IconSparkles, IconArrowRight, IconCheck, IconExternal,
} from "@/components/ui/Icons";

const FRAMEWORKS = [
  "ISO/IEC 27001:2022",
  "SOC 2 — Trust Services Criteria",
  "Loi 09-08 — CNDP",
  "Loi 05-20 — DNSSI reference",
];

const SECTORS = ["SaaS exporters", "Fintech", "BPO & call centers", "Manufacturing", "Healthtech", "Logistics"];

const FEATURES = [
  {
    icon: IconDoc,
    title: "One evidence pass, four frameworks",
    body: "ISO 27001, SOC 2 and the Moroccan Loi 09-08 / Loi 05-20 layer are cross-mapped control by control — one piece of evidence satisfies an ISO auditor and a CNDP form at once.",
  },
  {
    icon: IconShield,
    title: "Controls that know your business",
    body: "A control only appears when it applies. Handle CIN numbers or sensitive data and the right CNDP authorisation controls switch on — with the exclusion reason always visible.",
  },
  {
    icon: IconPulse,
    title: "Continuous control monitoring",
    body: "Optional collectors surface observations from your stack. A collector only ever records an observation — a human still sets the control state.",
  },
  {
    icon: IconClipboard,
    title: "Questionnaire autopilot",
    body: "Drop in the 120-question file your client sent. Get each question matched to controls, a confidence score, and a drafted answer backed by your evidence.",
  },
  {
    icon: IconExternal,
    title: "A Trust Center you can share",
    body: "Publish a live, read-only readiness page per client — scores, monitor status, data-residency facts — so the next questionnaire starts from a link.",
  },
  {
    icon: IconPlug,
    title: "Legal templates, prefilled",
    body: "Article 23 processor agreements, the art. 14(i) subcontracting declaration pack, and SCC + transfer impact assessments, generated with your client\u2019s facts already in place.",
  },
];

const STEPS = [
  { n: "01", title: "Scope the client", body: "Sector, headcount, export markets and a couple of flags decide which controls actually apply." },
  { n: "02", title: "Run the gap assessment", body: "Work the checklist control by control — implemented, partial, gap, not applicable." },
  { n: "03", title: "Attach evidence as you go", body: "Manual attestations and automated observations land on the same control." },
  { n: "04", title: "Ask the agent, publish the answer", body: "Get a grounded, cited answer in seconds, or publish a Trust Center link instead of a spreadsheet." },
];

const PLANS = [
  {
    name: "Starter",
    price: "Contact us",
    desc: "For your first European questionnaire.",
    features: ["1 client workspace", "ISO 27001 + Loi 09-08", "Questionnaire autopilot", "Email support"],
  },
  {
    name: "Growth",
    price: "Contact us",
    desc: "For a consultancy running several clients.",
    features: ["Unlimited client workspaces", "All 4 frameworks cross-mapped", "Continuous monitoring collectors", "Compliance agent included", "Trust Center per client"],
    highlight: true,
  },
  {
    name: "Enterprise",
    price: "Contact us",
    desc: "For regulated groups and audit firms.",
    features: ["SSO + audit-grade ledger", "Dedicated onboarding", "Custom control mapping", "Priority support"],
  },
];

export default function LandingPage() {
  return (
    <main className="overflow-x-hidden">
      <MarketingNav />

      {/* ---------------- Hero ---------------- */}
      <section className="relative border-b border-line">
        <div className="shell relative pb-16 pt-20 text-center sm:pt-28">
          <span className="pill mx-auto border-[rgba(91,140,255,.25)] bg-[rgba(91,140,255,.10)] text-[#a9c2ff]">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--ok)]" />
            Built in Morocco, for Moroccan exporters
          </span>

          <h1 className="mx-auto mt-6 max-w-3xl text-4xl font-semibold tracking-tight sm:text-5xl md:text-6xl">
            Answer the next security questionnaire
            <span className="block bg-gradient-to-r from-[#8fb0ff] to-[#b79bff] bg-clip-text text-transparent">
              in days, not weeks.
            </span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-dim sm:text-lg">
            Compliance OS turns ISO 27001, SOC 2 and Morocco&rsquo;s own Loi 09-08 / Loi
            05-20 requirements into a single evidence programme — with an agent that
            answers from your actual record, not from guesswork.
          </p>

          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/login" className="btn-primary px-6 py-2.5 text-[14px]">
              Start a free readiness assessment
              <IconArrowRight size={14} />
            </Link>
            <a href="#agent" className="btn-ghost px-6 py-2.5 text-[14px]">
              Meet the compliance agent
            </a>
          </div>

          <p className="mt-4 text-[11.5px] text-mute">
            No credit card. No DGSSI claim made or implied — readiness and evidence
            tooling only.
          </p>
        </div>

        {/* product mockup, built from the real UI components */}
        <div className="shell pb-24">
          <div className="card animate-in mx-auto max-w-4xl !p-0 shadow-[var(--shadow-glow)]">
            <div className="flex items-center gap-1.5 border-b border-line px-4 py-3">
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--bad)]/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--warn)]/70" />
              <span className="h-2.5 w-2.5 rounded-full bg-[var(--ok)]/70" />
              <span className="ml-3 text-[11px] text-mute">app.complianceos.ma/dashboard</span>
            </div>
            <div className="grid gap-4 p-6 sm:grid-cols-3">
              {[
                { l: "ISO/IEC 27001:2022", v: 86 },
                { l: "SOC 2 — TSC", v: 74 },
                { l: "Loi 09-08 — CNDP", v: 92 },
              ].map((s) => (
                <div key={s.l} className="metric flex items-center gap-4 text-left">
                  <ScoreRing pct={s.v} size={56} />
                  <div>
                    <div className="panel-title">{s.l}</div>
                    <div className="mt-1 text-[12px] text-dim">readiness</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="grid gap-px border-t border-line bg-[var(--line-soft)] sm:grid-cols-2">
              <div className="bg-[var(--surface)] p-5 text-left">
                <div className="panel-title">Recent evidence</div>
                <p className="mt-2 text-[13px] text-dim">
                  Récépissé CNDP n° 12 345/2026 attached to <span className="text-[var(--text)]">MA09-08-01</span>
                </p>
                <div className="mt-3"><Badge value="implemented" /></div>
              </div>
              <div className="bg-[var(--surface)] p-5 text-left">
                <div className="panel-title">Monitor observation</div>
                <p className="mt-2 text-[13px] text-dim">
                  0 committed secrets · 2 dependencies flagged by <span className="text-[var(--text)]">trivy</span>
                </p>
                <div className="mt-3"><Badge value="medium" label="review" /></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------- Frameworks ---------------- */}
      <section id="frameworks" className="border-b border-line" style={{ background: "var(--bg-soft)" }}>
        <div className="shell py-10">
          <p className="text-center text-[11px] uppercase tracking-[.13em] text-mute">
            Modelled against the frameworks Moroccan exporters are actually asked for
          </p>
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2.5">
            {FRAMEWORKS.map((f) => (
              <span key={f} className="pill border-line bg-[var(--surface-2)] text-dim">{f}</span>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Problem framing ---------------- */}
      <section className="shell py-20">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div>
            <p className="panel-title text-[#a9c2ff]">Why this exists</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              You didn&rsquo;t go looking for compliance.
              <br /> A client&rsquo;s procurement team did.
            </h2>
            <p className="mt-4 text-[14px] leading-relaxed text-dim">
              Most Moroccan companies aren&rsquo;t legally required to run a compliance
              programme. The demand is contractual: a French client&rsquo;s security
              questionnaire, a bank&rsquo;s vendor file, a public tender. Compliance OS is
              built around that reality.
            </p>
            <ul className="mt-6 space-y-3 text-[13.5px]">
              {[
                "Evidence structured around the questionnaire you actually received",
                "Controls excluded — with a visible reason — when they don\u2019t apply to you",
                "A Moroccan regulatory layer no foreign platform models correctly",
              ].map((t) => (
                <li key={t} className="flex items-start gap-2.5">
                  <span className="mt-0.5 flex h-5 w-5 flex-none items-center justify-center rounded-full bg-[rgba(91,140,255,.14)] text-[#a9c2ff]">
                    <IconCheck size={12} />
                  </span>
                  {t}
                </li>
              ))}
            </ul>
          </div>

          <div className="card">
            <div className="panel-title">Who it&rsquo;s built for</div>
            <div className="mt-4 flex flex-wrap gap-2">
              {SECTORS.map((s) => (
                <span key={s} className="pill border-line bg-[var(--surface-2)] text-dim">{s}</span>
              ))}
            </div>
            <div className="divider my-6" />
            <div className="panel-title">A real scenario</div>
            <p className="mt-2 text-[13.5px] leading-relaxed text-dim">
              &ldquo;A 42-person SaaS company in Casablanca gets a 120-question
              security review from a new French client, two-week deadline.
              Compliance OS turns that into a scoped checklist, an evidence
              programme, and a drafted response.&rdquo;
            </p>
            <p className="mt-2 text-[11px] text-mute">Illustrative scenario, not a customer quote.</p>
          </div>
        </div>
      </section>

      {/* ---------------- Features ---------------- */}
      <section id="product" className="border-y border-line" style={{ background: "var(--bg-soft)" }}>
        <div className="shell py-20">
          <div className="mx-auto max-w-2xl text-center">
            <p className="panel-title text-[#a9c2ff]">Product</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              Everything the evidence programme needs.
            </h2>
          </div>

          <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div key={f.title} className="card card-hover h-full">
                <div className="flex h-10 w-10 items-center justify-center rounded-[10px] bg-[rgba(91,140,255,.12)] text-[#a9c2ff]">
                  <f.icon size={18} />
                </div>
                <h3 className="mt-4 text-[14.5px] font-semibold">{f.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-dim">{f.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Agent ---------------- */}
      <section id="agent" className="shell py-20">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div className="card !p-6">
            <div className="flex items-center gap-2.5 border-b border-line pb-4">
              <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-[rgba(91,140,255,.12)] text-[#a9c2ff]">
                <IconSparkles size={16} />
              </span>
              <div>
                <div className="text-[13px] font-semibold">Compliance agent</div>
                <div className="text-[11px] text-mute">answers from your evidence only</div>
              </div>
            </div>
            <div className="mt-4 space-y-3">
              <div className="msg-user ml-auto max-w-[85%] px-3.5 py-2.5 text-[13px]">
                Are we ready to answer a transfer question from our French client?
              </div>
              <div className="msg-agent max-w-[90%] px-3.5 py-2.5 text-[13px] leading-relaxed">
                France is on the CNDP adequacy list, so a standard transfer is lower
                friction — but your art. 23 processor contract is still required.
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="citation">transfer:FR</span>
                  <span className="citation">control:MA09-08-05</span>
                </div>
              </div>
            </div>
          </div>

          <div>
            <p className="panel-title text-[#a9c2ff]">New in this release</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              An agent that cites its evidence — or says it doesn&rsquo;t know.
            </h2>
            <p className="mt-4 text-[14px] leading-relaxed text-dim">
              Every answer is built from a retrieved context bundle and carries a
              citation to a control, monitor check or score. When the record
              doesn&rsquo;t support an answer, it says so and routes you to the right
              screen — it never guesses.
            </p>
            <ul className="mt-6 space-y-2.5 text-[13px] text-dim">
              {[
                "Works fully offline from an LLM — no US provider dependency required",
                "CNDP transfer position computed from the canonical adequacy list",
                "Declines out-of-scope questions instead of improvising",
              ].map((t) => (
                <li key={t} className="flex items-start gap-2.5">
                  <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
                  {t}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ---------------- How it works ---------------- */}
      <section id="how-it-works" className="border-t border-line" style={{ background: "var(--bg-soft)" }}>
        <div className="shell py-20">
          <div className="mx-auto max-w-2xl text-center">
            <p className="panel-title text-[#a9c2ff]">How it works</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              From a blank client file to a cited answer
            </h2>
          </div>

          <div className="mt-14 grid gap-5 md:grid-cols-4">
            {STEPS.map((s) => (
              <div key={s.n} className="card h-full">
                <div className="text-[28px] font-semibold text-[var(--line)]">{s.n}</div>
                <h3 className="mt-2 text-[14px] font-semibold">{s.title}</h3>
                <p className="mt-2 text-[13px] leading-relaxed text-dim">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- Trust center preview ---------------- */}
      <section id="trust-preview" className="shell py-20">
        <div className="grid gap-10 md:grid-cols-2 md:items-center">
          <div>
            <p className="panel-title text-[#a9c2ff]">Trust Center</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              Stop rebuilding the same review for every client.
            </h2>
            <p className="mt-4 text-[14px] leading-relaxed text-dim">
              Publish a read-only page with framework scores, monitor status and
              data-residency facts for each client. Share the link instead of a
              spreadsheet.
            </p>
            <Link href="/login" className="btn-primary mt-6 inline-flex px-5 py-2.5 text-[13.5px]">
              Try the dashboard
              <IconArrowRight size={13} />
            </Link>
          </div>

          <div className="card">
            <p className="panel-title text-[#a9c2ff]">Security posture</p>
            <h3 className="mt-2 text-[18px] font-semibold">Atlas Software SARL</h3>
            <p className="text-[12.5px] text-dim">SaaS · Casablanca</p>
            <div className="mt-5 grid grid-cols-2 gap-3">
              <Metric label="ISO/IEC 27001:2022" value="86%" tone="accent" />
              <Metric label="Loi 09-08 — CNDP" value="92%" tone="ok" />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-3">
              <Metric label="Monitors passing" value={18} tone="ok" />
              <Metric label="EU data residency" value="Frankfurt, DE" />
            </div>
            <div className="mt-3"><Bar pct={88} tone="accent" /></div>
            <p className="mt-4 text-[11px] leading-relaxed text-mute">
              Sample data for illustration — every published Trust Center carries a
              disclaimer appropriate to that client&rsquo;s actual legal status.
            </p>
          </div>
        </div>
      </section>

      {/* ---------------- Pricing ---------------- */}
      <section id="pricing" className="border-t border-line" style={{ background: "var(--bg-soft)" }}>
        <div className="shell py-20">
          <div className="mx-auto max-w-2xl text-center">
            <p className="panel-title text-[#a9c2ff]">Pricing</p>
            <h2 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">
              Simple pricing. Billed by invoice while we onboard early customers.
            </h2>
            <p className="mt-3 text-[13.5px] text-dim">
              Self-serve checkout is coming; for now every plan starts with a short call.
            </p>
          </div>

          <div className="mt-14 grid gap-5 md:grid-cols-3">
            {PLANS.map((p) => (
              <div key={p.name} className={`card flex h-full flex-col ${p.highlight ? "shadow-[var(--shadow-glow)]" : ""}`}
                   style={p.highlight ? { borderColor: "rgba(91,140,255,.4)" } : undefined}>
                {p.highlight && (
                  <span className="pill mb-3 w-fit border-[rgba(91,140,255,.3)] bg-[rgba(91,140,255,.12)] text-[#a9c2ff]">
                    Most popular
                  </span>
                )}
                <div className="text-[15px] font-semibold">{p.name}</div>
                <div className="mt-1 text-[13px] text-dim">{p.desc}</div>
                <div className="mt-4 text-[22px] font-semibold">{p.price}</div>
                <ul className="mt-5 flex-1 space-y-2.5 text-[12.5px] text-dim">
                  {p.features.map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <span className="mt-0.5 text-[var(--ok)]"><IconCheck size={13} /></span>
                      {f}
                    </li>
                  ))}
                </ul>
                <Link href="/login" className={p.highlight ? "btn-primary mt-6 justify-center" : "btn-ghost mt-6 justify-center"}>
                  Talk to us
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- CTA ---------------- */}
      <section className="shell py-20 text-center">
        <h2 className="mx-auto max-w-2xl text-3xl font-semibold tracking-tight sm:text-4xl">
          Built for the company that just got the questionnaire.
        </h2>
        <p className="mx-auto mt-4 max-w-xl text-[14px] text-dim">
          Scope your first client, run the gap assessment, and see how far your
          existing evidence actually gets you — today.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link href="/login" className="btn-primary px-6 py-2.5 text-[14px]">
            Start free
            <IconArrowRight size={14} />
          </Link>
          <a href="#frameworks" className="btn-ghost px-6 py-2.5 text-[14px]">
            Compare frameworks
          </a>
        </div>
      </section>

      <MarketingFooter />
    </main>
  );
}
