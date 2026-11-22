"use client";

import Link from "next/link";
import { useState } from "react";
import { IconShield, IconArrowRight } from "@/components/ui/Icons";

const LINKS = [
  { href: "#frameworks", label: "Frameworks" },
  { href: "#product", label: "Product" },
  { href: "#agent", label: "Agent" },
  { href: "#pricing", label: "Pricing" },
];

export function MarketingNav() {
  const [open, setOpen] = useState(false);

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-[var(--bg)]/75 backdrop-blur-md">
      <div className="shell flex items-center justify-between py-3.5">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-[#6b96ff] to-[#8b5cf6] text-white">
            <IconShield size={16} />
          </span>
          <span className="text-[14px] font-semibold tracking-tight">
            Compliance OS
          </span>
        </Link>

        <nav className="hidden items-center gap-7 text-[13px] text-dim md:flex">
          {LINKS.map((l) => (
            <a key={l.href} href={l.href} className="transition hover:text-[var(--text)]">
              {l.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-2.5 md:flex">
          <Link href="/login" className="btn-ghost">
            Sign in
          </Link>
          <Link href="/login" className="btn-primary">
            Start free
            <IconArrowRight size={13} />
          </Link>
        </div>

        <button
          aria-label="Toggle menu"
          className="flex h-9 w-9 items-center justify-center rounded-[10px] border border-line text-dim md:hidden"
          onClick={() => setOpen((v) => !v)}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {open ? <path d="M6 6l12 12M18 6L6 18" /> : <path d="M3 6h18M3 12h18M3 18h18" />}
          </svg>
        </button>
      </div>

      {open && (
        <div className="border-t border-line bg-[var(--surface)] px-5 py-4 md:hidden">
          <nav className="flex flex-col gap-4 text-[13px] text-dim">
            {LINKS.map((l) => (
              <a key={l.href} href={l.href} onClick={() => setOpen(false)} className="hover:text-[var(--text)]">
                {l.label}
              </a>
            ))}
            <div className="mt-2 flex flex-col gap-2 border-t border-line pt-4">
              <Link href="/login" className="btn-ghost justify-center" onClick={() => setOpen(false)}>
                Sign in
              </Link>
              <Link href="/login" className="btn-primary justify-center" onClick={() => setOpen(false)}>
                Start free
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}
