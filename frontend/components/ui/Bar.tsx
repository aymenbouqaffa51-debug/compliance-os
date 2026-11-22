export function Bar({ pct, tone }: { pct: number; tone?: "ok" | "warn" | "bad" | "accent" }) {
  const clamped = Math.max(0, Math.min(100, pct));
  const bg =
    tone === "ok" ? "var(--ok)"
    : tone === "warn" ? "var(--warn)"
    : tone === "bad" ? "var(--bad)"
    : "linear-gradient(90deg, var(--accent), var(--accent-2))";
  return (
    <div className="track">
      <span style={{ width: `${clamped}%`, background: bg }} />
    </div>
  );
}
