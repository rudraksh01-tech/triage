import { THRESHOLD } from "@/lib/config";
import { ago, latency } from "@/lib/format";
import type { Ticket } from "@/lib/types";
import { DraftPanel } from "./DraftPanel";
import { CategoryChip, ConfidenceMeter, PriorityChip, ProbBars, RouteMark, SectionTitle } from "./marks";

function Step({
  index,
  title,
  meta,
  children,
  last = false,
}: {
  index: number;
  title: string;
  meta?: string;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <li className="grid grid-cols-[20px_1fr] gap-3">
      <div className="flex flex-col items-center">
        <span className="flex size-5 items-center justify-center rounded-full border border-line-strong font-mono text-[10px] text-ink-2">
          {index}
        </span>
        {!last && <span className="mt-1 w-px flex-1 bg-line" />}
      </div>
      <div className={last ? "" : "pb-5"}>
        <div className="flex items-baseline gap-2">
          <span className="font-medium">{title}</span>
          {meta && <span className="tnum font-mono text-2xs text-ink-3">{meta}</span>}
        </div>
        <div className="mt-1.5 text-ink-2">{children}</div>
      </div>
    </li>
  );
}

export function TicketDetail({ ticket, now, onBack }: { ticket: Ticket; now: number; onBack?: () => void }) {
  const kept = ticket.route !== "llm";
  const changed =
    ticket.route === "llm" &&
    (ticket.student.category !== ticket.category || ticket.student.priority !== ticket.priority);

  return (
    <article className="flex h-full flex-col">
      <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line px-5">
        {onBack && (
          <button onClick={onBack} className="-ml-1 rounded px-1 text-ink-2 hover:text-ink md:hidden" aria-label="Back to list">
            ←
          </button>
        )}
        <span className="truncate font-mono text-ink-2">@{ticket.brand}</span>
        <span className="text-ink-3">·</span>
        <span className="tnum shrink-0 font-mono text-2xs text-ink-3">{ago(now - ticket.receivedAt)} ago</span>
        <span className="ml-auto hidden font-mono text-2xs text-ink-3 sm:inline">#{ticket.id}</span>
      </header>

      <div className="flex-1 overflow-y-auto">
        <section className="border-b border-line px-5 py-6">
          <p className="max-w-[62ch] text-[15px] leading-[24px] text-ink">{ticket.text}</p>
          <div className="mt-4 flex items-center gap-2">
            <CategoryChip category={ticket.category} />
            <PriorityChip priority={ticket.priority} />
          </div>
        </section>

        <section className="border-b border-line px-5 py-5">
          <SectionTitle>Routing</SectionTitle>
          <ol>
            <Step index={1} title="MiniLM student" meta={latency(ticket.modelMs)} last={kept}>
              <div className="flex items-center gap-3">
                <div className="w-40">
                  <ConfidenceMeter value={ticket.confidence} threshold={THRESHOLD} />
                </div>
                <span className="tnum font-mono text-2xs">
                  {ticket.confidence.toFixed(2)} {ticket.confidence >= THRESHOLD ? "≥" : "<"} {THRESHOLD.toFixed(2)}
                </span>
              </div>
              <p className="mt-2">
                {ticket.route === "model" && "Confident on both labels, so they were accepted without calling the LLM."}
                {ticket.route === "llm" && "Not confident enough on at least one label, so the ticket was passed on."}
                {ticket.route === "deferred" &&
                  "Not confident enough, but the LLM budget for this minute was used up. The model's label is kept and the ticket is flagged."}
              </p>
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <div>
                  <div className="mb-2 text-2xs text-ink-3">Category</div>
                  <ProbBars probs={ticket.probs.category} chosen={ticket.student.category} />
                </div>
                <div>
                  <div className="mb-2 text-2xs text-ink-3">Priority</div>
                  <ProbBars probs={ticket.probs.priority} chosen={ticket.student.priority} />
                </div>
              </div>
            </Step>
            {ticket.route === "llm" && (
              <Step index={2} title="LLM" meta={latency(ticket.llmMs)} last>
                {changed ? (
                  <div className="flex flex-wrap items-center gap-2">
                    Changed the label from
                    <CategoryChip category={`${ticket.student.category} · ${ticket.student.priority}`} muted />
                    to
                    <CategoryChip category={`${ticket.category} · ${ticket.priority}`} />
                  </div>
                ) : (
                  <p>Agreed with the student.</p>
                )}
              </Step>
            )}
          </ol>
          <div className="mt-4 flex items-center gap-2 text-2xs text-ink-3">
            Final route <RouteMark route={ticket.route} />
          </div>
        </section>

        <DraftPanel key={ticket.id} ticket={ticket} />
      </div>
    </article>
  );
}
