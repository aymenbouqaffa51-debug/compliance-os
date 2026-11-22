import { ReactNode } from "react";

export function Metric({
  label, value, hint, tone = "neutral", icon,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "neutral" | "ok" | "warn" | "bad" | "accent";
  icon?: ReactNode;
}) {
  const colour =
    tone === "ok" ? "text-ok"
    : tone === "warn" ? "text-warn"
    : tone === "bad" ? "text-bad"
    : tone === "accent" ? "text-[#a9c2ff]"
    : "";

  return (
    <div className="metric">
      <div className="flex items-center justify-between">
        <span className="panel-title">{label}</span>
        {icon && <span className="text-mute">{icon}</span>}
      </div>
      <div className={`mt-2 text-[26px] font-semibold leading-none tracking-tight ${colour}`}>
        {value}
      </div>
      {hint && <div className="mt-1.5 text-[11.5px] text-mute">{hint}</div>}
    </div>
  );
}
