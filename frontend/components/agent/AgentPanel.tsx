"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, getToken } from "@/lib/api";
import {
  IconSend, IconSparkles, IconAlert, IconCheck, IconRefresh, IconShield,
} from "@/components/ui/Icons";

type Citation = { kind: string; ref: string; label: string };

type Answer = {
  text: string;
  citations: Citation[];
  intent: string;
  grounded: boolean;
  follow_ups: string[];
  used_llm: boolean;
};

type Turn =
  | { role: "user"; text: string }
  | { role: "agent"; answer: Answer }
  | { role: "error"; text: string };

/**
 * The agent answers ONLY from the client's recorded compliance data. Every
 * claim carries a citation, and when the data does not support an answer it
 * says so rather than guessing. That is a deliberate constraint: a compliance
 * assistant that improvises is a liability, not a feature.
 */
export function AgentPanel({
  clientId, clientName, onClose,
}: {
  clientId: string;
  clientName: string;
  onClose: () => void;
}) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const scroller = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await api<{ suggestions: string[] }>("/api/agent/suggestions");
        setSuggestions(r.suggestions);
      } catch { /* suggestions are optional */ }
    })();
  }, []);

  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [turns, busy]);

  useEffect(() => {
    inputRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ask = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || !clientId || busy) return;
      setInput("");
      setTurns((t) => [...t, { role: "user", text: q }]);
      setBusy(true);
      try {
        const answer = await api<Answer>(`/api/clients/${clientId}/agent/ask`, {
          method: "POST",
          body: JSON.stringify({ question: q }),
        });
        setTurns((t) => [...t, { role: "agent", answer }]);
      } catch (e) {
        setTurns((t) => [
          ...t,
          { role: "error", text: e instanceof Error ? e.message : "Request failed" },
        ]);
      } finally {
        setBusy(false);
        inputRef.current?.focus();
      }
    },
    [clientId, busy],
  );

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(input);
    }
  }

  const hasClient = Boolean(clientId);

  return (
    <>
      {/* backdrop */}
      <div
        className="fixed inset-0 z-40 bg-black/55 backdrop-blur-[2px] animate-in"
        onClick={onClose}
      />

      {/* panel */}
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[480px] flex-col border-l border-line bg-[var(--bg-soft)] shadow-[-24px_0_64px_rgba(0,0,0,.5)] animate-in">
        {/* header */}
        <div className="flex items-center gap-2.5 border-b border-line px-4 py-3.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-[8px] bg-gradient-to-br from-[#6b96ff] to-[#8b5cf6] text-white">
            <IconSparkles size={14} />
          </span>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="text-[13px] font-semibold">Compliance agent</div>
            <div className="truncate text-[11px] text-mute">
              {hasClient ? `grounded in ${clientName}` : "no client selected"}
            </div>
          </div>
          <button
            onClick={() => setTurns([])}
            className="rounded-md p-1.5 text-mute transition hover:bg-white/[.06] hover:text-[var(--text)]"
            title="Clear conversation"
          >
            <IconRefresh size={14} />
          </button>
          <button
            onClick={onClose}
            className="rounded-md px-2 py-1 text-[12px] text-mute transition hover:bg-white/[.06] hover:text-[var(--text)]"
          >
            Esc
          </button>
        </div>

        {/* transcript */}
        <div ref={scroller} className="chat-scroll flex-1 space-y-4 overflow-y-auto px-4 py-4">
          {turns.length === 0 && (
            <div className="space-y-4">
              <div className="rounded-xl border border-line bg-[var(--surface)] p-3.5">
                <div className="flex items-center gap-2 text-[12px] font-medium text-[#c4d6ff]">
                  <IconShield size={13} />
                  Answers come only from your recorded data
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-mute">
                  Every claim is cited to a control, a monitor check or a score.
                  If the data does not support an answer, the agent says so instead
                  of guessing.
                </p>
              </div>

              {hasClient && suggestions.length > 0 && (
                <div className="space-y-1.5">
                  <div className="panel-title">Try asking</div>
                  {suggestions.slice(0, 6).map((s) => (
                    <button
                      key={s}
                      onClick={() => ask(s)}
                      className="group flex w-full items-center gap-2 rounded-[9px] border border-line bg-[var(--surface)] px-3 py-2 text-left text-[12.5px] text-dim transition hover:border-[rgba(91,140,255,.3)] hover:text-[var(--text)]"
                    >
                      <IconSparkles size={12} className="shrink-0 text-mute group-hover:text-[#a9c2ff]" />
                      {s}
                    </button>
                  ))}
                </div>
              )}

              {!hasClient && (
                <div className="rounded-xl border border-[rgba(245,181,68,.25)] bg-[rgba(245,181,68,.07)] p-3.5 text-[12px] text-warn">
                  Create a client first. The agent has nothing to reason about without
                  a compliance record.
                </div>
              )}
            </div>
          )}

          {turns.map((t, i) => (
            <div key={i} className="animate-in">
              {t.role === "user" && (
                <div className="flex justify-end">
                  <div className="msg-user max-w-[85%] px-3.5 py-2.5 text-[13px] leading-relaxed">
                    {t.text}
                  </div>
                </div>
              )}

              {t.role === "error" && (
                <div className="flex items-start gap-2 rounded-xl border border-[rgba(255,92,108,.28)] bg-[rgba(255,92,108,.08)] px-3.5 py-2.5 text-[12.5px] text-bad">
                  <IconAlert size={14} className="mt-0.5 shrink-0" />
                  <span>{t.text}</span>
                </div>
              )}

              {t.role === "agent" && (
                <div className="msg-agent px-3.5 py-3">
                  <div className="mb-2 flex items-center gap-2">
                    <span className="text-[10.5px] font-semibold uppercase tracking-[.1em] text-mute">
                      {t.answer.intent}
                    </span>
                    {!t.answer.grounded && (
                      <span className="pill border-[rgba(245,181,68,.28)] bg-[rgba(245,181,68,.10)] text-[10px] text-warn">
                        limited data
                      </span>
                    )}
                    {t.answer.used_llm && (
                      <span className="pill border-[rgba(91,140,255,.24)] bg-[rgba(91,140,255,.10)] text-[10px] text-[#a9c2ff]">
                        polished
                      </span>
                    )}
                  </div>

                  <div className="whitespace-pre-wrap text-[13px] leading-[1.65] text-[var(--text)]">
                    {renderMarkdownish(t.answer.text)}
                  </div>

                  {t.answer.citations.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5 border-t border-line-soft pt-2.5">
                      {t.answer.citations.slice(0, 8).map((c, j) => (
                        <span key={j} className="citation" title={c.label}>
                          {c.ref}
                        </span>
                      ))}
                      {t.answer.citations.length > 8 && (
                        <span className="text-[10.5px] text-mute">
                          +{t.answer.citations.length - 8}
                        </span>
                      )}
                    </div>
                  )}

                  {t.answer.follow_ups.length > 0 && (
                    <div className="mt-2.5 flex flex-wrap gap-1.5">
                      {t.answer.follow_ups.slice(0, 3).map((f) => (
                        <button
                          key={f}
                          onClick={() => ask(f)}
                          className="rounded-full border border-line bg-white/[.03] px-2.5 py-1 text-[11px] text-dim transition hover:border-[rgba(91,140,255,.3)] hover:text-[var(--text)]"
                        >
                          {f}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {busy && (
            <div className="msg-agent flex items-center gap-2 px-3.5 py-3">
              <span className="h-1.5 w-1.5 rounded-full bg-[var(--accent)] animate-pulse-dot" />
              <span className="text-[12.5px] text-mute">reading your compliance record</span>
            </div>
          )}
        </div>

        {/* composer */}
        <div className="border-t border-line p-3">
          <div className="flex items-end gap-2">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              disabled={!hasClient || busy}
              placeholder={hasClient ? "Ask about gaps, readiness, monitors…" : "Select a client first"}
              className="input max-h-32 min-h-[38px] flex-1 resize-none py-2.5 text-[13px]"
            />
            <button
              onClick={() => ask(input)}
              disabled={!input.trim() || !hasClient || busy}
              className="btn-primary h-[38px] w-[38px] shrink-0 px-0"
              title="Send"
            >
              <IconSend size={15} />
            </button>
          </div>
          <div className="mt-1.5 flex items-center gap-1.5 text-[10.5px] text-mute">
            <IconCheck size={10} />
            grounded in your data &middot; cited &middot; never invents a pass
          </div>
        </div>
      </aside>
    </>
  );
}

/** Minimal inline formatting: **bold** and `code` only. */
function renderMarkdownish(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g);
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) {
      return (
        <strong key={i} className="font-semibold text-[var(--text)]">
          {p.slice(2, -2)}
        </strong>
      );
    }
    if (p.startsWith("`") && p.endsWith("`")) {
      return (
        <code key={i} className="rounded bg-black/40 px-1 py-0.5 font-mono text-[11.5px] text-[#a9c2ff]">
          {p.slice(1, -1)}
        </code>
      );
    }
    return <span key={i}>{p}</span>;
  });
}
