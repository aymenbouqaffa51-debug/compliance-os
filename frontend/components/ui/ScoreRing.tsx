export function ScoreRing({
  pct, size = 64, stroke = 6, label,
}: {
  pct: number; size?: number; stroke?: number; label?: string;
}) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const clamped = Math.max(0, Math.min(100, pct));
  const dash = (clamped / 100) * c;

  const tone =
    clamped >= 90 ? "var(--ok)"
    : clamped >= 70 ? "var(--accent)"
    : clamped >= 40 ? "var(--warn)"
    : "var(--bad)";

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke="var(--line-soft)" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none"
                stroke={tone} strokeWidth={stroke} strokeLinecap="round"
                strokeDasharray={`${dash} ${c}`}
                style={{ transition: "stroke-dasharray .6s cubic-bezier(.2,.8,.2,1)" }} />
      </svg>
      <span className="absolute text-[12px] font-semibold tabular-nums" style={{ color: tone }}>
        {label ?? `${Math.round(clamped)}%`}
      </span>
    </div>
  );
}
