"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";
import { REALTIME_URL } from "@/lib/config";
import { latency, median, pct } from "@/lib/format";
import type { FeedStatus } from "@/lib/live";
import type { QueueStats, Ticket } from "@/lib/types";

type Theme = "system" | "light" | "dark";
const NEXT: Record<Theme, Theme> = { system: "light", light: "dark", dark: "system" };

// The html data-theme attribute is the source of truth; an inline script in
// layout.tsx sets it from localStorage before first paint.
function readTheme(): Theme {
  return (document.documentElement.dataset.theme as Theme | undefined) ?? "system";
}

function subscribe(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });
  return () => observer.disconnect();
}

function useTheme() {
  const theme = useSyncExternalStore(subscribe, readTheme, () => "system" as Theme);
  function cycle() {
    const next = NEXT[theme];
    const root = document.documentElement;
    if (next === "system") delete root.dataset.theme;
    else root.dataset.theme = next;
    try {
      localStorage.setItem("theme", next);
    } catch {}
  }
  return [theme, cycle] as const;
}

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col justify-center" title={hint}>
      <span className="text-2xs text-ink-3">{label}</span>
      <span className="tnum font-mono text-[13px] text-ink">{value}</span>
    </div>
  );
}

function Sparkline({ values }: { values: number[] }) {
  const w = 96;
  const h = 22;
  if (values.length < 2) return <svg width={w} height={h} aria-hidden />;
  const max = Math.max(4, ...values);
  const step = w / (values.length - 1);
  const pts = values.map((v, i) => `${(i * step).toFixed(1)},${(h - 1 - (v / max) * (h - 2)).toFixed(1)}`);
  return (
    <svg width={w} height={h} aria-label={`Queue depth, last ${values.length} seconds`} role="img">
      <polyline points={pts.join(" ")} fill="none" stroke="var(--accent)" strokeWidth="1.25" strokeLinejoin="round" />
    </svg>
  );
}

const STATUS: Record<FeedStatus, { label: string; dot: string }> = {
  live: { label: "Live", dot: "bg-accent" },
  connecting: { label: "Reconnecting", dot: "bg-medium" },
  offline: { label: "Sample data", dot: "bg-low" },
};

function BurstButton({ queue }: { queue: QueueStats | null }) {
  const [pending, setPending] = useState(false);
  const cooling = (queue?.burstReadyInMs ?? 0) > 0;

  async function fire() {
    if (!REALTIME_URL) return;
    setPending(true);
    try {
      await fetch(`${REALTIME_URL}/burst`, { method: "POST" });
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      onClick={fire}
      disabled={!queue || cooling || pending}
      title="Drops 300 tickets into the queue at once, like an outage would"
      className="h-7 rounded-md border border-line px-2.5 text-2xs text-ink-2 hover:bg-hover disabled:opacity-50"
    >
      {cooling ? `Outage again in ${Math.ceil((queue?.burstReadyInMs ?? 0) / 1000)}s` : "Simulate outage"}
    </button>
  );
}

export function Topbar({
  tickets,
  status,
  queue,
  depthHistory,
}: {
  tickets: Ticket[];
  status: FeedStatus;
  queue: QueueStats | null;
  depthHistory: number[];
}) {
  const [theme, cycleTheme] = useTheme();
  const n = tickets.length || 1;
  const byModel = tickets.filter((t) => t.route === "model").length;
  const escalated = tickets.filter((t) => t.route === "llm");
  const deferred = tickets.filter((t) => t.route === "deferred").length;
  const s = STATUS[status];

  return (
    <header className="flex h-14 shrink-0 items-center gap-6 border-b border-line bg-surface px-4">
      <Link href="/" className="flex items-center gap-2">
        <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
          <rect x="1" y="1" width="16" height="16" rx="4" className="fill-accent" />
          <path d="M5 6h8M7 9h4M8.5 12h1" stroke="var(--accent-ink)" strokeWidth="1.6" strokeLinecap="round" />
        </svg>
        <span className="text-[14px] font-semibold tracking-[-0.01em]">Triage</span>
      </Link>

      <div className="hidden items-center gap-6 border-l border-line pl-6 lg:flex">
        <Stat label="Handled by model" value={pct(byModel / n)} hint="Share of tickets that never reached the LLM" />
        <Stat label="Escalated" value={`${escalated.length}`} hint={`${deferred} more wanted the LLM but were deferred`} />
        <Stat label="Model p50" value={latency(median(tickets.map((t) => t.modelMs)))} />
        <Stat label="LLM p50" value={latency(median(escalated.map((t) => t.llmMs ?? 0)))} />
        {queue && (
          <div className="flex items-center gap-3 border-l border-line pl-6">
            <Stat label="In queue" value={`${queue.waiting + queue.active}`} hint={`${queue.doneLastMinute} done in the last minute`} />
            <Sparkline values={depthHistory} />
          </div>
        )}
      </div>

      <div className="ml-auto flex items-center gap-3">
        {queue && <BurstButton queue={queue} />}
        <span className="flex items-center gap-1.5 text-2xs text-ink-3" role="status">
          <span className="relative flex size-1.5">
            {status === "live" && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-50" />
            )}
            <span className={`relative inline-flex size-1.5 rounded-full ${s.dot}`} />
          </span>
          {s.label}
        </span>
        <button
          onClick={cycleTheme}
          className="h-7 rounded-md border border-line px-2 text-2xs text-ink-2 hover:bg-hover"
          aria-label={`Theme: ${theme}. Click to change.`}
        >
          {theme}
        </button>
      </div>
    </header>
  );
}
