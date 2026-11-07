import Link from "next/link";
import { capitalize } from "@/lib/format";
import { CATEGORIES, type Ticket } from "@/lib/types";

export type View =
  | { kind: "all" }
  | { kind: "priority"; value: "high" }
  | { kind: "route"; value: "llm" | "deferred" }
  | { kind: "category"; value: string };

export function matches(view: View, t: Ticket): boolean {
  switch (view.kind) {
    case "all":
      return true;
    case "priority":
      return t.priority === view.value;
    case "route":
      return t.route === view.value;
    case "category":
      return t.category === view.value;
  }
}

function same(a: View, b: View) {
  return a.kind === b.kind && ("value" in a ? a.value : "") === ("value" in b ? b.value : "");
}

function Item({
  v,
  label,
  dot,
  view,
  tickets,
  onChange,
}: {
  v: View;
  label: string;
  dot?: string;
  view: View;
  tickets: Ticket[];
  onChange: (v: View) => void;
}) {
  const active = same(v, view);
  const count = tickets.filter((t) => matches(v, t)).length;
  return (
    <button
      onClick={() => onChange(v)}
      aria-current={active ? "page" : undefined}
      className={`flex h-7 w-full items-center gap-2 rounded-md px-2 text-left ${
        active ? "bg-hover text-ink" : "text-ink-2 hover:bg-hover/70 hover:text-ink"
      }`}
    >
      {dot && <span className={`size-1.5 rounded-full ${dot}`} />}
      <span className="flex-1 truncate">{label}</span>
      <span className="tnum font-mono text-2xs text-ink-3">{count}</span>
    </button>
  );
}

export function Sidebar({
  tickets,
  view,
  onChange,
}: {
  tickets: Ticket[];
  view: View;
  onChange: (v: View) => void;
}) {
  const shared = { view, tickets, onChange };

  return (
    <nav className="flex flex-col gap-5 p-3" aria-label="Queues">
      <div className="flex flex-col gap-px">
        <Item {...shared} v={{ kind: "all" }} label="All tickets" />
        <Item {...shared} v={{ kind: "priority", value: "high" }} label="High priority" dot="bg-high" />
        <Item {...shared} v={{ kind: "route", value: "llm" }} label="Escalated to LLM" dot="bg-llm" />
        <Item {...shared} v={{ kind: "route", value: "deferred" }} label="Deferred" dot="bg-medium" />
      </div>
      <div className="flex flex-col gap-px">
        <div className="px-2 pb-1 text-2xs font-medium uppercase tracking-[0.06em] text-ink-3">Category</div>
        {CATEGORIES.map((c) => (
          <Item {...shared} key={c} v={{ kind: "category", value: c }} label={capitalize(c)} />
        ))}
      </div>
      <Link href="/metrics" className="mx-2 border-t border-line pt-4 text-ink-2 hover:text-ink">
        How it was measured →
      </Link>
    </nav>
  );
}
