export function ago(ms: number): string {
  const s = Math.max(0, ms / 1000);
  if (s < 60) return `${Math.max(1, Math.round(s))}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  if (s < 86400) return `${Math.round(s / 3600)}h`;
  return `${Math.round(s / 86400)}d`;
}

export function latency(ms: number | null | undefined): string {
  if (ms == null) return "–";
  return ms < 100 ? `${ms.toFixed(1)} ms` : `${(ms / 1000).toFixed(2)} s`;
}

export function pct(x: number, digits = 0): string {
  return `${(x * 100).toFixed(digits)}%`;
}

export function median(xs: number[]): number | null {
  if (!xs.length) return null;
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
}

// tweets arrive with the brand handle first, which is noise in a list row
export function stripLeadingHandles(text: string): string {
  return text.replace(/^(\.?@\w+\s*)+/, "").trim() || text;
}

export function capitalize(s: string): string {
  return s[0].toUpperCase() + s.slice(1);
}
