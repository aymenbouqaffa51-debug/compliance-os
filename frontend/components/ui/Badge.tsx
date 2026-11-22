const STYLES: Record<string, string> = {
  PASS: "bg-[rgba(36,209,126,.12)] text-ok border-[rgba(36,209,126,.28)]",
  FAIL: "bg-[rgba(255,92,108,.12)] text-bad border-[rgba(255,92,108,.28)]",
  ERROR: "bg-[rgba(245,181,68,.12)] text-warn border-[rgba(245,181,68,.28)]",
  NOT_APPLICABLE: "bg-white/[.04] text-mute border-line",
  SKIPPED: "bg-white/[.04] text-mute border-line",
  implemented: "bg-[rgba(36,209,126,.12)] text-ok border-[rgba(36,209,126,.28)]",
  partial: "bg-[rgba(245,181,68,.12)] text-warn border-[rgba(245,181,68,.28)]",
  gap: "bg-[rgba(255,92,108,.12)] text-bad border-[rgba(255,92,108,.28)]",
  not_assessed: "bg-white/[.04] text-mute border-line",
  high: "bg-[rgba(36,209,126,.12)] text-ok border-[rgba(36,209,126,.28)]",
  medium: "bg-[rgba(245,181,68,.12)] text-warn border-[rgba(245,181,68,.28)]",
  low: "bg-[rgba(255,92,108,.12)] text-bad border-[rgba(255,92,108,.28)]",
  critical: "bg-[rgba(255,92,108,.16)] text-bad border-[rgba(255,92,108,.34)]",
  neutral: "bg-white/[.04] text-dim border-line",
};

export function Badge({ value, label }: { value: string; label?: string }) {
  const cls = STYLES[value] || STYLES.neutral;
  return (
    <span className={`pill ${cls}`}>
      {label ?? value.replace(/_/g, " ").toLowerCase()}
    </span>
  );
}
