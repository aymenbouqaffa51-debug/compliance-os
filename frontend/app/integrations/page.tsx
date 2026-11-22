"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { Badge } from "@/components/ui/Badge";
import { Empty } from "@/components/ui/Empty";
import { api, getSelectedClient, ApiError } from "@/lib/api";
import { IconPlug, IconCheck, IconAlert, IconShield } from "@/components/ui/Icons";

type Integration = {
  provider: string;
  config: Record<string, unknown>;
  created_at: string;
  last_used_at: string | null;
};

const PROVIDERS = [
  {
    id: "github",
    label: "GitHub",
    configHint: '{"org": "your-org"}',
    permissions: "Fine-grained PAT, read-only: Administration, Members, Code scanning.",
    checks: "org 2FA, branch protection, secret scanning, Dependabot ageing, outside collaborators",
  },
  {
    id: "aws",
    label: "Amazon Web Services",
    configHint: '{"region": "eu-west-3"}',
    permissions: "IAM user with the AWS-managed SecurityAudit policy. Read-only by construction.",
    checks: "root MFA, root keys, S3 public access, CloudTrail, RDS/EBS encryption, open SSH/RDP, GuardDuty",
  },
  {
    id: "workspace",
    label: "Google Workspace",
    configHint: '{"domain": "yourcompany.com"}',
    permissions: "Service-account key with domain-wide delegation, read-only directory scopes.",
    checks: "2-step verification enrolment, suspended user hygiene",
  },
];

export default function IntegrationsPage() {
  const router = useRouter();
  const [clientId, setClientId] = useState("");
  const [existing, setExisting] = useState<Integration[]>([]);
  const [provider, setProvider] = useState("github");
  const [secret, setSecret] = useState("");
  const [configText, setConfigText] = useState('{"org": ""}');
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

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

  const load = useCallback(async () => {
    if (!clientId) return;
    try {
      setExisting(await api<Integration[]>(`/api/clients/${clientId}/integrations`));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) router.push("/login");
      else setExisting([]);
    }
  }, [clientId, router]);

  useEffect(() => { load(); }, [load]);

  function pickProvider(id: string) {
    setProvider(id);
    setMsg("");
    setError("");
    const p = PROVIDERS.find((x) => x.id === id);
    setConfigText(p?.configHint || "{}");
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMsg("");
    let config: Record<string, unknown> = {};
    try {
      config = JSON.parse(configText || "{}");
    } catch {
      setError("Config must be valid JSON.");
      return;
    }
    if (!secret.trim()) {
      setError("Enter the credential.");
      return;
    }
    setSaving(true);
    try {
      await api(`/api/clients/${clientId}/integrations`, {
        method: "POST",
        body: JSON.stringify({ provider, secret, config }),
      });
      setSecret("");
      setMsg(`${provider} saved. The credential is encrypted at rest and never returned by the API.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function remove(p: string) {
    setError("");
    try {
      await api(`/api/clients/${clientId}/integrations/${p}`, { method: "DELETE" });
      setMsg(`${p} removed.`);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Remove failed");
    }
  }

  const current = PROVIDERS.find((p) => p.id === provider)!;

  return (
    <AppShell>
      <div className="mb-6">
        <h1 className="h1">Integrations</h1>
        <p className="mt-1 text-[13px] text-mute">
          Read-only connections. Credentials are Fernet-encrypted at rest, never
          returned by the API, and scrubbed from logs.
        </p>
      </div>

      {msg && (
        <div className="mb-4 flex items-start gap-2 rounded-[10px] border border-[rgba(36,209,126,.28)] bg-[rgba(36,209,126,.08)] px-3.5 py-2.5 text-[12.5px] text-ok">
          <IconCheck size={14} className="mt-0.5 shrink-0" />
          <span>{msg}</span>
        </div>
      )}
      {error && (
        <div className="mb-4 flex items-start gap-2 rounded-[10px] border border-[rgba(255,92,108,.28)] bg-[rgba(255,92,108,.08)] px-3.5 py-2.5 text-[12.5px] text-bad">
          <IconAlert size={14} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        {/* form */}
        <form onSubmit={save} className="card space-y-4">
          <div>
            <div className="label">Provider</div>
            <div className="grid gap-2 sm:grid-cols-3">
              {PROVIDERS.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => pickProvider(p.id)}
                  className={`rounded-[10px] border px-3 py-2.5 text-left text-[12.5px] transition ${
                    provider === p.id
                      ? "border-[rgba(91,140,255,.45)] bg-[rgba(91,140,255,.08)] font-medium text-[var(--text)]"
                      : "border-line bg-[var(--surface)] text-dim hover:border-[#2c3444]"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="rounded-[10px] border border-line bg-[var(--bg-soft)] p-3">
            <div className="flex items-center gap-1.5 text-[11.5px] font-medium text-[#a9c2ff]">
              <IconShield size={12} /> Read-only by design
            </div>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-mute">
              {current.permissions}
            </p>
            <p className="mt-1.5 text-[11.5px] leading-relaxed text-mute">
              <span className="text-dim">Checks enabled:</span> {current.checks}
            </p>
          </div>

          <div>
            <label className="label" htmlFor="secret">Credential</label>
            <input id="secret" type="password" className="input" value={secret}
                   onChange={(e) => setSecret(e.target.value)}
                   autoComplete="off" placeholder="paste the token or key" />
            <p className="mt-1 text-[10.5px] text-mute">
              Encrypted before storage. Never logged, never returned by any endpoint.
            </p>
          </div>

          <div>
            <label className="label" htmlFor="cfg">Config (JSON, non-secret)</label>
            <textarea id="cfg" className="input font-mono text-[11.5px]" rows={3}
                      value={configText}
                      onChange={(e) => setConfigText(e.target.value)} />
          </div>

          <button className="btn-primary w-full" type="submit"
                  disabled={!clientId || saving}>
            {saving ? "Saving…" : `Connect ${current.label}`}
          </button>
        </form>

        {/* connected */}
        <div className="card">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="h2">Connected</h2>
            <span className="text-[11px] text-mute">{existing.length}</span>
          </div>
          {existing.length === 0 ? (
            <p className="py-4 text-[12px] text-mute">Nothing connected yet.</p>
          ) : (
            <ul className="space-y-2">
              {existing.map((i) => (
                <li key={i.provider}
                    className="flex items-center justify-between gap-2 rounded-[9px] border border-line bg-[var(--surface)] px-3 py-2.5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5 text-[12.5px] font-medium">
                      <IconPlug size={12} className="text-ok" />
                      {i.provider}
                    </div>
                    <div className="mt-0.5 truncate font-mono text-[10.5px] text-mute">
                      {JSON.stringify(i.config)}
                    </div>
                    {i.last_used_at && (
                      <div className="text-[10px] text-mute">
                        last used {i.last_used_at.slice(0, 10)}
                      </div>
                    )}
                  </div>
                  <button className="btn-danger shrink-0 px-2 py-1 text-[11px]"
                          onClick={() => remove(i.provider)}>
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}

          <div className="mt-4 border-t border-line pt-3">
            <div className="label">No credentials needed</div>
            <p className="text-[11.5px] leading-relaxed text-mute">
              Perimeter checks (TLS, security headers, SPF/DKIM/DMARC) run against a
              public domain with no credential at all. Set the client&apos;s domain and
              run the monitors.
            </p>
          </div>
        </div>
      </div>
    </AppShell>
  );
}
