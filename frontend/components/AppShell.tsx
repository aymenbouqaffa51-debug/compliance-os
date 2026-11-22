"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { apiClient, getToken, setToken, ApiError } from "@/lib/api";
import {
  IconGauge, IconPulse, IconPlug, IconDoc, IconClipboard,
  IconSparkles, IconShield, IconLogout,
} from "@/components/ui/Icons";
import { AgentPanel } from "@/components/agent/AgentPanel";

const NAV = [
  { href: "/dashboard", label: "Readiness", icon: IconGauge },
  { href: "/monitors", label: "Monitors", icon: IconPulse },
  { href: "/questionnaires", label: "Questionnaires", icon: IconClipboard },
  { href: "/policies", label: "Policies", icon: IconDoc },
  { href: "/integrations", label: "Integrations", icon: IconPlug },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [clients, setClients] = useState<any[]>([]);
  const [clientId, setClientId] = useState<string>("");
  const [agentOpen, setAgentOpen] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    (async () => {
      try {
        const [profile, list] = await Promise.all([apiClient.me(), apiClient.clients()]);
        setMe(profile);
        setClients(list);
        const saved = typeof window !== "undefined"
          ? window.localStorage.getItem("compliance_client_id") : null;
        const pick = list.find((c: any) => c.id === saved)?.id || list[0]?.id || "";
        setClientId(pick);
        if (pick) window.localStorage.setItem("compliance_client_id", pick);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
      } finally {
        setReady(true);
      }
    })();
  }, [router]);

  function chooseClient(id: string) {
    setClientId(id);
    window.localStorage.setItem("compliance_client_id", id);
    window.dispatchEvent(new CustomEvent("compliance:client-changed", { detail: id }));
  }

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <div className="flex items-center gap-2 text-[13px] text-mute">
          <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" />
          Loading workspace
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      {/* ---- sidebar ---- */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-line bg-[var(--bg-soft)]/80 backdrop-blur lg:flex">
        <div className="flex items-center gap-2.5 px-5 py-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-[10px] bg-gradient-to-br from-[#6b96ff] to-[#8b5cf6] text-white">
            <IconShield size={17} />
          </span>
          <div className="leading-tight">
            <div className="text-[13.5px] font-semibold tracking-tight">Compliance OS</div>
            <div className="text-[10.5px] text-mute">evidence automation</div>
          </div>
        </div>

        <nav className="mt-1 flex-1 space-y-0.5 px-3">
          {NAV.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname?.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                className={`flex items-center gap-2.5 rounded-[9px] px-3 py-2 text-[13px] transition ${
                  active
                    ? "bg-white/[.06] font-medium text-[var(--text)]"
                    : "text-dim hover:bg-white/[.03] hover:text-[var(--text)]"
                }`}
              >
                <Icon size={15} className={active ? "text-[#a9c2ff]" : "text-mute"} />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="px-3 pb-3">
          <button
            onClick={() => setAgentOpen(true)}
            className="group flex w-full items-center gap-2.5 rounded-[9px] border border-[rgba(91,140,255,.22)] bg-[rgba(91,140,255,.08)] px-3 py-2.5 text-left text-[13px] transition hover:bg-[rgba(91,140,255,.13)]"
          >
            <IconSparkles size={15} className="text-[#a9c2ff]" />
            <span className="flex-1 font-medium text-[#c4d6ff]">Ask the agent</span>
            <kbd className="rounded border border-line bg-black/30 px-1.5 py-0.5 font-mono text-[10px] text-mute">
              K
            </kbd>
          </button>
        </div>

        <div className="border-t border-line px-4 py-3">
          <div className="truncate text-[11.5px] text-dim">{me?.email}</div>
          <div className="mt-0.5 flex items-center gap-2">
            <span className="pill border-line bg-white/[.04] text-[10px] text-mute">
              {me?.role?.replace(/_/g, " ")}
            </span>
            <button
              onClick={() => { setToken(null); router.push("/login"); }}
              className="ml-auto text-mute transition hover:text-[var(--bad)]"
              title="Sign out"
            >
              <IconLogout size={14} />
            </button>
          </div>
        </div>
      </aside>

      {/* ---- main ---- */}
      <div className="lg:pl-[232px]">
        <header className="sticky top-0 z-20 border-b border-line bg-[var(--bg)]/80 backdrop-blur">
          <div className="flex h-[57px] items-center gap-3 px-5 sm:px-7">
            <div className="flex items-center gap-2 lg:hidden">
              <IconShield size={17} className="text-[#a9c2ff]" />
              <span className="text-[13px] font-semibold">Compliance OS</span>
            </div>
            <div className="ml-auto flex items-center gap-2.5">
              {clients.length > 0 && (
                <div className="relative">
                  <select
                    value={clientId}
                    onChange={(e) => chooseClient(e.target.value)}
                    className="input h-8 min-w-[190px] cursor-pointer appearance-none pr-8 text-[12.5px]"
                  >
                    {clients.map((c) => (
                      <option key={c.id} value={c.id}>{c.legal_name}</option>
                    ))}
                  </select>
                  <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-mute">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="m8 10 4 4 4-4" />
                    </svg>
                  </span>
                </div>
              )}
              <button
                onClick={() => setAgentOpen(true)}
                className="btn-primary h-8 px-3 text-[12.5px] lg:hidden"
              >
                <IconSparkles size={14} /> Agent
              </button>
            </div>
          </div>
        </header>

        <main className="px-5 py-7 sm:px-7">{children}</main>
      </div>

      {agentOpen && (
        <AgentPanel
          clientId={clientId}
          clientName={clients.find((c) => c.id === clientId)?.legal_name || ""}
          onClose={() => setAgentOpen(false)}
        />
      )}
    </div>
  );
}
