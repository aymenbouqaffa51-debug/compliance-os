import Link from "next/link";
import { IconShield } from "@/components/ui/Icons";

export function MarketingFooter() {
  return (
    <footer className="border-t border-line">
      <div className="shell py-14">
        <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-5">
          <div className="lg:col-span-2">
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-[#6b96ff] to-[#8b5cf6] text-white">
                <IconShield size={16} />
              </span>
              <span className="text-[14px] font-semibold tracking-tight">Compliance OS</span>
            </div>
            <p className="mt-3 max-w-xs text-[13px] leading-relaxed text-dim">
              Readiness assessment and evidence automation for Moroccan companies
              selling into Europe — ISO 27001, SOC 2 and the native Loi 09-08 /
              Loi 05-20 layer, cross-mapped.
            </p>
            <p className="mt-4 text-[11px] text-mute">🇲🇦 Made in Morocco.</p>
          </div>

          <div>
            <div className="panel-title">Product</div>
            <ul className="mt-3 space-y-2 text-[13px] text-dim">
              <li><Link className="hover:text-[var(--text)]" href="/dashboard">Readiness</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/monitors">Monitors</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/questionnaires">Questionnaires</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/policies">Policies</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/integrations">Integrations</Link></li>
            </ul>
          </div>

          <div>
            <div className="panel-title">Frameworks</div>
            <ul className="mt-3 space-y-2 text-[13px] text-dim">
              <li>ISO/IEC 27001:2022</li>
              <li>SOC 2 — Trust Services Criteria</li>
              <li>Loi 09-08 — CNDP</li>
              <li>Loi 05-20 — DNSSI reference</li>
            </ul>
          </div>

          <div>
            <div className="panel-title">Legal</div>
            <ul className="mt-3 space-y-2 text-[13px] text-dim">
              <li><Link className="hover:text-[var(--text)]" href="/legal#mentions">Mentions légales</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/legal#privacy">Privacy policy</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/legal#terms">Terms of service</Link></li>
              <li><Link className="hover:text-[var(--text)]" href="/legal#security">Security</Link></li>
            </ul>
          </div>
        </div>

        <div className="divider my-10" />

        <div className="flex flex-col gap-4 text-[11.5px] text-mute sm:flex-row sm:items-center sm:justify-between">
          <p>© {new Date().getFullYear()} Compliance OS. All rights reserved.</p>
          <p className="max-w-xl leading-relaxed">
            Compliance OS provides readiness assessment and evidence automation
            software. It is not a DGSSI-qualified cybersecurity service provider,
            and nothing on this site is legal advice.
          </p>
        </div>
      </div>
    </footer>
  );
}
