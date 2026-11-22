const TOKEN_KEY = "compliance_token";
const CLIENT_KEY = "compliance_client_id";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string | null) {
  if (typeof window === "undefined") return;
  if (token) window.localStorage.setItem(TOKEN_KEY, token);
  else {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(CLIENT_KEY);
  }
}

export function getSelectedClient(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(CLIENT_KEY) || "";
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const res = await fetch(path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers || {}),
    },
  });
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  let body: any = null;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  if (!res.ok) {
    const detail = body?.detail ?? body?.message ?? res.statusText;
    throw new ApiError(
      res.status,
      typeof detail === "string" ? detail : JSON.stringify(detail),
    );
  }
  return body as T;
}

/** Authenticated binary download (dossier, exports). */
export async function download(path: string, filename: string) {
  const token = getToken();
  const res = await fetch(path, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new ApiError(res.status, "Download failed");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// --------------------------------------------------------------------- types
export type Score = {
  framework_id: string;
  framework_name: string;
  pct: number;
  verdict: string;
  applicable: number;
  gaps: number;
  partials: number;
  unassessed: number;
  excluded: number;
};

export type ClientRow = {
  id: string;
  slug: string;
  legal_name: string;
  sector: string;
  headcount: string;
  rc: string;
  ice: string;
  created_at: string;
};

export type MonitorResult = {
  check_id: string;
  title: string;
  outcome: string;
  severity: string;
  observed: unknown;
  message: string;
  drift: string;
  controls: string[];
};

export type MonitorRun = {
  fingerprint: string;
  score: number;
  counts: Record<string, number>;
  sources: string[];
  started_at: string;
  finished_at: string;
  results: MonitorResult[];
};

export type AgentCitation = { kind: string; ref: string; label: string };

export type AgentAnswer = {
  text: string;
  citations: AgentCitation[];
  intent: string;
  grounded: boolean;
  follow_ups: string[];
  used_llm: boolean;
};

export const apiClient = {
  register: (tenant_name: string, email: string, password: string) =>
    api<{ access_token: string; role: string; email: string; tenant_id: string }>(
      "/api/auth/register",
      { method: "POST", body: JSON.stringify({ tenant_name, email, password }) },
    ),
  login: (email: string, password: string, totp_code?: string) =>
    api<{ access_token: string; role: string; email: string; tenant_id: string; totp_required: boolean }>(
      "/api/auth/login",
      { method: "POST", body: JSON.stringify({ email, password, totp_code }) },
    ),
  me: () =>
    api<{ id: string; email: string; role: string; tenant_name: string; totp_enabled: boolean }>(
      "/api/auth/me",
    ),
  clients: () => api<ClientRow[]>("/api/clients"),
  scores: (clientId: string) => api<Score[]>(`/api/clients/${clientId}/score`),
  latestMonitor: (clientId: string) =>
    api<MonitorRun>(`/api/clients/${clientId}/monitor/latest`),
  runMonitor: (clientId: string) =>
    api<MonitorRun>(`/api/clients/${clientId}/monitor/run`, { method: "POST" }),
  checks: () =>
    api<{ id: string; title: string; source: string; severity: string; remediation: string }[]>(
      "/api/checks",
    ),
  ask: (clientId: string, question: string, polish = false) =>
    api<AgentAnswer>(`/api/clients/${clientId}/agent/ask`, {
      method: "POST",
      body: JSON.stringify({ question, polish }),
    }),
  agentSuggestions: () =>
    api<{ suggestions: string[] }>("/api/agent/suggestions"),
  agentContext: (clientId: string) =>
    api<Record<string, unknown>>(`/api/clients/${clientId}/agent/context`),
};
