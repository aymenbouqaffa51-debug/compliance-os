// Inline SVG icons. No icon package: keeps the bundle small and the licence
// surface at zero.

type P = { className?: string; size?: number };

const base = (size = 16) => ({
  width: size, height: size, viewBox: "0 0 24 24", fill: "none",
  stroke: "currentColor", strokeWidth: 1.75,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const,
});

export const IconGauge = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M12 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"/><path d="m13.4 10.6 3.6-3.6"/><path d="M3 20a9 9 0 1 1 18 0"/></svg>
);
export const IconPulse = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M3 12h4l2-7 4 14 2-7h6"/></svg>
);
export const IconPlug = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M9 3v6"/><path d="M15 3v6"/><path d="M6 9h12v3a6 6 0 0 1-12 0V9Z"/><path d="M12 18v3"/></svg>
);
export const IconDoc = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h4"/></svg>
);
export const IconClipboard = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M9 4h6v3H9z"/><path d="M9 5.5H7a2 2 0 0 0-2 2V19a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7.5a2 2 0 0 0-2-2h-2"/><path d="M9 12h6M9 16h4"/></svg>
);
export const IconSparkles = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3v4M12 17v4M3 12h4M17 12h4"/><path d="m6.3 6.3 2.4 2.4M15.3 15.3l2.4 2.4M17.7 6.3l-2.4 2.4M8.7 15.3l-2.4 2.4"/></svg>
);
export const IconShield = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3 5 6v6c0 4.4 3 8 7 9 4-1 7-4.6 7-9V6Z"/><path d="m9 12 2 2 4-4"/></svg>
);
export const IconAlert = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z"/></svg>
);
export const IconCheck = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="m4 12 5 5L20 6"/></svg>
);
export const IconArrowRight = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M5 12h14M13 6l6 6-6 6"/></svg>
);
export const IconDownload = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M12 3v12M7 11l5 5 5-5"/><path d="M5 21h14"/></svg>
);
export const IconSend = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="m4 12 16-8-6 16-2.5-6.5L4 12Z"/></svg>
);
export const IconRefresh = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M20 11a8 8 0 1 0-1.6 5.6"/><path d="M20 5v6h-6"/></svg>
);
export const IconLogout = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4"/><path d="M10 12H3M6 8l-4 4 4 4"/></svg>
);
export const IconChevron = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="m8 10 4 4 4-4"/></svg>
);
export const IconExternal = ({ className, size }: P) => (
  <svg {...base(size)} className={className}><path d="M14 4h6v6"/><path d="M20 4 10 14"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/></svg>
);
