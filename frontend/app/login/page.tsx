"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { apiClient, setToken } from "@/lib/api";
import { IconShield, IconArrowRight, IconSparkles } from "@/components/ui/Icons";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [tenant, setTenant] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [totp, setTotp] = useState("");
  const [needsTotp, setNeedsTotp] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res =
        mode === "register"
          ? await apiClient.register(tenant, email, password)
          : await apiClient.login(email, password, totp || undefined);
      setToken(res.access_token);
      router.push("/dashboard");
    } catch (err: any) {
      if (err?.status === 401 && !needsTotp && mode === "login") {
        setNeedsTotp(true);
        setError("Enter the 6-digit code from your authenticator app.");
      } else {
        setError(err?.message || "Something went wrong.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen">
      {/* left: form */}
      <div className="flex w-full flex-col justify-center px-6 py-10 sm:px-12 lg:w-[46%]">
        <div className="mx-auto w-full max-w-[352px]">
          <div className="mb-9 flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-[11px] bg-gradient-to-br from-[#6b96ff] to-[#8b5cf6] text-white">
              <IconShield size={18} />
            </span>
            <div className="leading-tight">
              <div className="text-[14px] font-semibold tracking-tight">Compliance OS</div>
              <div className="text-[10.5px] text-mute">evidence automation</div>
            </div>
          </div>

          <h1 className="text-[24px] font-semibold leading-tight tracking-tight">
            {mode === "login" ? "Sign in" : "Create your workspace"}
          </h1>
          <p className="mt-1.5 text-[13px] leading-relaxed text-dim">
            {mode === "login"
              ? "Readiness, monitoring and audit evidence in one place."
              : "One workspace, your clients, your evidence — under your control."}
          </p>

          <form onSubmit={submit} className="mt-7 space-y-3.5">
            {mode === "register" && (
              <div>
                <label className="label" htmlFor="tenant">Organisation</label>
                <input id="tenant" className="input" value={tenant} autoComplete="organization"
                       onChange={(e) => setTenant(e.target.value)} required minLength={2}
                       placeholder="Atlas Software SARL" />
              </div>
            )}
            <div>
              <label className="label" htmlFor="email">Email</label>
              <input id="email" type="email" className="input" value={email}
                     onChange={(e) => setEmail(e.target.value)} required
                     autoComplete="username" placeholder="you@company.ma" />
            </div>
            <div>
              <label className="label" htmlFor="password">Password</label>
              <input id="password" type="password" className="input" value={password}
                     onChange={(e) => setPassword(e.target.value)} required
                     minLength={10} autoComplete={mode === "register" ? "new-password" : "current-password"}
                     placeholder={mode === "register" ? "at least 10 characters" : "••••••••••"} />
            </div>
            {needsTotp && (
              <div>
                <label className="label" htmlFor="totp">Authenticator code</label>
                <input id="totp" className="input font-mono tracking-[.35em]" value={totp}
                       onChange={(e) => setTotp(e.target.value)} inputMode="numeric"
                       placeholder="000000" maxLength={6} autoComplete="one-time-code" />
              </div>
            )}

            {error && (
              <div className="rounded-[9px] border border-[rgba(255,92,108,.28)] bg-[rgba(255,92,108,.08)] px-3 py-2 text-[12px] text-bad">
                {error}
              </div>
            )}

            <button type="submit" className="btn-primary mt-1 w-full py-2.5" disabled={busy}>
              {busy ? "Working…" : mode === "login" ? "Sign in" : "Create workspace"}
              {!busy && <IconArrowRight size={14} />}
            </button>

            {mode === "register" && (
              <p className="text-center text-[11px] leading-relaxed text-mute">
                By creating a workspace you agree to the{" "}
                <a href="/legal#terms" target="_blank" className="underline hover:text-dim">Terms</a>
                {" "}and{" "}
                <a href="/legal#privacy" target="_blank" className="underline hover:text-dim">Privacy Policy</a>.
              </p>
            )}
          </form>

          <button
            className="mt-5 w-full text-center text-[12px] text-mute transition hover:text-dim"
            onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setNeedsTotp(false); }}
          >
            {mode === "login" ? "No account? Create one" : "Already have an account? Sign in"}
          </button>
        </div>
      </div>

      {/* right: proof panel */}
      <div className="relative hidden flex-1 items-center justify-center border-l border-line bg-[var(--bg-soft)] lg:flex">
        <div className="max-w-[420px] px-10">
          <div className="mb-6 flex h-10 w-10 items-center justify-center rounded-[12px] border border-[rgba(91,140,255,.25)] bg-[rgba(91,140,255,.10)] text-[#a9c2ff]">
            <IconSparkles size={18} />
          </div>
          <h2 className="text-[19px] font-semibold leading-snug tracking-tight">
            An agent that answers from your evidence — not from the internet.
          </h2>
          <p className="mt-3 text-[13px] leading-relaxed text-dim">
            Ask it what your biggest gaps are, whether a control regressed, or what a
            buyer&apos;s questionnaire is really asking. Every claim is cited to a control,
            a monitor check or a score. When the data does not support an answer, it says so.
          </p>

          <div className="mt-7 space-y-2.5">
            {[
              "Answers grounded in your control register",
              "Continuous read-only monitoring with drift alerts",
              "CNDP and Law 05-20 positions computed, not guessed",
              "One-click audit dossier with verified hashes",
            ].map((t) => (
              <div key={t} className="flex items-start gap-2.5 text-[12.5px] text-dim">
                <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--accent)]" />
                {t}
              </div>
            ))}
          </div>

          <p className="mt-8 border-t border-line pt-4 text-[10.5px] leading-relaxed text-mute">
            Readiness assessment and evidence automation. Not a certification, not an
            audit, and not legal advice.
          </p>
        </div>
      </div>
    </main>
  );
}
