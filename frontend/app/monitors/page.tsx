"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/Badge";
import { Metric } from "@/components/ui/Metric";
import { Empty } from "@/components/ui/Empty";
import { Bar } from "@/components/ui/Bar";
import { apiClient, getSelectedClient, ApiError, MonitorRun } from "@/lib/api";
import { IconPulse, IconRefresh, IconAlert, IconCheck } from "@/components/ui/Icons";

type Filter = "all" | "FAIL" | "PASS" | "OTHER";

export default function MonitorsPage() {
  const router = useRouter();
  const [clientId, setClientId] = useState("");
  const [run, setRun] = useState<MonitorRun | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");

  useEffect(() => {
    function sync() { setClientId(getSelectedClient()); }
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

  const loadLatest = useCallback(async () => {
    if (!clientId) return;
    try {
      setRun(await apiClient.latestMonitor(clientId));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setRun(null);
    }
  }, [clientId, router]);

  useEffect(() => { loadLatest(); }, [loadLatest]);

  async function runNow() {
    if (!clientId) return;
    setBusy(true);
    setError("");
    try {
      setRun(await apiClient.runMonitor(clientId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Monitor run failed");
    } finally {
      setBusy(false);
    }
  }

  const results = run?.results ?? [];
  const passing = results.filter((r) => r.outcome === "PASS").length;
  const failing = results.filter((r) => r.outcome === "FAIL").length;
  const drift = results.filter((r) => r.drift).length;
  const na = results.filter((r) => r.outcome === "NOT_APPLICABLE").length;

  const visible = results.filter((r) => {
    if (filter === "all") return true;
    if (filter === "FAIL") return r.outcome === "FAIL";
    if (filter === "PASS") return r.outcome === "PASS";
    return r.outcome !== "PASS" && r.outcome !== "FAIL";
  });

  return (
    <AppShell>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="h1">Continuous monitors</h1>
          <p className="mt-1 text-[13px] text-mute">
            Read-only checks against your perimeter, identity and cloud posture.
            A check result is an observation — the control verdict is your call.
          </p>
        </div>
        <button className="btn-primary" onClick={runNow} disabled={busy || !clientId}>
          <IconRefresh size={14} />
          {busy ? "Running…" : "Run checks"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-[10px] border border-[rgba(255,92,108,.28)] bg-[rgba(255,92,108,.08)] px-3.5 py-2.5 text-[12.5px] text-bad">
          {error}
        </div>
      )}

      {!run ? (
        <Empty
          icon={<IconPulse size={22} />}
          title="No monitoring run yet"
          body="Add a domain or an integration, then run the checks. Perimeter checks need no credentials at all."
          action={<button className="btn-primary" onClick={runNow} disabled={busy || !clientId}>
            {busy ? "Running…" : "Run first check"}
          </button>}
        />
      ) : (
        <>
          <div className="grid gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
            <Metric label="Score" value={`${run.score.toFixed(1)}%`}
                    tone={run.score >= 80 ? "ok" : run.score >= 50 ? "warn" : "bad"}
                    hint="decisive checks only" icon={<IconPulse size={14} />} />
            <Metric label="Passing" value={passing} tone="ok"
                    hint="observed as expected" icon={<IconCheck size={14} />} />
            <Metric label="Failing" value={failing} tone={failing ? "bad" : "ok"}
                    hint={failing ? "needs attention" : "nothing failing"}
                    icon={<IconAlert size={14} />} />
            <Metric label="Drift" value={drift} tone={drift ? "warn" : "ok"}
                    hint={drift ? "regressions since last run" : "no regressions"}
                    icon={<IconRefresh size={14} />} />
          </div>

          <div className="mt-3.5 card">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-3 text-[11.5px] text-mute">
                <span>{run.sources.length} source(s): {run.sources.join(", ") || "none"}</span>
                <span className="hidden font-mono text-[10.5px] sm:inline">
                  {run.fingerprint.slice(0, 16)}…
                </span>
                <span>{run.finished_at?.replace("T", " ").slice(0, 16)}</span>
              </div>
              {na > 0 && (
                <span className="text-[11px] text-mute">{na} not applicable</span>
              )}
            </div>
            <div className="mt-2.5">
              <Bar pct={results.length ? (passing / Math.max(1, passing + failing)) * 100 : 0}
                   tone={failing ? "warn" : "ok"} />
            </div>
          </div>

          <div className="mt-4 mb-3 flex flex-wrap gap-1.5">
            {(["all", "FAIL", "PASS", "OTHER"] as const).map((f) => (
              <button key={f}
                      className={filter === f ? "btn-primary h-8 px-3 text-[12px]" : "btn-ghost h-8 px-3 text-[12px]"}
                      onClick={() => setFilter(f)}>
                {f === "all" ? `All ${results.length}`
                  : f === "FAIL" ? `Failing ${failing}`
                  : f === "PASS" ? `Passing ${passing}`
                  : `No opinion ${na}`}
              </button>
            ))}
          </div>

          <div className="card overflow-hidden p-0">
            <div className="overflow-x-auto">
              <table className="table">
                <thead>
                  <tr>
                    <th className="px-4">Check</th>
                    <th>Status</th>
                    <th>Severity</th>
                    <th>Observed</th>
                    <th className="pr-4">Controls</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((r) => (
                    <tr key={r.check_id}>
                      <td className="px-4">
                        <div className="font-medium">{r.title}</div>
                        <div className="mt-0.5 font-mono text-[10.5px] text-mute">
                          {r.check_id}
                        </div>
                        {r.drift && (
                          <div className="mt-1 text-[10.5px] text-warn">
                            drift: {r.drift}
                          </div>
                        )}
                      </td>
                      <td><Badge value={r.outcome} /></td>
                      <td className="text-[11.5px] text-mute">{r.severity}</td>
                      <td className="max-w-[240px] truncate font-mono text-[11px] text-dim">
                        {r.observed === null || r.observed === undefined
                          ? "—"
                          : typeof r.observed === "object"
                          ? JSON.stringify(r.observed)
                          : String(r.observed)}
                      </td>
                      <td className="pr-4 text-[11px] text-mute">
                        {r.controls.slice(0, 3).join(", ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {visible.length === 0 && (
              <div className="py-10 text-center text-[12.5px] text-mute">
                No checks in this filter.
              </div>
            )}
          </div>

          <p className="mt-4 text-[10.5px] leading-relaxed text-mute">
            A failing check means the observed fact differs from the expected value.
            It is evidence for a human decision, not an automatic control failure.
          </p>
        </>
      )}
    </AppShell>
  );
}
