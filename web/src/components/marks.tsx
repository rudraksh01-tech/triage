import type { Priority, Route } from "@/lib/types";

const PRIORITY_BAR: Record<Priority, string> = {
  high: "bg-high",
  medium: "bg-medium",
  low: "bg-low/60",
};

const PRIORITY_CHIP: Record<Priority, string> = {
  high: "bg-high-soft text-high",
  medium: "bg-medium-soft text-medium",
  low: "bg-low-soft text-low",
};

export function PriorityBar({ priority }: { priority: Priority }) {
  return (
    <span
      aria-label={`${priority} priority`}
      className={`block h-full w-[3px] rounded-full ${PRIORITY_BAR[priority]}`}
    />
  );
}

export function PriorityChip({ priority }: { priority: Priority }) {
  return (
    <span className={`inline-flex h-5 items-center rounded px-1.5 text-2xs font-medium ${PRIORITY_CHIP[priority]}`}>
      {priority}
    </span>
  );
}

export function CategoryChip({ category, muted = false }: { category: string; muted?: boolean }) {
  return (
    <span
      className={`inline-flex h-5 items-center rounded border px-1.5 text-2xs ${
        muted ? "border-dashed border-line-strong text-ink-3 line-through" : "border-line text-ink-2"
      }`}
    >
      {category}
    </span>
  );
}

const ROUTE: Record<Route, { label: string; title: string; cls: string }> = {
  model: { label: "model", title: "Handled by the fine-tuned model", cls: "text-accent" },
  llm: { label: "escalated", title: "Low confidence, labelled by the LLM", cls: "text-llm" },
  deferred: {
    label: "deferred",
    title: "Low confidence, but the LLM budget was used up. Model label kept.",
    cls: "text-medium",
  },
};

export function RouteMark({ route, compact = false }: { route: Route; compact?: boolean }) {
  const r = ROUTE[route];
  return (
    <span title={r.title} className={`inline-flex items-center gap-1 font-mono text-2xs ${r.cls}`}>
      <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden>
        {route === "model" && <rect x="1" y="1" width="6" height="6" rx="1" fill="currentColor" />}
        {route === "llm" && <path d="M4 0.5 7.5 4 4 7.5 0.5 4Z" fill="currentColor" />}
        {route === "deferred" && (
          <rect x="1" y="1" width="6" height="6" rx="1" fill="none" stroke="currentColor" strokeWidth="1.4" />
        )}
      </svg>
      {!compact && r.label}
    </span>
  );
}

export function ConfidenceMeter({ value, threshold }: { value: number; threshold: number }) {
  const ok = value >= threshold;
  return (
    <div
      className="relative h-1.5 w-full rounded-full bg-line"
      role="meter"
      aria-label="Model confidence"
      aria-valuenow={value}
      aria-valuemin={0}
      aria-valuemax={1}
    >
      <div className={`h-full rounded-full ${ok ? "bg-accent" : "bg-llm"}`} style={{ width: `${value * 100}%` }} />
      <div
        className="absolute -top-1 h-3.5 w-px bg-ink-2"
        style={{ left: `${threshold * 100}%` }}
        title={`threshold ${threshold}`}
      />
    </div>
  );
}

export function ProbBars({ probs, chosen }: { probs: Record<string, number>; chosen: string }) {
  const top = Object.entries(probs)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3);
  return (
    <div className="grid grid-cols-[84px_1fr_40px] items-center gap-x-3 gap-y-1.5">
      {top.map(([label, p]) => (
        <div key={label} className="contents">
          <span className={`truncate text-2xs ${label === chosen ? "text-ink" : "text-ink-3"}`}>{label}</span>
          <div className="h-1 rounded-full bg-line">
            <div
              className={`h-full rounded-full ${label === chosen ? "bg-ink-2" : "bg-line-strong"}`}
              style={{ width: `${p * 100}%` }}
            />
          </div>
          <span className="tnum text-right font-mono text-2xs text-ink-3">{p.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-[18px] min-w-[18px] items-center justify-center rounded border border-line bg-surface-2 px-1 font-mono text-[10px] text-ink-3">
      {children}
    </kbd>
  );
}

export function SectionTitle({ children }: { children: React.ReactNode }) {
  return <h2 className="mb-3 text-2xs font-medium uppercase tracking-[0.06em] text-ink-3">{children}</h2>;
}
