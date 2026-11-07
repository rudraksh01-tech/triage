import { useEffect, useRef } from "react";
import { ago, stripLeadingHandles } from "@/lib/format";
import type { Ticket } from "@/lib/types";
import { CategoryChip, PriorityBar, RouteMark } from "./marks";

export function TicketList({
  tickets,
  selectedId,
  onSelect,
  now,
}: {
  tickets: Ticket[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  now: number;
}) {
  const listRef = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    listRef.current?.querySelector(`[data-id="${CSS.escape(selectedId)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [selectedId]);

  if (tickets.length === 0) {
    return <p className="p-8 text-center text-ink-3">Nothing in this queue.</p>;
  }

  return (
    <ul ref={listRef} role="listbox" aria-label="Tickets" className="divide-y divide-line">
      {tickets.map((t) => {
        const active = t.id === selectedId;
        return (
          <li key={`${t.id}-${t.doneAt}`} data-id={t.id} role="option" aria-selected={active}>
            <button
              onClick={() => onSelect(t.id)}
              className={`grid w-full grid-cols-[3px_1fr] gap-3 px-4 py-3 text-left ${
                active ? "bg-hover" : "hover:bg-surface-2"
              }`}
            >
              <PriorityBar priority={t.priority} />
              <div className="min-w-0">
                <div className="flex items-center gap-2 text-2xs text-ink-3">
                  <span className="truncate font-mono text-ink-2">@{t.brand}</span>
                  {t.burst && (
                    <span className="rounded bg-medium-soft px-1 text-[10px] text-medium" title="Arrived during a simulated outage">
                      burst
                    </span>
                  )}
                  <span className="tnum ml-auto shrink-0 font-mono">{ago(now - t.receivedAt)}</span>
                </div>
                <p className="mt-0.5 line-clamp-2 text-ink">{stripLeadingHandles(t.text)}</p>
                <div className="mt-2 flex items-center gap-2">
                  <CategoryChip category={t.category} />
                  <RouteMark route={t.route} />
                  <span className="tnum ml-auto font-mono text-2xs text-ink-3">{t.confidence.toFixed(2)}</span>
                </div>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
