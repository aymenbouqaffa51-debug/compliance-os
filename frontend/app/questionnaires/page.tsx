"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { api, apiClient, getToken, ClientRow, ApiError } from "@/lib/api";

type Answer = {
  row: number;
  question: string;
  reference: string;
  matched_controls: string[];
  frameworks: string[];
  state: string;
  confidence: string;
  review_flag: string;
  review_reason: string;
  draft: string;
  evidence_refs: string[];
};

type Detail = {
  id: string;
  name: string;
  source_file: string;
  total_questions: number;
  counts: Record<string, number>;
  answers: Answer[];
  status: string;
};

const CONF_STYLE: Record<string, string> = {
  high: "text-ok",
  medium: "text-warn",
  low: "text-bad",
};

export default function QuestionnairesPage() {
  const router = useRouter();
  const [me, setMe] = useState<any>(null);
  const [clients, setClients] = useState<ClientRow[]>([]);
  const [selected, setSelected] = useState("");
  const [list, setList] = useState<any[]>([]);
  const [detail, setDetail] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftText, setDraftText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!getToken()) { router.push("/login"); return; }
    (async () => {
      try {
        const [profile, cl] = await Promise.all([apiClient.me(), apiClient.clients()]);
        setMe(profile);
        setClients(cl);
        if (cl.length) setSelected(cl[0].id);
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) router.push("/login");
      }
    })();
  }, [router]);

  const loadList = useCallback(async () => {
    if (!selected) return;
    try {
      const rows = await api<any[]>(`/api/clients/${selected}/questionnaires`);
      setList(rows);
    } catch { setList([]); }
  }, [selected]);

  useEffect(() => { loadList(); setDetail(null); }, [loadList]);

  async function upload() {
    const f = fileRef.current?.files?.[0];
    if (!f || !selected) return;
    setBusy(true);
    setError("");
    try {
      const fd = new FormData();
      fd.append("file", f);
      fd.append("name", f.name.replace(/\.[^.]+$/, ""));
      const token = getToken();
      const res = await fetch(`/api/clients/${selected}/questionnaires/upload`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: fd,
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.detail || "Upload failed");
      await loadList();
      setDetail(await api<Detail>(`/api/clients/${selected}/questionnaires/${body.id}`));
      if (fileRef.current) fileRef.current.value = "";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function open(id: string) {
    setError("");
    try {
      setDetail(await api<Detail>(`/api/clients/${selected}/questionnaires/${id}`));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open");
    }
  }

  async function saveEdit(row: number) {
    if (!detail) return;
    try {
      const res = await api<{ answers: Answer[]; counts: Record<string, number> }>(
        `/api/clients/${selected}/questionnaires/${detail.id}/answers`,
        { method: "PATCH", body: JSON.stringify({ row, draft: draftText }) },
      );
      setDetail({ ...detail, answers: res.answers, counts: res.counts });
      setEditing(null);
      await loadList();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    }
  }

  function exportAs(fmt: "md" | "csv") {
    if (!detail) return;
    const token = getToken();
    fetch(`/api/clients/${selected}/questionnaires/${detail.id}/export?fmt=${fmt}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => r.blob())
      .then((blob) => {
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `questionnaire-${detail.id.slice(0, 8)}.${fmt}`;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch(() => setError("Export failed"));
  }

  return (
    <AppShell>
      
      <main className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="text-xl font-semibold">Questionnaires</h1>
        <p className="mt-1 text-sm text-slate-400">
          Upload a buyer&apos;s security questionnaire. Answers are drafted from your
          recorded control state &mdash; never invented.
        </p>

        <div className="mt-6 flex flex-wrap items-end gap-3">
          <div className="min-w-[220px]">
            <label className="label" htmlFor="client">Client</label>
            <select id="client" className="input" value={selected}
                    onChange={(e) => setSelected(e.target.value)}>
              {clients.map((c) => <option key={c.id} value={c.id}>{c.legal_name}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="file">CSV or XLSX</label>
            <input id="file" ref={fileRef} type="file" accept=".csv,.xlsx,.xlsm,.txt"
                   className="input file:mr-3 file:rounded file:border-0 file:bg-line file:px-3 file:py-1 file:text-slate-200" />
          </div>
          <button className="btn-primary" onClick={upload} disabled={busy || !selected}>
            {busy ? "Drafting..." : "Upload & draft"}
          </button>
        </div>

        {error && <p className="mt-3 text-sm text-bad">{error}</p>}

        <div className="mt-6 grid gap-5 lg:grid-cols-[280px_1fr]">
          <div className="card">
            <h2 className="mb-3 text-sm font-semibold">Uploaded</h2>
            {list.length === 0 ? (
              <p className="text-xs text-slate-500">Nothing uploaded yet.</p>
            ) : (
              <ul className="space-y-2">
                {list.map((q) => (
                  <li key={q.id}>
                    <button onClick={() => open(q.id)}
                            className={`w-full rounded-lg border border-line px-3 py-2 text-left text-xs hover:bg-line ${detail?.id === q.id ? "bg-line" : ""}`}>
                      <div className="truncate font-medium text-slate-200">{q.name || q.source_file}</div>
                      <div className="mt-1 text-slate-500">
                        {q.total_questions} questions
                        {q.counts?.needs_review > 0 && (
                          <span className="ml-2 text-warn">{q.counts.needs_review} to review</span>
                        )}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            {!detail ? (
              <div className="card">
                <p className="text-sm text-slate-400">
                  Select an upload to inspect the drafted answers.
                </p>
              </div>
            ) : (
              <>
                <div className="card mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold">{detail.name}</div>
                    <div className="text-xs text-slate-500">
                      {detail.total_questions} questions &middot;{" "}
                      <span className="text-ok">{detail.counts.high || 0} high</span> &middot;{" "}
                      <span className="text-warn">{detail.counts.needs_review || 0} need review</span>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button className="btn-ghost text-xs" onClick={() => exportAs("md")}>Export MD</button>
                    <button className="btn-ghost text-xs" onClick={() => exportAs("csv")}>Export CSV</button>
                  </div>
                </div>

                <div className="space-y-3">
                  {detail.answers.map((a) => (
                    <div key={a.row} className="card">
                      <div className="flex items-start justify-between gap-3">
                        <div className="text-sm text-slate-200">
                          <span className="mr-2 text-xs text-slate-500">#{a.row}</span>
                          {a.question}
                        </div>
                        <div className="shrink-0 text-right">
                          <span className={`text-[11px] font-medium ${CONF_STYLE[a.confidence] || "text-slate-400"}`}>
                            {a.confidence.toUpperCase()}
                          </span>
                          {a.review_flag && (
                            <div className="mt-1 rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 text-[10px] text-warn">
                              REVIEW
                            </div>
                          )}
                        </div>
                      </div>

                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                        {a.matched_controls.length > 0 && (
                          <span>controls: {a.matched_controls.slice(0, 4).join(", ")}</span>
                        )}
                        {a.state && <span>state: {a.state}</span>}
                        {a.review_reason && <span className="text-warn">{a.review_reason}</span>}
                      </div>

                      {editing === a.row ? (
                        <div className="mt-3">
                          <textarea className="input text-xs" rows={3} value={draftText}
                                    onChange={(e) => setDraftText(e.target.value)} />
                          <div className="mt-2 flex gap-2">
                            <button className="btn-primary text-xs" onClick={() => saveEdit(a.row)}>Save</button>
                            <button className="btn-ghost text-xs" onClick={() => setEditing(null)}>Cancel</button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <p className="mt-3 whitespace-pre-wrap text-xs leading-relaxed text-slate-300">
                            {a.draft || <span className="text-slate-500">(no draft &mdash; answer manually)</span>}
                          </p>
                          <button className="mt-2 text-[11px] text-accent hover:underline"
                                  onClick={() => { setEditing(a.row); setDraftText(a.draft); }}>
                            Edit answer
                          </button>
                        </>
                      )}

                      {a.evidence_refs.length > 0 && (
                        <div className="mt-2 border-t border-line pt-2 text-[11px] text-slate-500">
                          evidence: {a.evidence_refs.slice(0, 2).join("; ")}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </AppShell>
  );
}
