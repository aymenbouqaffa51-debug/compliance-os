"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, apiClient, getToken, ClientRow, ApiError } from "@/lib/api";

export default function PoliciesPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [selected, setSelected] = useState("");
  const [published, setPublished] = useState<any[]>([]);
  const [available, setAvailable] = useState<any[]>([]);
  const [open, setOpen] = useState<any | null>(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [ackEmail, setAckEmail] = useState("");

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    (async () => {
      try {
        const [p, cl, av] = await Promise.all([
          apiClient.me(), apiClient.clients(), api<any[]>("/api/policies/available"),
        ]);
        setMe(p); setClients(cl); setAvailable(av);
        if (cl.length) setSelected(cl[0].id);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
      }
    })();
  }, [router]);

  const load = useCallback(async () => {
    if (!selected) return;
    try { setPublished(await api<any[]>(`/api/clients/${selected}/policies`)); }
    catch { setPublished([]); }
  }, [selected]);

  useEffect(() => { load(); setOpen(null); }, [load]);

  async function publish(policyId: string, lang: string) {
    setError(""); setMsg("");
    try {
      const r = await api<any>(`/api/clients/${selected}/policies/publish`, {
        method: "POST",
        body: JSON.stringify({ policy_id: policyId, language: lang }),
      });
      setMsg(`Published ${r.title} v${r.version}.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed");
    }
  }

  async function view(id: string) {
    try { setOpen(await api<any>(`/api/clients/${selected}/policies/${id}`)); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not load"); }
  }

  async function acknowledge() {
    if (!open || !ackEmail) return;
    setError(""); setMsg("");
    try {
      await api(`/api/clients/${selected}/policies/${open.id}/acknowledge`, {
        method: "POST",
        body: JSON.stringify({ person_email: ackEmail, method: "web" }),
      });
      setMsg(`Recorded acknowledgement from ${ackEmail}.`);
      setAckEmail("");
      await view(open.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  const current = published.filter((p) => p.is_current);

  return (
    <AppShell>
      
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-xl font-semibold">Policies</h1>
        <p className="mt-1 text-sm text-slate-400">
          Publish versioned ISMS policies and track who has acknowledged them.
          An unsigned policy is a document, not a control.
        </p>

        <div className="mt-6">
          <label className="label" htmlFor="client">Client</label>
          <select id="client" className="input max-w-sm" value={selected}
                  onChange={(e) => setSelected(e.target.value)}>
            {clients.map((c) => <option key={c.id} value={c.id}>{c.legal_name}</option>)}
          </select>
        </div>

        {msg && <p className="mt-3 text-sm text-ok">{msg}</p>}
        {error && <p className="mt-3 text-sm text-bad">{error}</p>}

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <div className="card">
            <h2 className="mb-3 text-sm font-semibold">Published</h2>
            {current.length === 0 ? (
              <p className="text-xs text-slate-500">No policy published yet.</p>
            ) : (
              <ul className="space-y-2">
                {current.map((p) => (
                  <li key={p.id} className="flex items-center justify-between border-b border-line pb-2">
                    <button className="text-left text-xs hover:underline" onClick={() => view(p.id)}>
                      <div className="font-medium text-slate-200">{p.title}</div>
                      <div className="text-slate-500">
                        v{p.version} &middot; {p.acknowledgement_count} acknowledged
                      </div>
                    </button>
                    <span className="text-[10px] uppercase text-slate-600">{p.language}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <h2 className="mb-3 text-sm font-semibold">Available templates</h2>
            <ul className="max-h-[420px] space-y-1 overflow-y-auto">
              {available.map((p) => (
                <li key={p.id} className="flex items-center justify-between border-b border-line py-1.5">
                  <span className="truncate pr-2 text-xs text-slate-300">{p.title_en}</span>
                  <span className="flex shrink-0 gap-1">
                    <button className="btn-ghost px-2 py-0.5 text-[10px]"
                            onClick={() => publish(p.id, "fr")}>FR</button>
                    <button className="btn-ghost px-2 py-0.5 text-[10px]"
                            onClick={() => publish(p.id, "en")}>EN</button>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {open && (
          <div className="card mt-6">
            <div className="mb-3 flex items-start justify-between">
              <div>
                <div className="text-sm font-semibold">{open.title}</div>
                <div className="text-xs text-slate-500">
                  v{open.version} &middot; sha256 {open.content_sha256.slice(0, 16)}&hellip;
                </div>
              </div>
              <button className="btn-ghost text-xs" onClick={() => setOpen(null)}>Close</button>
            </div>

            <div className="mb-4 flex flex-wrap items-end gap-2">
              <div className="min-w-[220px]">
                <label className="label" htmlFor="ack">Record acknowledgement</label>
                <input id="ack" type="email" className="input" placeholder="employee@company.ma"
                       value={ackEmail} onChange={(e) => setAckEmail(e.target.value)} />
              </div>
              <button className="btn-primary" onClick={acknowledge}>Acknowledge</button>
            </div>

            {open.acknowledgements?.length > 0 && (
              <div className="mb-4">
                <div className="label">Acknowledged by</div>
                <ul className="text-xs text-slate-400">
                  {open.acknowledgements.map((a: any, i: number) => (
                    <li key={i}>{a.person_email} &middot; {a.acknowledged_at.slice(0, 10)}</li>
                  ))}
                </ul>
              </div>
            )}

            <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap rounded-lg border border-line bg-ink p-4 text-[11px] leading-relaxed text-slate-400">
              {open.body}
            </pre>
          </div>
        )}
      </main>
    </AppShell>
  );
}
