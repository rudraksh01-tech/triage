"use client";

import { useEffect, useMemo, useState } from "react";
import { wsUrl } from "@/lib/config";
import { useFeed, useNow } from "@/lib/live";
import type { Ticket } from "@/lib/types";
import { Kbd } from "./marks";
import { Sidebar, matches, type View } from "./Sidebar";
import { TicketDetail } from "./TicketDetail";
import { TicketList } from "./TicketList";
import { Topbar } from "./Topbar";

export function Inbox({ sample }: { sample: Ticket[] }) {
  const feed = useFeed(wsUrl, sample);
  const clock = useNow();
  const [view, setView] = useState<View>({ kind: "all" });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mobileDetail, setMobileDetail] = useState(false);

  const newest = useMemo(() => Math.max(0, ...feed.tickets.map((t) => t.receivedAt)), [feed.tickets]);
  const now = clock ?? newest;

  // sample timestamps are fixed; shift them so the sample reads as "recent"
  const tickets = useMemo(() => {
    if (feed.status !== "offline" || clock == null) return feed.tickets;
    const shift = clock - newest;
    return feed.tickets.map((t) => ({ ...t, receivedAt: t.receivedAt + shift }));
  }, [feed.tickets, feed.status, clock, newest]);

  const visible = useMemo(() => tickets.filter((t) => matches(view, t)), [tickets, view]);
  // new tickets arrive at the top; keep the user's selection where it is
  const selected = visible.find((t) => t.id === selectedId) ?? visible[0] ?? null;

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      const i = visible.findIndex((t) => t.id === selected?.id);
      if (e.key === "j" || e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedId(visible[Math.min(visible.length - 1, i + 1)]?.id ?? null);
      } else if (e.key === "k" || e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedId(visible[Math.max(0, i - 1)]?.id ?? null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, selected]);

  return (
    <div className="flex h-dvh flex-col">
      <Topbar tickets={tickets} status={feed.status} queue={feed.queue} depthHistory={feed.depthHistory} />
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-56 shrink-0 overflow-y-auto border-r border-line md:block">
          <Sidebar tickets={tickets} view={view} onChange={setView} />
        </aside>

        <section
          className={`min-w-0 flex-1 overflow-y-auto border-r border-line bg-surface md:max-w-[440px] ${
            mobileDetail ? "hidden md:block" : ""
          }`}
        >
          <div className="sticky top-0 z-10 flex h-10 items-center gap-2 border-b border-line bg-surface/90 px-4 backdrop-blur">
            <span className="tnum font-mono text-2xs text-ink-3">{visible.length} tickets</span>
            <span className="ml-auto hidden items-center gap-1 text-2xs text-ink-3 md:flex">
              <Kbd>J</Kbd>
              <Kbd>K</Kbd>
              to move
            </span>
          </div>
          <TicketList
            tickets={visible}
            selectedId={selected?.id ?? null}
            now={now}
            onSelect={(id) => {
              setSelectedId(id);
              setMobileDetail(true);
            }}
          />
        </section>

        <main className={`min-w-0 flex-1 bg-surface ${mobileDetail ? "" : "hidden md:block"}`}>
          {selected ? (
            <TicketDetail ticket={selected} now={now} onBack={() => setMobileDetail(false)} />
          ) : (
            <p className="p-8 text-ink-3">Waiting for the first ticket…</p>
          )}
        </main>
      </div>
    </div>
  );
}
