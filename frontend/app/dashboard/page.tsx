"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Metric } from "@/components/ui/Metric";
import { ScoreRing } from "@/components/ui/ScoreRing";
import { Bar } from "@/components/ui/Bar";
import { Badge } from "@/components/ui/Badge";
import { Empty } from "@/components/ui/Empty";
import { api, apiClient, download, getToken, Score, ApiError } from "@/lib/api";
import {
  IconGauge, IconAlert, IconDownload, IconSparkles, IconShield,
  IconArrowRight, IconPulse,
} from "@/components/ui/Icons";

export default function DashboardPage() {
  const router = useRouter();
  const [clientId, setClientId] = useState("");
  const [scores, setScores] = useState<Score[]>([]);
  const [agentContext, setAgentContext] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [exporting, setExporting] = useState(false);

  // AppShell owns the client selector; listen for its change event.
  useEffect(() => {
    function sync() {
      const id = window.localStorage.getItem("compliance_client_id") || "";
      setClientId(id);
    }
    sync();
    window.addEventListener("compliance:client-changed", sync);
    window.addEventListener("storage", sync);
    const t = setTimeout(sync, 400);
    return () => {
      window.removeEventListener("compliance:client-changed", sync);
      window.removeEventListener("storage", sync);
      clearTimeout(t);
    };
  }, []);

  const load = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    setError("");
    try {
      const [s, ctx] = await Promise.all([
        apiClient.scores(clientId),
        apiClient.agentContext(clientId).catch(() => null),
      ]);
      setScores(s);
      setAgentContext(ctx);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setError(e instanceof Error ? e.message : "Failed to load");
    } finally {
      setLoading(false);
    }
  }, [clientId, router]);

  useEffect(() => { load(); }, [load]);

  async function exportDossier() {
    if (!clientId) return;
    setExporting(true);
    try {
      await download(
        `/api/clients/${clientId}/audit-dossier`,
        `audit-dossier-${new Date().toISOString().slice(0, 10)}.zip`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setExporting(false);
    }
  }

  const totalGaps = scores.reduce((n, s) => n + s.gaps, 0);
  const totalUnassessed = scores.reduce((n, s) => n + s.unassessed, 0);
  const worst = scores.length
    ? scores.reduce((a, b) => (a.pct < b.pct ? a : b))
    : null;
  const monitorScore = agentContext?.monitor_score ?? null;

  return (
    <AppShell>
      {/* header */}
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1">Readiness</h1>
          <p className="mt-1 text-[13px] text-mute">
            Position against each framework, from your recorded control state.
          </p>
        </div>
        <button className="btn-ghost" onClick={exportDossier}
                disabled={!clientId || exporting}>
          <IconDownload size={14} />
          {exporting ? "Building…" : "Export audit dossier"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-[10px] border border-[rgba(255,92,108,.28)] bg-[rgba(255,92,108,.08)] px-3.5 py-2.5 text-[12.5px] text-bad">
          {error}
        </div>
      )}

      {loading ? (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="metric h-[104px] shimmer" />
          ))}
        </div>
      ) : !clientId ? (
        <Empty
          icon={<IconShield size={22} />}
          title="No client selected"
          body="Create a client to start assessing controls. Everything on this page is scoped to one client."
        />
      ) : (
        <>
          {/* metric row */}
          <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            <Metric
              label="Open gaps"
              value={totalGaps}
              tone={totalGaps ? "bad" : "ok"}
              hint={totalGaps ? "controls recorded as gaps" : "no gaps recorded"}
              icon={<IconAlert size={14} />}
            />
            <Metric
              label="Not assessed"
              value={totalUnassessed}
              tone={totalUnassessed ? "warn" : "ok"}
              hint="unknown is not the same as passing"
              icon={<IconGauge size={14} />}
            />
            <Metric
              label="Monitor score"
              value={monitorScore === null ? "—" : `${monitorScore.toFixed(1)}%`}
              tone={monitorScore === null ? "neutral" : monitorScore >= 80 ? "ok" : monitorScore >= 50 ? "warn" : "bad"}
              hint={monitorScore === null ? "no run yet" : "technical checks"}
              icon={<IconPulse size={14} />}
            />
            <Metric
              label="Weakest"
              value={worst ? `${worst.pct.toFixed(0)}%` : "—"}
              hint={worst ? worst.framework_name : "no assessment"}
              icon={<IconShield size={14} />}
            />
          </div>

          {/* frameworks */}
          <div className="mt-6">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="h2">By framework</h2>
              <span className="text-[11.5px] text-mute">
                {scores.reduce((n, s) => n + s.applicable, 0)} applicable controls
              </span>
            </div>

            <div className="grid gap-3.5 sm:grid-cols-2 xl:grid-cols-4">
              {scores.map((s) => (
                <div key={s.framework_id} className="card card-hover">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate text-[12.5px] font-medium">
                        {s.framework_name}
                      </div>
                      <div className="mt-0.5 text-[11px] text-mute">{s.verdict}</div>
                    </div>
                    <ScoreRing pct={s.pct} size={54} stroke={5} />
                  </div>
                  <div className="mt-3">
                    <Bar pct={s.pct} tone={s.pct >= 90 ? "ok" : s.pct >= 40 ? "warn" : "bad"} />
                  </div>
                  <div className="mt-2.5 flex flex-wrap gap-1.5">
                    {s.gaps > 0 && <Badge value="gap" label={`${s.gaps} gap`} />}
                    {s.partials > 0 && <Badge value="partial" label={`${s.partials} partial`} />}
                    {s.unassessed > 0 && <Badge value="not_assessed" label={`${s.unassessed} n/a`} />}
                    {s.gaps === 0 && s.partials === 0 && s.unassessed === 0 && (
                      <Badge value="implemented" label="complete" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* agent nudge + gaps table */}
          <div className="mt-6 grid gap-3.5 lg:grid-cols-[1fr_320px]">
            <div className="card overflow-hidden p-0">
              <div className="flex items-center justify-between border-b border-line px-4 py-3">
                <h2 className="h2">Remediation queue</h2>
                <span className="text-[11.5px] text-mute">weighted, heaviest first</span>
              </div>
              <div className="overflow-x-auto">
                <table className="table">
                  <thead>
                    <tr>
                      <th className="px-4">Framework</th>
                      <th>Score</th>
                      <th>Gaps</th>
                      <th>Partial</th>
                      <th className="pr-4">Verdict</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.map((s) => (
                      <tr key={s.framework_id}>
                        <td className="px-4 font-medium">{s.framework_name}</td>
                        <td className="tabular-nums">{s.pct.toFixed(1)}%</td>
                        <td className={s.gaps ? "text-bad tabular-nums" : "text-mute"}>
                          {s.gaps}
                        </td>
                        <td className={s.partials ? "text-warn tabular-nums" : "text-mute"}>
                          {s.partials}
                        </td>
                        <td className="pr-4 text-dim">{s.verdict}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card flex flex-col justify-between bg-gradient-to-br from-[rgba(91,140,255,.07)] to-transparent">
              <div>
                <div className="mb-2 flex h-8 w-8 items-center justify-center rounded-[9px] border border-[rgba(91,140,255,.25)] bg-[rgba(91,140,255,.10)] text-[#a9c2ff]">
                  <IconSparkles size={15} />
                </div>
                <div className="text-[13px] font-medium">Ask what to fix first</div>
                <p className="mt-1 text-[12px] leading-relaxed text-mute">
                  The agent ranks your gaps by weight and by what blocks a buyer,
                  then cites each control it used.
                </p>
              </div>
              <button
                className="btn-ghost mt-3 w-full justify-between"
                onClick={() => {
                  window.dispatchEvent(new KeyboardEvent("keydown", { key: "k" }));
                  document.querySelector<HTMLButtonElement>("button[title='Ask the agent']")?.click();
                }}
              >
                Open agent
                <IconArrowRight size={13} />
              </button>
            </div>
          </div>

          <p className="mt-6 border-t border-line pt-4 text-[10.5px] leading-relaxed text-mute">
            Readiness percentages are computed from your recorded control state and are a
            planning signal, not an auditor&apos;s opinion. Controls marked not-applicable are
            excluded from the denominator. This platform does not issue certifications.
          </p>
        </>
      )}
    </AppShell>
  );
}
