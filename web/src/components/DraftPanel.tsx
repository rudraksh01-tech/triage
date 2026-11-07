"use client";

import { useState } from "react";
import { API_URL } from "@/lib/config";
import type { Draft, Ticket } from "@/lib/types";
import { SectionTitle } from "./marks";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "done"; draft: Draft }
  | { kind: "error"; message: string };

export function DraftPanel({ ticket }: { ticket: Ticket }) {
  const [state, setState] = useState<State>({ kind: "idle" });
  const [copied, setCopied] = useState(false);

  async function run() {
    if (!API_URL) return;
    setState({ kind: "loading" });
    try {
      const res = await fetch(`${API_URL}/v1/draft`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ text: ticket.text, brand: ticket.brand }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setState({ kind: "done", draft: (await res.json()) as Draft });
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : "request failed" });
    }
  }

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {}
  }

  return (
    <section className="px-5 py-5">
      <SectionTitle>Draft reply</SectionTitle>

      {state.kind === "idle" && (
        <div className="flex items-center justify-between gap-4 rounded-md border border-dashed border-line-strong px-4 py-4">
          <p className="text-ink-3">
            {API_URL
              ? "Writes a first reply using how agents answered the most similar past tickets."
              : "Drafting needs the API, which isn't connected in this preview."}
          </p>
          <button
            onClick={run}
            disabled={!API_URL}
            className="h-8 shrink-0 rounded-md bg-accent px-3 font-medium text-accent-ink hover:opacity-90 disabled:opacity-40"
          >
            Draft reply
          </button>
        </div>
      )}

      {state.kind === "loading" && (
        <div className="space-y-2 rounded-md border border-line px-4 py-4" aria-busy="true">
          <div className="h-3 w-4/5 animate-pulse rounded bg-hover" />
          <div className="h-3 w-3/5 animate-pulse rounded bg-hover" />
        </div>
      )}

      {state.kind === "error" && (
        <div className="flex items-center justify-between rounded-md border border-line px-4 py-3 text-ink-2">
          Couldn&apos;t draft a reply ({state.message}).
          <button onClick={run} className="text-accent hover:underline">
            Retry
          </button>
        </div>
      )}

      {state.kind === "done" && (
        <div className="space-y-4">
          {state.draft.draft ? (
            <div className="rounded-md border border-line bg-surface-2 px-4 py-3">
              <p className="whitespace-pre-wrap text-ink">{state.draft.draft}</p>
              <div className="mt-3 flex items-center gap-3 text-2xs text-ink-3">
                <span className="tnum font-mono">{state.draft.draft.length}/280</span>
                <button onClick={() => copy(state.draft.draft!)} className="ml-auto text-accent hover:underline">
                  {copied ? "Copied" : "Copy"}
                </button>
                <button onClick={run} className="hover:text-ink">
                  Regenerate
                </button>
              </div>
            </div>
          ) : (
            <p className="rounded-md border border-line px-4 py-3 text-ink-2">
              No draft: {state.draft.reason ?? "the LLM didn't answer"}. The examples below are still useful.
            </p>
          )}

          <details className="group" open={!state.draft.draft}>
            <summary className="cursor-pointer list-none text-2xs text-ink-3 hover:text-ink">
              <span className="group-open:hidden">Show</span>
              <span className="hidden group-open:inline">Hide</span> the {state.draft.examples.length} past tickets it
              was based on
            </summary>
            <ol className="mt-3 space-y-3">
              {state.draft.examples.map((ex, i) => (
                <li key={i} className="rounded-md border border-line px-3 py-2.5">
                  <div className="flex items-center gap-2 text-2xs text-ink-3">
                    <span className="font-mono">@{ex.brand}</span>
                    <span className="tnum ml-auto font-mono" title="cosine similarity / cross-encoder score">
                      sim {ex.similarity.toFixed(2)}
                      {ex.rerank_score != null && ` · rerank ${ex.rerank_score.toFixed(1)}`}
                    </span>
                  </div>
                  <p className="mt-1 text-ink-2">{ex.ticket}</p>
                  <p className="mt-1.5 border-l-2 border-accent/40 pl-2 text-ink">{ex.reply}</p>
                </li>
              ))}
            </ol>
          </details>
        </div>
      )}
    </section>
  );
}
