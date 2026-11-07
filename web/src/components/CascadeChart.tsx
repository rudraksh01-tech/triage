"use client";

import { useEffect, useId, useRef, useState } from "react";
import { pct } from "@/lib/format";
import type { CurvePoint } from "@/lib/results";

const H = 240;
const M = { top: 16, right: 20, bottom: 36, left: 44 };

function niceDomain(values: number[]): [number, number] {
  const lo = Math.floor((Math.min(...values) - 0.02) * 20) / 20;
  const hi = Math.ceil((Math.max(...values) + 0.01) * 20) / 20;
  return [Math.max(0, lo), Math.min(1, hi)];
}

export function CascadeChart({
  title,
  points,
  metric,
  llmOnly,
  threshold,
}: {
  title: string;
  points: CurvePoint[];
  metric: "category_accuracy" | "priority_accuracy";
  llmOnly: number;
  threshold: number;
}) {
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(560);
  const [hover, setHover] = useState<number | null>(null);
  const titleId = useId();

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.max(280, e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // one point per distinct escalation rate keeps the line honest (thresholds that
  // route the same tickets are the same operating point)
  const pts = points
    .filter((p, i, a) => i === 0 || p.escalated !== a[i - 1].escalated)
    .sort((a, b) => a.escalated - b.escalated);
  const chosen = points.find((p) => p.threshold === threshold) ?? pts[0];

  const [y0, y1] = niceDomain([...pts.map((p) => p[metric]), llmOnly]);
  const iw = width - M.left - M.right;
  const ih = H - M.top - M.bottom;
  const x = (v: number) => M.left + v * iw;
  const y = (v: number) => M.top + (1 - (v - y0) / (y1 - y0)) * ih;
  const yTicks = Array.from({ length: Math.round((y1 - y0) / 0.05) + 1 }, (_, i) => y0 + i * 0.05).filter(
    (_, i, a) => a.length <= 7 || i % 2 === 0,
  );
  const path = pts.map((p, i) => `${i ? "L" : "M"}${x(p.escalated).toFixed(1)},${y(p[metric]).toFixed(1)}`).join("");

  function nearest(px: number) {
    const v = (px - M.left) / iw;
    let best = 0;
    pts.forEach((p, i) => {
      if (Math.abs(p.escalated - v) < Math.abs(pts[best].escalated - v)) best = i;
    });
    return best;
  }

  const h = hover == null ? null : pts[hover];
  const tipLeft = h ? Math.min(width - 170, Math.max(0, x(h.escalated) + 10)) : 0;

  return (
    <figure className="min-w-0" aria-labelledby={titleId}>
      <figcaption id={titleId} className="mb-2 text-[13px] font-medium">
        {title}
      </figcaption>
      <div ref={wrap} className="relative">
        <svg
          width={width}
          height={H}
          role="img"
          aria-label={`${title}: accuracy against share of tickets escalated. Values in the table below.`}
          tabIndex={0}
          className="block touch-none outline-none focus-visible:ring-2 focus-visible:ring-accent"
          onPointerMove={(e) => setHover(nearest(e.clientX - e.currentTarget.getBoundingClientRect().left))}
          onPointerLeave={() => setHover(null)}
          onFocus={() => setHover(pts.indexOf(chosen) >= 0 ? pts.indexOf(chosen) : 0)}
          onBlur={() => setHover(null)}
          onKeyDown={(e) => {
            if (e.key === "ArrowRight") setHover((i) => Math.min(pts.length - 1, (i ?? 0) + 1));
            if (e.key === "ArrowLeft") setHover((i) => Math.max(0, (i ?? 0) - 1));
          }}
        >
          {yTicks.map((t) => (
            <g key={t}>
              <line x1={M.left} x2={width - M.right} y1={y(t)} y2={y(t)} stroke="var(--line)" strokeWidth="1" />
              <text x={M.left - 8} y={y(t)} dy="0.32em" textAnchor="end" className="fill-ink-3 font-mono text-[10px]">
                {pct(t)}
              </text>
            </g>
          ))}
          {[0, 0.25, 0.5, 0.75, 1].map((t) => (
            <text key={t} x={x(t)} y={H - M.bottom + 18} textAnchor="middle" className="fill-ink-3 font-mono text-[10px]">
              {pct(t)}
            </text>
          ))}
          <text x={M.left + iw / 2} y={H - 4} textAnchor="middle" className="fill-ink-3 text-[11px]">
            Tickets sent to the LLM
          </text>

          {/* reference: every ticket to the LLM */}
          <line x1={M.left} x2={width - M.right} y1={y(llmOnly)} y2={y(llmOnly)} stroke="var(--ink-3)" strokeWidth="1.5" />
          <text x={M.left + 6} y={y(llmOnly) - 6} className="fill-ink-2 text-[11px]" paintOrder="stroke" stroke="var(--paper)" strokeWidth="4">
            LLM on every ticket · {pct(llmOnly, 1)}
          </text>

          <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" />

          {/* deployed operating point */}
          <circle cx={x(chosen.escalated)} cy={y(chosen[metric])} r="5" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />
          <text
            x={x(chosen.escalated) + (chosen.escalated > 0.6 ? -10 : 10)}
            y={y(chosen[metric]) + 18}
            textAnchor={chosen.escalated > 0.6 ? "end" : "start"}
            className="fill-ink text-[11px] font-medium" paintOrder="stroke" stroke="var(--paper)" strokeWidth="4"
          >
            Deployed · {pct(chosen.escalated)} escalated · {pct(chosen[metric], 1)}
          </text>

          {h && (
            <g pointerEvents="none">
              <line x1={x(h.escalated)} x2={x(h.escalated)} y1={M.top} y2={M.top + ih} stroke="var(--ink-3)" strokeWidth="1" />
              <circle cx={x(h.escalated)} cy={y(h[metric])} r="4" fill="var(--accent)" stroke="var(--surface)" strokeWidth="2" />
            </g>
          )}
        </svg>

        {h && (
          <div
            className="pointer-events-none absolute top-2 w-[160px] rounded-md border border-line bg-surface px-3 py-2 shadow-sm"
            style={{ left: tipLeft }}
            role="status"
          >
            <div className="tnum font-mono text-[15px] text-ink">{pct(h[metric], 1)}</div>
            <div className="flex items-center gap-1.5 text-2xs text-ink-2">
              <span className="inline-block h-0.5 w-3 rounded bg-accent" /> accuracy with cascade
            </div>
            <div className="mt-1.5 text-2xs text-ink-3">
              <span className="tnum font-mono text-ink-2">{pct(h.escalated, 1)}</span> escalated · threshold{" "}
              <span className="tnum font-mono text-ink-2">{h.threshold.toFixed(2)}</span>
            </div>
          </div>
        )}
      </div>
    </figure>
  );
}
