import { ReactNode } from "react";

export function Empty({
  icon, title, body, action,
}: { icon?: ReactNode; title: string; body?: ReactNode; action?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 py-12 text-center">
      {icon && <div className="text-mute">{icon}</div>}
      <div className="text-[14px] font-medium">{title}</div>
      {body && <div className="max-w-sm text-[12.5px] leading-relaxed text-mute">{body}</div>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}
